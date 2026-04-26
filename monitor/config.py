"""
Risk Monitor Configuration

NOTE ON ML MODEL:
- XGBoost ML model is currently DISABLED
- Using rule-based risk scoring (health factor thresholds)
- ML will be enabled after collecting real testnet data
- Backup ML model: risk_monitor_ml_backup.py
"""

# Scoring Method
# Options: 'rule_based' (current) | 'ml_xgboost' (future)
SCORING_METHOD = 'rule_based'

# ML Model Settings (for future use)
ML_MODEL_PATH = '/home/mobra/protocol/ai-engine/aave_real_model.json'
ML_ENABLED = False  # Will be enabled after testnet data collection

# Risk Thresholds (Rule-Based)
# Aligned with Aave's liquidation mechanism
RISK_THRESHOLDS = {
    'safe': 1.30,      # HF > 1.30 - No action
    'warning': 1.15,   # HF 1.15-1.30 - Notify user
    'alert': 1.05,     # HF 1.05-1.15 - Prepare rebalancing
    'critical': 1.00,  # HF < 1.05 - Execute protection
}

# Data Collection for Future ML
COLLECT_DATA_FOR_ML = True
ML_DATA_PATH = '/home/mobra/protocol/data/testnet_collected_data.parquet'

# Monitoring Settings
MONITOR_INTERVAL_SECONDS = 30
BATCH_SIZE = 100
MAX_POSITIONS = 10000

# Blockchain Settings
MONAD_RPC_URL = 'https://testnet-rpc.monad.xyz'
MONAD_WS_URL = 'wss://testnet-ws.monad.xyz'
CHAIN_ID = 10143  # Monad Testnet

# Contract Addresses (to be filled after deploy)
POSITION_REGISTRY_ADDRESS = None
PROTECTION_EXECUTOR_ADDRESS = None
FEE_COLLECTOR_ADDRESS = None

# Alert Settings
ALERT_WEBHOOK_URL = None
ALERT_EMAIL = None
ALERT_DISCORD_WEBHOOK = None

# Feature Flags
ENABLE_PROTECTION_EXECUTION = False  # Start in shadow mode
ENABLE_REAL_TRANSACTIONS = False     # Testnet only
LOG_LEVEL = 'INFO'
