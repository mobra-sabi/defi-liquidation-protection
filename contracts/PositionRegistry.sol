// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * @title PositionRegistry
 * @dev Manages user protection configurations and permissions
 *
 * Security principles:
 * 1. Non-custodial - Contract never holds user funds
 * 2. Limited permissions - Only rebalancing, no withdrawals
 * 3. User controls all parameters
 */

contract PositionRegistry {
    // ============ Structs ============

    struct UserProtectionConfig {
        address user;
        address lendingProtocol;      // Aave/Morpho pool address
        uint256 triggerHealthFactor;  // HF below which AI acts (e.g., 1.15 = 115%)
        uint256 targetHealthFactor;   // HF to rebalance to (e.g., 1.40 = 140%)
        uint256 maxRebalancePercent;  // Max % of position to rebalance at once
        bool isActive;
        uint256 lastActionTimestamp;
        uint256 totalExecutions;      // Track for circuit breaker
        uint256 registrationTime;
    }

    // ============ State Variables ============

    // User => Config
    mapping(address => UserProtectionConfig) public userConfigs;

    // AI Executor addresses (multisig or governance controlled)
    mapping(address => bool) public aiExecutors;

    // Circuit breaker tracking: user => hour => count
    mapping(address => mapping(uint256 => uint256)) public hourlyExecutionCount;

    // Protocol owner
    address public owner;

    // Emergency pause
    bool public paused;

    // Circuit breaker threshold
    uint256 public constant CIRCUIT_BREAKER_THRESHOLD = 10;
    uint256 public constant CIRCUIT_BREAKER_WINDOW = 1 hours;

    // ============ Events ============

    event PositionRegistered(
        address indexed user,
        address indexed lendingProtocol,
        uint256 triggerHF,
        uint256 targetHF,
        uint256 maxRebalancePercent
    );

    event PositionUpdated(
        address indexed user,
        uint256 triggerHF,
        uint256 targetHF,
        uint256 maxRebalancePercent
    );

    event PositionDeactivated(address indexed user);
    event PositionReactivated(address indexed user);

    event AIExecutorAdded(address indexed executor);
    event AIExecutorRemoved(address indexed executor);

    event ProtectionExecuted(
        address indexed user,
        uint256 collateralSold,
        uint256 debtRepaid,
        uint256 newHealthFactor,
        uint256 timestamp
    );

    event CircuitBreakerTriggered(address indexed user, uint256 hour, uint256 count);
    event EmergencyPauseTriggered(address indexed triggeredBy);
    event EmergencyPauseLifted(address indexed triggeredBy);

    // ============ Modifiers ============

    modifier onlyOwner() {
        require(msg.sender == owner, "Only owner");
        _;
    }

    modifier onlyAIExecutor() {
        require(aiExecutors[msg.sender], "Only AI executor");
        _;
    }

    modifier whenNotPaused() {
        require(!paused, "Contract paused");
        _;
    }

    modifier validHealthFactors(uint256 trigger, uint256 target) {
        require(trigger > 1e18, "Trigger must be > 1.0");
        require(target > trigger, "Target must be > trigger");
        require(target <= 3e18, "Target must be <= 3.0");
        _;
    }

    // ============ Constructor ============

    constructor() {
        owner = msg.sender;
        paused = false;

        // Add deployer as AI executor initially
        aiExecutors[msg.sender] = true;
        emit AIExecutorAdded(msg.sender);
    }

    // ============ User Functions ============

    /**
     * @notice Register a new position for protection
     * @param lendingProtocol Address of Aave/Morpho pool
     * @param triggerHF Health factor threshold to trigger protection (scaled by 1e18)
     * @param targetHF Target health factor after rebalancing (scaled by 1e18)
     * @param maxRebalancePercent Max percentage of position to rebalance (0-100)
     */
    function registerPosition(
        address lendingProtocol,
        uint256 triggerHF,
        uint256 targetHF,
        uint256 maxRebalancePercent
    ) external whenNotPaused validHealthFactors(triggerHF, targetHF) {
        require(lendingProtocol != address(0), "Invalid protocol address");
        require(maxRebalancePercent > 0 && maxRebalancePercent <= 50, "Rebalance % must be 1-50");
        require(userConfigs[msg.sender].registrationTime == 0, "Already registered");

        userConfigs[msg.sender] = UserProtectionConfig({
            user: msg.sender,
            lendingProtocol: lendingProtocol,
            triggerHealthFactor: triggerHF,
            targetHealthFactor: targetHF,
            maxRebalancePercent: maxRebalancePercent,
            isActive: true,
            lastActionTimestamp: 0,
            totalExecutions: 0,
            registrationTime: block.timestamp
        });

        emit PositionRegistered(
            msg.sender,
            lendingProtocol,
            triggerHF,
            targetHF,
            maxRebalancePercent
        );
    }

    /**
     * @notice Update protection parameters
     */
    function updateConfig(
        uint256 triggerHF,
        uint256 targetHF,
        uint256 maxRebalancePercent
    ) external whenNotPaused validHealthFactors(triggerHF, targetHF) {
        require(userConfigs[msg.sender].registrationTime > 0, "Not registered");
        require(maxRebalancePercent > 0 && maxRebalancePercent <= 50, "Rebalance % must be 1-50");

        UserProtectionConfig storage config = userConfigs[msg.sender];
        config.triggerHealthFactor = triggerHF;
        config.targetHealthFactor = targetHF;
        config.maxRebalancePercent = maxRebalancePercent;

        emit PositionUpdated(msg.sender, triggerHF, targetHF, maxRebalancePercent);
    }

    /**
     * @notice Deactivate protection (user can call anytime)
     */
    function deactivate() external {
        require(userConfigs[msg.sender].registrationTime > 0, "Not registered");
        userConfigs[msg.sender].isActive = false;
        emit PositionDeactivated(msg.sender);
    }

    /**
     * @notice Reactivate protection
     */
    function reactivate() external whenNotPaused {
        require(userConfigs[msg.sender].registrationTime > 0, "Not registered");
        userConfigs[msg.sender].isActive = true;
        emit PositionReactivated(msg.sender);
    }

    /**
     * @notice Unregister completely (removes all data)
     */
    function unregister() external {
        require(userConfigs[msg.sender].registrationTime > 0, "Not registered");
        delete userConfigs[msg.sender];
    }

    // ============ AI Executor Functions ============

    /**
     * @notice Record a protection execution (called by ProtectionExecutor)
     * @param user Address of protected user
     * @param collateralSold Amount of collateral sold
     * @param debtRepaid Amount of debt repaid
     */
    function recordExecution(
        address user,
        uint256 collateralSold,
        uint256 debtRepaid,
        uint256 newHealthFactor
    ) external onlyAIExecutor whenNotPaused {
        UserProtectionConfig storage config = userConfigs[user];
        require(config.registrationTime > 0, "User not registered");
        require(config.isActive, "Protection not active");

        // Update execution tracking
        config.lastActionTimestamp = block.timestamp;
        config.totalExecutions++;

        // Circuit breaker: track hourly executions
        uint256 currentHour = block.timestamp / 1 hours;
        hourlyExecutionCount[user][currentHour]++;

        emit ProtectionExecuted(
            user,
            collateralSold,
            debtRepaid,
            newHealthFactor,
            block.timestamp
        );
    }

    /**
     * @notice Check if circuit breaker should trigger for user
     */
    function checkCircuitBreaker(address user) external view returns (bool) {
        uint256 currentHour = block.timestamp / 1 hours;
        return hourlyExecutionCount[user][currentHour] >= CIRCUIT_BREAKER_THRESHOLD;
    }

    // ============ Owner Functions ============

    /**
     * @notice Add AI executor address
     */
    function addAIExecutor(address executor) external onlyOwner {
        require(executor != address(0), "Invalid address");
        aiExecutors[executor] = true;
        emit AIExecutorAdded(executor);
    }

    /**
     * @notice Remove AI executor address
     */
    function removeAIExecutor(address executor) external onlyOwner {
        aiExecutors[executor] = false;
        emit AIExecutorRemoved(executor);
    }

    /**
     * @notice Emergency pause all operations
     */
    function emergencyPause() external onlyOwner {
        paused = true;
        emit EmergencyPauseTriggered(msg.sender);
    }

    /**
     * @notice Lift emergency pause
     */
    function liftPause() external onlyOwner {
        paused = false;
        emit EmergencyPauseLifted(msg.sender);
    }

    /**
     * @notice Transfer ownership
     */
    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "Invalid address");
        owner = newOwner;
    }

    // ============ View Functions ============

    /**
     * @notice Get full config for a user
     */
    function getConfig(address user) external view returns (UserProtectionConfig memory) {
        return userConfigs[user];
    }

    /**
     * @notice Check if user has active protection
     */
    function isProtected(address user) external view returns (bool) {
        UserProtectionConfig memory config = userConfigs[user];
        return config.registrationTime > 0 && config.isActive;
    }

    /**
     * @notice Check if address is authorized AI executor
     */
    function isAIExecutor(address addr) external view returns (bool) {
        return aiExecutors[addr];
    }

    /**
     * @notice Get user's hourly execution count
     */
    function getHourlyExecutionCount(address user, uint256 hour) external view returns (uint256) {
        return hourlyExecutionCount[user][hour];
    }
}
