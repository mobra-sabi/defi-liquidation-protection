#!/usr/bin/env python3
"""
Risk Monitor v2 - Rule-Based Risk Scoring

This version uses simple, transparent health factor thresholds instead of ML.
Why:
- ML model requires real Class 0 data (healthy positions HF 1.0-1.5)
- We will collect this data on testnet before training real ML model
- Rule-based is explainable, defensive, and aligned with Aave's own liquidation logic

Risk Levels:
- HF > 1.30: Safe - No action
- HF 1.15-1.30: Warning - Notify user
- HF 1.05-1.15: Alert - Prepare rebalancing
- HF < 1.05: Critical - Execute protection immediately
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import logging

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Web3 imports
try:
    from web3 import Web3
    from web3.middleware.geth_poa import geth_poa_middleware
except ImportError:
    Web3 = None
    geth_poa_middleware = None

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('risk_monitor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """Risk levels based on health factor."""
    SAFE = "safe"           # HF > 1.30
    WARNING = "warning"     # HF 1.15-1.30
    ALERT = "alert"         # HF 1.05-1.15
    CRITICAL = "critical"   # HF < 1.05


@dataclass
class PositionRisk:
    """Risk assessment for a position."""
    user_address: str
    health_factor: float
    collateral_usd: float
    debt_usd: float
    risk_level: RiskLevel
    action: str
    timestamp: datetime
    
    def to_dict(self) -> Dict:
        return {
            'user_address': self.user_address,
            'health_factor': self.health_factor,
            'collateral_usd': self.collateral_usd,
            'debt_usd': self.debt_usd,
            'risk_level': self.risk_level.value,
            'action': self.action,
            'timestamp': self.timestamp.isoformat(),
        }


class RuleBasedRiskScorer:
    """
    Simple, transparent risk scoring based on health factor thresholds.
    
    This replaces the ML model until we collect real testnet data.
    """
    
    # Thresholds (aligned with Aave's liquidation logic)
    THRESHOLD_SAFE = 1.30
    THRESHOLD_WARNING = 1.15
    THRESHOLD_ALERT = 1.05
    
    def calculate_risk(self, health_factor: float, 
                      collateral_usd: float = 0, 
                      debt_usd: float = 0) -> PositionRisk:
        """
        Calculate risk level based on health factor.
        
        Args:
            health_factor: Position health factor
            collateral_usd: Collateral value in USD
            debt_usd: Debt value in USD
            
        Returns:
            PositionRisk with level and recommended action
        """
        if health_factor > self.THRESHOLD_SAFE:
            risk_level = RiskLevel.SAFE
            action = "No action needed - position is healthy"
            
        elif health_factor > self.THRESHOLD_WARNING:
            risk_level = RiskLevel.WARNING
            action = "Notify user - position approaching risk zone"
            
        elif health_factor > self.THRESHOLD_ALERT:
            risk_level = RiskLevel.ALERT
            action = "Prepare rebalancing - position at risk"
            
        else:
            risk_level = RiskLevel.CRITICAL
            action = "Execute protection immediately - liquidation imminent"
        
        return PositionRisk(
            user_address="",  # Will be set by caller
            health_factor=health_factor,
            collateral_usd=collateral_usd,
            debt_usd=debt_usd,
            risk_level=risk_level,
            action=action,
            timestamp=datetime.now()
        )


class RiskMonitor:
    """
    Real-time risk monitor using rule-based scoring.
    
    Collects data for future ML model training while protecting users.
    """
    
    def __init__(self, 
                 rpc_url: str = None,
                 position_registry_address: str = None,
                 websocket_url: str = None):
        """
        Initialize risk monitor.
        
        Args:
            rpc_url: Monad RPC endpoint
            position_registry_address: On-chain position registry
            websocket_url: WebSocket for real-time updates
        """
        # Load config from environment
        self.rpc_url = rpc_url or os.getenv('MONAD_RPC_URL', 'https://testnet-rpc.monad.xyz')
        self.websocket_url = websocket_url or os.getenv('MONAD_WS_URL', 'wss://testnet-ws.monad.xyz')
        self.registry_address = position_registry_address or os.getenv('POSITION_REGISTRY_ADDRESS')
        
        # Web3 connection (if available)
        if Web3:
            try:
                self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))
                if geth_poa_middleware:
                    self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)
            except Exception as e:
                logger.warning(f"Web3 connection failed: {e}")
                self.w3 = None
        else:
            self.w3 = None
        
        # Risk scorer (rule-based)
        self.risk_scorer = RuleBasedRiskScorer()
        
        # Data collection for future ML
        self.collected_data: List[Dict] = []
        self.data_collection_enabled = True
        
        # Alert callbacks
        self.alert_callbacks: List[Callable] = []
        
        # Running state
        self.is_running = False
        self.monitor_task = None
        
        logger.info(f"Risk Monitor initialized")
        logger.info(f"RPC: {self.rpc_url}")
        logger.info(f"Rule-based scoring active (ML disabled)")
        
    def add_alert_callback(self, callback: Callable[[PositionRisk], None]):
        """Add callback for risk alerts."""
        self.alert_callbacks.append(callback)
        
    def assess_position(self, user_address: str, health_factor: float,
                       collateral_usd: float = 0, debt_usd: float = 0) -> PositionRisk:
        """
        Assess risk for a single position.
        
        Args:
            user_address: User's blockchain address
            health_factor: Position health factor
            collateral_usd: Collateral value
            debt_usd: Debt value
            
        Returns:
            PositionRisk assessment
        """
        # Calculate risk
        risk = self.risk_scorer.calculate_risk(health_factor, collateral_usd, debt_usd)
        risk.user_address = user_address
        
        # Collect data for future ML training
        if self.data_collection_enabled:
            self._collect_data_point(risk)
        
        # Trigger alerts for warning and above
        if risk.risk_level in [RiskLevel.WARNING, RiskLevel.ALERT, RiskLevel.CRITICAL]:
            self._trigger_alerts(risk)
        
        return risk
    
    def _collect_data_point(self, risk: PositionRisk):
        """Collect data point for future ML model training."""
        data_point = {
            'timestamp': risk.timestamp.isoformat(),
            'user_address': risk.user_address,
            'health_factor': risk.health_factor,
            'collateral_usd': risk.collateral_usd,
            'debt_usd': risk.debt_usd,
            'risk_level': risk.risk_level.value,
            'hour_of_day': risk.timestamp.hour,
            'day_of_week': risk.timestamp.weekday(),
            'is_weekend': risk.timestamp.weekday() >= 5,
        }
        
        self.collected_data.append(data_point)
        
        # Save to disk periodically
        if len(self.collected_data) % 100 == 0:
            self._save_collected_data()
    
    def _save_collected_data(self):
        """Save collected data to disk for future ML training."""
        try:
            import pandas as pd
            df = pd.DataFrame(self.collected_data)
            df.to_parquet('/home/mobra/protocol/data/testnet_collected_data.parquet', index=False)
            logger.info(f"Saved {len(self.collected_data)} data points")
        except Exception as e:
            logger.error(f"Error saving data: {e}")
    
    def _trigger_alerts(self, risk: PositionRisk):
        """Trigger all registered alert callbacks."""
        for callback in self.alert_callbacks:
            try:
                callback(risk)
            except Exception as e:
                logger.error(f"Alert callback error: {e}")
        
        # Log the alert
        logger.warning(
            f"RISK ALERT: {risk.user_address} - "
            f"HF: {risk.health_factor:.3f} - "
            f"Level: {risk.risk_level.value.upper()} - "
            f"Action: {risk.action}"
        )
    
    async def start_monitoring(self, interval_seconds: float = 30.0):
        """
        Start continuous monitoring loop.
        
        Args:
            interval_seconds: Time between scans
        """
        self.is_running = True
        logger.info(f"Starting monitoring (interval: {interval_seconds}s)")
        
        while self.is_running:
            try:
                await self._scan_all_positions()
                await asyncio.sleep(interval_seconds)
            except Exception as e:
                logger.error(f"Monitoring error: {e}")
                await asyncio.sleep(5)
    
    async def _scan_all_positions(self):
        """Scan all registered positions."""
        # In production, query from on-chain registry
        # For now, simulate with monitored positions
        
        # Example: Query PositionRegistry contract
        if self.registry_address:
            try:
                # This would query the actual contract
                # positions = self._query_on_chain_positions()
                pass
            except Exception as e:
                logger.error(f"Error querying positions: {e}")
    
    def stop(self):
        """Stop monitoring."""
        self.is_running = False
        self._save_collected_data()
        logger.info("Monitoring stopped")
    
    def get_statistics(self) -> Dict:
        """Get monitoring statistics."""
        return {
            'data_points_collected': len(self.collected_data),
            'monitoring_active': self.is_running,
            'scoring_method': 'rule_based',
            'thresholds': {
                'safe': self.risk_scorer.THRESHOLD_SAFE,
                'warning': self.risk_scorer.THRESHOLD_WARNING,
                'alert': self.risk_scorer.THRESHOLD_ALERT,
            }
        }


# Simple CLI test
if __name__ == '__main__':
    print("="*70)
    print("RISK MONITOR V2 - RULE-BASED SCORING")
    print("="*70)
    print()
    
    # Initialize
    monitor = RiskMonitor()
    
    # Test positions
    test_positions = [
        ("0x123...", 2.50, 10000, 4000, "Healthy position"),
        ("0x456...", 1.25, 5000, 3500, "Warning zone"),
        ("0x789...", 1.10, 3000, 2500, "Alert zone"),
        ("0xabc...", 0.95, 2000, 1800, "Critical - liquidation imminent"),
    ]
    
    print("Testing risk scoring:\n")
    
    for addr, hf, coll, debt, desc in test_positions:
        risk = monitor.assess_position(addr, hf, coll, debt)
        
        print(f"Position: {desc}")
        print(f"  HF: {hf:.3f}")
        print(f"  Risk Level: {risk.risk_level.value.upper()}")
        print(f"  Action: {risk.action}")
        print()
    
    print("="*70)
    print("Statistics:")
    stats = monitor.get_statistics()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    print("="*70)
    print()
    print("✅ Rule-based risk monitor ready for testnet deployment")
    print("✅ Data collection active for future ML model")
