// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "./PositionRegistry.sol";

/**
 * @title ProtectionExecutor
 * @dev Executes protective rebalancing actions for users
 *
 * This contract:
 * 1. Receives execution calls from AI executor
 * 2. Validates all parameters
 * 3. Executes swaps and debt repayment via DEX
 * 4. Ensures circuit breaker limits are respected
 * 5. Emits detailed events for monitoring
 */

interface IAavePool {
    function getUserAccountData(address user) external view returns (
        uint256 totalCollateralBase,
        uint256 totalDebtBase,
        uint256 availableBorrowsBase,
        uint256 currentLiquidationThreshold,
        uint256 ltv,
        uint256 healthFactor
    );

    function repay(
        address asset,
        uint256 amount,
        uint256 interestRateMode,
        address onBehalfOf
    ) external returns (uint256);

    function withdraw(
        address asset,
        uint256 amount,
        address to
    ) external returns (uint256);
}

interface IDEXRouter {
    function swapExactTokensForTokens(
        uint256 amountIn,
        uint256 amountOutMin,
        address[] calldata path,
        address to,
        uint256 deadline
    ) external returns (uint256[] memory amounts);
}

interface IERC20 {
    function approve(address spender, uint256 amount) external returns (bool);
    function allowance(address owner, address spender) external view returns (uint256);
    function balanceOf(address account) external view returns (uint256);
    function decimals() external view returns (uint8);
}

contract ProtectionExecutor {
    // ============ State Variables ============

    PositionRegistry public registry;
    address public owner;
    address public feeCollector;

    // Fee percentage (1.5% = 150 basis points)
    uint256 public constant FEE_BASIS_POINTS = 150;
    uint256 public constant BASIS_POINTS_DIVISOR = 10000;

    // Emergency pause
    bool public paused;

    // ============ Events ============

    event ProtectionActionExecuted(
        address indexed user,
        address indexed protocol,
        uint256 collateralAmount,
        address collateralAsset,
        uint256 debtRepaid,
        address debtAsset,
        uint256 feeAmount,
        uint256 healthFactorBefore,
        uint256 healthFactorAfter,
        uint256 timestamp
    );

    event SwapExecuted(
        address indexed user,
        address tokenIn,
        address tokenOut,
        uint256 amountIn,
        uint256 amountOut
    );

    event ExecutionFailed(
        address indexed user,
        string reason,
        uint256 timestamp
    );

    event FeeCollectorUpdated(address indexed newFeeCollector);
    event EmergencyPauseTriggered(address indexed triggeredBy);
    event EmergencyPauseLifted(address indexed triggeredBy);

    // ============ Modifiers ============

    modifier onlyOwner() {
        require(msg.sender == owner, "Only owner");
        _;
    }

    modifier onlyAIExecutor() {
        require(registry.isAIExecutor(msg.sender), "Only AI executor");
        _;
    }

    modifier whenNotPaused() {
        require(!paused, "Contract paused");
        _;
    }

    // ============ Constructor ============

    constructor(address _registry, address _feeCollector) {
        require(_registry != address(0), "Invalid registry");
        require(_feeCollector != address(0), "Invalid fee collector");

        registry = PositionRegistry(_registry);
        feeCollector = _feeCollector;
        owner = msg.sender;
        paused = false;
    }

    // ============ Core Execution Function ============

    /**
     * @notice Execute protection for a user
     * @param user Address of the user to protect
     * @param collateralAsset Address of collateral token to sell
     * @param debtAsset Address of debt token to repay
     * @param collateralAmount Amount of collateral to sell
     * @param minDebtRepaid Minimum amount of debt to receive (slippage protection)
     * @param swapPath DEX swap path
     */
    function executeProtection(
        address user,
        address collateralAsset,
        address debtAsset,
        uint256 collateralAmount,
        uint256 minDebtRepaid,
        address[] calldata swapPath
    ) external onlyAIExecutor whenNotPaused {
        // 1. Validate user is registered and active
        PositionRegistry.UserProtectionConfig memory config = registry.getConfig(user);
        require(config.registrationTime > 0, "User not registered");
        require(config.isActive, "Protection not active");

        // 2. Check circuit breaker
        require(!registry.checkCircuitBreaker(user), "Circuit breaker active");

        // 3. Validate collateral amount within limits
        require(collateralAmount > 0, "Invalid amount");

        // Get current position data
        IAavePool pool = IAavePool(config.lendingProtocol);
        (
            uint256 totalCollateral,
            uint256 totalDebt,
            ,
            ,
            ,
            uint256 healthFactorBefore
        ) = pool.getUserAccountData(user);

        require(healthFactorBefore < config.triggerHealthFactor, "HF above trigger");

        // Calculate max allowed collateral to sell
        uint256 maxCollateral = (totalCollateral * config.maxRebalancePercent) / 100;
        require(collateralAmount <= maxCollateral, "Exceeds max rebalance %");

        // 4. Execute swap
        uint256 debtRepaid = _executeSwap(
            user,
            collateralAsset,
            debtAsset,
            collateralAmount,
            minDebtRepaid,
            swapPath
        );

        // 5. Calculate and collect fee
        uint256 feeAmount = (debtRepaid * FEE_BASIS_POINTS) / BASIS_POINTS_DIVISOR;
        uint256 netDebtRepaid = debtRepaid - feeAmount;

        // 6. Repay debt
        _repayDebt(user, debtAsset, netDebtRepaid);

        // 7. Collect fee
        _collectFee(debtAsset, feeAmount);

        // 8. Record execution in registry
        (
            uint256 totalCollateralAfter,
            uint256 totalDebtAfter,
            ,
            ,
            ,
            uint256 healthFactorAfter
        ) = pool.getUserAccountData(user);

        registry.recordExecution(user, collateralAmount, netDebtRepaid, healthFactorAfter);

        // 9. Emit event
        emit ProtectionActionExecuted(
            user,
            config.lendingProtocol,
            collateralAmount,
            collateralAsset,
            netDebtRepaid,
            debtAsset,
            feeAmount,
            healthFactorBefore,
            healthFactorAfter,
            block.timestamp
        );
    }

    // ============ Internal Functions ============

    function _executeSwap(
        address user,
        address collateralAsset,
        address debtAsset,
        uint256 collateralAmount,
        uint256 minDebtRepaid,
        address[] calldata swapPath
    ) internal returns (uint256) {
        // Approve DEX to spend collateral (user must have approved this contract)
        IERC20(collateralAsset).approve(swapPath[0], collateralAmount);

        // Execute swap (this is simplified - real implementation would use actual DEX)
        // In production, this would call Uniswap/SushiSwap/etc router
        uint256 deadline = block.timestamp + 300; // 5 min deadline

        // For now, simulate swap result
        // In production: IDEXRouter(swapPath[0]).swapExactTokensForTokens(...)
        uint256 receivedAmount = minDebtRepaid; // Simplified

        emit SwapExecuted(user, collateralAsset, debtAsset, collateralAmount, receivedAmount);

        return receivedAmount;
    }

    function _repayDebt(address user, address debtAsset, uint256 amount) internal {
        // Approve Aave to spend debt tokens
        IERC20(debtAsset).approve(address(registry.getConfig(user).lendingProtocol), amount);

        // Repay debt
        IAavePool(registry.getConfig(user).lendingProtocol).repay(
            debtAsset,
            amount,
            2, // Variable interest rate mode
            user
        );
    }

    function _collectFee(address asset, uint256 amount) internal {
        // Transfer fee to fee collector
        IERC20(asset).approve(feeCollector, amount);
        // In production: safeTransfer to feeCollector
    }

    // ============ Owner Functions ============

    /**
     * @notice Update fee collector address
     */
    function updateFeeCollector(address newFeeCollector) external onlyOwner {
        require(newFeeCollector != address(0), "Invalid address");
        feeCollector = newFeeCollector;
        emit FeeCollectorUpdated(newFeeCollector);
    }

    /**
     * @notice Emergency pause
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
     * @notice Update position registry
     */
    function updateRegistry(address newRegistry) external onlyOwner {
        require(newRegistry != address(0), "Invalid address");
        registry = PositionRegistry(newRegistry);
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
     * @notice Calculate fee for a given amount
     */
    function calculateFee(uint256 amount) external pure returns (uint256) {
        return (amount * FEE_BASIS_POINTS) / BASIS_POINTS_DIVISOR;
    }

    /**
     * @notice Check if execution is possible
     */
    function canExecute(address user) external view returns (bool) {
        if (paused) return false;

        PositionRegistry.UserProtectionConfig memory config = registry.getConfig(user);
        if (config.registrationTime == 0 || !config.isActive) return false;
        if (registry.checkCircuitBreaker(user)) return false;

        return true;
    }
}
