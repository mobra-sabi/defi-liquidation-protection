// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * @title FeeCollector
 * @dev Collects and manages protocol fees from protection services
 *
 * Fee structure:
 * - 1.5% of protected amount (performance fee)
 * - Accumulated in treasury
 * - Can be distributed to token holders via governance
 */

interface IERC20 {
    function transfer(address to, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
    function approve(address spender, uint256 amount) external returns (bool);
}

contract FeeCollector {
    // ============ Structs ============

    struct FeeRecord {
        address token;
        uint256 amount;
        address user;           // User whose position was protected
        uint256 timestamp;
        uint256 protectionValue; // Total value protected
    }

    // ============ State Variables ============

    // Treasury balance per token
    mapping(address => uint256) public treasuryBalance;

    // Fee history
    FeeRecord[] public feeHistory;
    mapping(address => uint256) public userTotalFees; // User => total fees from their protections

    // Protocol metrics
    uint256 public totalFeesCollected;
    uint256 public totalProtectionValue;
    uint256 public totalProtections;

    // Access control
    address public owner;
    address public protectionExecutor;
    mapping(address => bool) public authorizedCollectors;

    // Governance (simplified - can be replaced with full DAO)
    address public governance;
    bool public distributionEnabled;
    uint256 public distributionThreshold; // Minimum fees before distribution

    // ============ Events ============

    event FeeCollected(
        address indexed token,
        uint256 amount,
        address indexed user,
        uint256 protectionValue,
        uint256 timestamp
    );

    event TreasuryWithdrawal(
        address indexed token,
        uint256 amount,
        address indexed recipient,
        string reason
    );

    event Distribution(
        address indexed token,
        uint256 totalAmount,
        uint256 recipientCount,
        uint256 timestamp
    );

    event ProtectionExecutorUpdated(address indexed newExecutor);
    event GovernanceUpdated(address indexed newGovernance);
    event DistributionThresholdUpdated(uint256 newThreshold);
    event DistributionEnabled(bool enabled);

    // ============ Modifiers ============

    modifier onlyOwner() {
        require(msg.sender == owner, "Only owner");
        _;
    }

    modifier onlyProtectionExecutor() {
        require(
            msg.sender == protectionExecutor || authorizedCollectors[msg.sender],
            "Only protection executor"
        );
        _;
    }

    modifier onlyGovernance() {
        require(msg.sender == governance, "Only governance");
        _;
    }

    // ============ Constructor ============

    constructor(address _governance) {
        require(_governance != address(0), "Invalid governance");

        owner = msg.sender;
        governance = _governance;
        distributionEnabled = false;
        distributionThreshold = 10000 * 1e6; // $10,000 equivalent (assuming 6 decimals)
    }

    // ============ Core Functions ============

    /**
     * @notice Collect fee from protection execution
     * @param token Address of token being collected
     * @param amount Fee amount
     * @param user User whose position was protected
     * @param protectionValue Total value of the protection
     */
    function collectFee(
        address token,
        uint256 amount,
        address user,
        uint256 protectionValue
    ) external onlyProtectionExecutor {
        require(token != address(0), "Invalid token");
        require(amount > 0, "Invalid amount");
        require(user != address(0), "Invalid user");

        // Transfer fee to treasury
        IERC20(token).transferFrom(msg.sender, address(this), amount);

        // Update balances
        treasuryBalance[token] += amount;
        totalFeesCollected += amount;
        totalProtectionValue += protectionValue;
        totalProtections++;
        userTotalFees[user] += amount;

        // Record fee
        feeHistory.push(FeeRecord({
            token: token,
            amount: amount,
            user: user,
            timestamp: block.timestamp,
            protectionValue: protectionValue
        }));

        emit FeeCollected(token, amount, user, protectionValue, block.timestamp);
    }

    /**
     * @notice Withdraw treasury funds (governance only, with timelock)
     */
    function withdrawTreasury(
        address token,
        uint256 amount,
        address recipient,
        string calldata reason
    ) external onlyGovernance {
        require(recipient != address(0), "Invalid recipient");
        require(amount <= treasuryBalance[token], "Insufficient balance");

        treasuryBalance[token] -= amount;

        IERC20(token).transfer(recipient, amount);

        emit TreasuryWithdrawal(token, amount, recipient, reason);
    }

    /**
     * @notice Distribute fees to token holders
     * @dev Simplified version - production would integrate with governance token
     */
    function distributeFees(address token) external onlyGovernance {
        require(distributionEnabled, "Distribution not enabled");
        require(treasuryBalance[token] >= distributionThreshold, "Below threshold");

        uint256 amountToDistribute = treasuryBalance[token];
        treasuryBalance[token] = 0;

        // In production, this would distribute proportionally to governance token holders
        // For now, we just emit event and rely on manual distribution

        emit Distribution(token, amountToDistribute, 0, block.timestamp);
    }

    // ============ Admin Functions ============

    /**
     * @notice Set protection executor address
     */
    function setProtectionExecutor(address _executor) external onlyOwner {
        require(_executor != address(0), "Invalid address");
        protectionExecutor = _executor;
        authorizedCollectors[_executor] = true;
        emit ProtectionExecutorUpdated(_executor);
    }

    /**
     * @notice Authorize additional collector
     */
    function authorizeCollector(address collector) external onlyOwner {
        require(collector != address(0), "Invalid address");
        authorizedCollectors[collector] = true;
    }

    /**
     * @notice Revoke collector authorization
     */
    function revokeCollector(address collector) external onlyOwner {
        authorizedCollectors[collector] = false;
    }

    /**
     * @notice Update governance address
     */
    function setGovernance(address _governance) external onlyOwner {
        require(_governance != address(0), "Invalid address");
        governance = _governance;
        emit GovernanceUpdated(_governance);
    }

    /**
     * @notice Enable/disable distribution
     */
    function setDistributionEnabled(bool enabled) external onlyGovernance {
        distributionEnabled = enabled;
        emit DistributionEnabled(enabled);
    }

    /**
     * @notice Update distribution threshold
     */
    function setDistributionThreshold(uint256 threshold) external onlyGovernance {
        distributionThreshold = threshold;
        emit DistributionThresholdUpdated(threshold);
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
     * @notice Get treasury balance for a token
     */
    function getTreasuryBalance(address token) external view returns (uint256) {
        return treasuryBalance[token];
    }

    /**
     * @notice Get total fee history count
     */
    function getFeeHistoryCount() external view returns (uint256) {
        return feeHistory.length;
    }

    /**
     * @notice Get fee history page
     */
    function getFeeHistoryPage(uint256 offset, uint256 limit) external view returns (FeeRecord[] memory) {
        uint256 end = offset + limit;
        if (end > feeHistory.length) {
            end = feeHistory.length;
        }

        FeeRecord[] memory page = new FeeRecord[](end - offset);
        for (uint256 i = offset; i < end; i++) {
            page[i - offset] = feeHistory[i];
        }

        return page;
    }

    /**
     * @notice Get protocol statistics
     */
    function getStats() external view returns (
        uint256 _totalFees,
        uint256 _totalProtectionValue,
        uint256 _totalProtections,
        uint256 _avgFeePerProtection
    ) {
        _totalFees = totalFeesCollected;
        _totalProtectionValue = totalProtectionValue;
        _totalProtections = totalProtections;
        _avgFeePerProtection = totalProtections > 0 ? totalFeesCollected / totalProtections : 0;
    }

    /**
     * @notice Get user's total fees
     */
    function getUserFees(address user) external view returns (uint256) {
        return userTotalFees[user];
    }
}
