#!/usr/bin/env python3
"""
Risk Monitor - Real-time DeFi Position Monitoring

Monitors user positions on Aave/Morpho, calculates risk scores using AI models,
and triggers protective actions when liquidation risk is detected.

Architecture:
- WebSocket connection to Monad blockchain
- Batched position updates (multicall)
- Async processing pipeline
- GPU-accelerated risk scoring
- Internal queue for high-risk positions

Hardware allocation:
- GPU 1 (RTX 3080): XGBoost risk scoring
- GPU 2 (RTX 3080): Anomaly detection and secondary checks

Usage:
    python risk_monitor.py --config config.yaml
"""

import os
import sys
import json
import asyncio
import logging
import signal
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import websockets
from web3 import Web3
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('risk_monitor.log')
    ]
)
logger = logging.getLogger(__name__)

load_dotenv()

# Configuration
MONITOR_DIR = Path(__file__).parent
DATA_DIR = MONITOR_DIR.parent / 'data'
AI_ENGINE_DIR = MONITOR_DIR.parent / 'ai-engine'


@dataclass
class Position:
    """Represents a user position on a lending protocol."""
    user_address: str
    protocol_address: str
    health_factor: float
    total_collateral_usd: float
    total_debt_usd: float
    available_borrows_usd: float
    current_ltv: float
    liquidation_threshold: float
    last_update: datetime = field(default_factory=datetime.now)
    risk_score: float = 0.0
    assets: List[Dict] = field(default_factory=list)


@dataclass
class RiskAssessment:
    """Risk assessment result for a position."""
    user_address: str
    risk_score: float
    risk_level: str  # low, medium, high, critical
    predicted_liquidation_time: Optional[float]  # minutes
    recommended_action: str
    confidence: float
    timestamp: datetime = field(default_factory=datetime.now)


class BlockchainListener:
    """Listens to blockchain events via WebSocket."""

    def __init__(self, rpc_url: str):
        self.rpc_url = rpc_url
        self.w3 = Web3(Web3.WebsocketProvider(rpc_url))
        self.running = False
        self.block_callbacks = []

    async def start(self):
        """Start listening for new blocks."""
        logger.info(f"Connecting to blockchain at {self.rpc_url}...")

        if not self.w3.is_connected():
            logger.error("Failed to connect to blockchain")
            return

        logger.info("Connected to blockchain")
        self.running = True

        # Subscribe to new blocks
        subscription = self.w3.eth.subscribe('newBlocks')

        while self.running:
            try:
                message = await subscription.get()
                block_number = message['number']
                timestamp = message['timestamp']

                logger.debug(f"New block: {block_number}")

                # Notify callbacks
                for callback in self.block_callbacks:
                    asyncio.create_task(callback(block_number, timestamp))

            except Exception as e:
                logger.error(f"Error processing block: {e}")
                await asyncio.sleep(1)

    def on_block(self, callback):
        """Register a callback for new blocks."""
        self.block_callbacks.append(callback)

    async def stop(self):
        """Stop listening."""
        self.running = False


class PositionLoader:
    """Loads positions from the PositionRegistry contract."""

    def __init__(self, registry_address: str, w3: Web3):
        self.registry_address = registry_address
        self.w3 = w3
        self.active_positions: Dict[str, Position] = {}

        # Contract ABI (simplified)
        self.registry_abi = [
            {
                "inputs": [{"name": "user", "type": "address"}],
                "name": "getConfig",
                "outputs": [{
                    "components": [
                        {"name": "user", "type": "address"},
                        {"name": "lendingProtocol", "type": "address"},
                        {"name": "triggerHealthFactor", "type": "uint256"},
                        {"name": "targetHealthFactor", "type": "uint256"},
                        {"name": "maxRebalancePercent", "type": "uint256"},
                        {"name": "isActive", "type": "bool"},
                        {"name": "lastActionTimestamp", "type": "uint256"},
                        {"name": "totalExecutions", "type": "uint256"},
                        {"name": "registrationTime", "type": "uint256"}
                    ],
                    "name": "",
                    "type": "tuple"
                }],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [],
                "name": "getAllUsers",
                "outputs": [{"name": "", "type": "address[]"}],
                "stateMutability": "view",
                "type": "function"
            }
        ]

        self.registry = self.w3.eth.contract(
            address=registry_address,
            abi=self.registry_abi
        )

    async def load_all_positions(self) -> Dict[str, Position]:
        """Load all active positions from registry."""
        logger.info("Loading positions from registry...")

        try:
            # In production, this would query all registered users
            # For now, simulate with test data
            positions = {}

            # Add test positions
            test_addresses = self._get_test_addresses()

            for addr in test_addresses:
                # Simulate position data
                positions[addr] = Position(
                    user_address=addr,
                    protocol_address="0x794a61358D6845594F94dc1DB02A252b5b4814aD",  # Aave V3
                    health_factor=1.0 + np.random.random() * 0.5,  # 1.0 - 1.5
                    total_collateral_usd=100000 + np.random.random() * 900000,
                    total_debt_usd=50000 + np.random.random() * 400000,
                    available_borrows_usd=10000,
                    current_ltv=0.75,
                    liquidation_threshold=0.8,
                )

            self.active_positions = positions
            logger.info(f"Loaded {len(positions)} positions")
            return positions

        except Exception as e:
            logger.error(f"Failed to load positions: {e}")
            return {}

    def _get_test_addresses(self) -> List[str]:
        """Get test addresses for simulation."""
        return [
            f"0x{''.join(['1234567890abcdef'[i % 16] for i in range(40)])}"
            for _ in range(100)
        ]

    async def refresh_positions(self):
        """Refresh position data periodically."""
        while True:
            await self.load_all_positions()
            await asyncio.sleep(300)  # Refresh every 5 minutes


class AIScorer:
    """GPU-accelerated AI risk scoring."""

    def __init__(self, model_path: str, gpu_id: int = 1):
        self.model_path = model_path
        self.gpu_id = gpu_id
        self.model = None
        self.features = None
        self.load_model()

    def load_model(self):
        """Load XGBoost model."""
        try:
            import xgboost as xgb

            logger.info(f"Loading model from {self.model_path}...")
            self.model = xgb.Booster()
            self.model.load_model(self.model_path)

            # Load metadata
            metadata_path = self.model_path.replace('.json', '_metadata.json')
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)
                self.features = metadata['features']

            logger.info(f"Model loaded with {len(self.features)} features")

        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            self.model = None

    def score_positions(self, positions: List[Position]) -> List[RiskAssessment]:
        """Score multiple positions using GPU."""
        if not self.model:
            logger.warning("Model not loaded, returning default scores")
            return [
                RiskAssessment(
                    user_address=p.user_address,
                    risk_score=0.5,
                    risk_level="unknown",
                    predicted_liquidation_time=None,
                    recommended_action="monitor",
                    confidence=0.0
                )
                for p in positions
            ]

        try:
            import xgboost as xgb

            # Prepare features
            X = self._extract_features(positions)

            # Create DMatrix with GPU
            dmatrix = xgb.DMatrix(X, feature_names=self.features)

            # Predict on GPU
            scores = self.model.predict(dmatrix)

            # Convert to RiskAssessment
            assessments = []
            for i, position in enumerate(positions):
                risk_score = float(scores[i])

                # Determine risk level
                if risk_score < 0.3:
                    risk_level = "low"
                    action = "monitor"
                elif risk_score < 0.6:
                    risk_level = "medium"
                    action = "watch"
                elif risk_score < 0.8:
                    risk_level = "high"
                    action = "prepare"
                else:
                    risk_level = "critical"
                    action = "protect"

                assessments.append(RiskAssessment(
                    user_address=position.user_address,
                    risk_score=risk_score,
                    risk_level=risk_level,
                    predicted_liquidation_time=30.0 if risk_score > 0.6 else None,
                    recommended_action=action,
                    confidence=risk_score
                ))

            return assessments

        except Exception as e:
            logger.error(f"Error during scoring: {e}")
            return []

    def _extract_features(self, positions: List[Position]) -> np.ndarray:
        """Extract features from positions for model input."""
        features = []

        for p in positions:
            # Create feature vector
            feat = [
                p.health_factor,
                p.total_collateral_usd / 1e6,  # Normalize
                p.total_debt_usd / 1e6,
                p.available_borrows_usd / 1e6,
                p.current_ltv,
                p.liquidation_threshold,
                # Derived features
                p.total_debt_usd / max(p.total_collateral_usd, 1),  # Debt ratio
                p.liquidation_threshold - p.current_ltv,  # Buffer
            ]

            # Pad to expected feature count
            while len(feat) < len(self.features):
                feat.append(0.0)

            features.append(feat[:len(self.features)])

        return np.array(features)


class RiskQueue:
    """Priority queue for high-risk positions."""

    def __init__(self, max_size: int = 10000):
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=max_size)
        self.high_risk_users: Set[str] = set()
        self.risk_history: Dict[str, List[RiskAssessment]] = defaultdict(list)

    async def add_assessment(self, assessment: RiskAssessment):
        """Add a risk assessment to the queue."""
        try:
            # Keep history
            self.risk_history[assessment.user_address].append(assessment)

            # Keep only last 100 assessments per user
            if len(self.risk_history[assessment.user_address]) > 100:
                self.risk_history[assessment.user_address] = \
                    self.risk_history[assessment.user_address][-100:]

            # Add to queue if high risk
            if assessment.risk_level in ['high', 'critical']:
                await self.queue.put(assessment)
                self.high_risk_users.add(assessment.user_address)
                logger.warning(
                    f"High risk detected: {assessment.user_address[:10]}... "
                    f"Score: {assessment.risk_score:.3f}, Action: {assessment.recommended_action}"
                )

        except asyncio.QueueFull:
            logger.error("Risk queue full, dropping assessment")

    async def get_high_risk(self, timeout: float = 1.0) -> Optional[RiskAssessment]:
        """Get next high-risk assessment from queue."""
        try:
            return await asyncio.wait_for(self.queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    def get_user_risk_trend(self, user_address: str) -> Optional[str]:
        """Analyze risk trend for a user."""
        history = self.risk_history.get(user_address, [])
        if len(history) < 3:
            return None

        recent_scores = [h.risk_score for h in history[-10:]]
        if len(recent_scores) < 2:
            return None

        # Simple trend analysis
        avg_recent = np.mean(recent_scores[-3:])
        avg_older = np.mean(recent_scores[:-3]) if len(recent_scores) > 3 else avg_recent

        if avg_recent > avg_older + 0.1:
            return "increasing"
        elif avg_recent < avg_older - 0.1:
            return "decreasing"
        return "stable"


class RiskMonitor:
    """Main risk monitoring orchestrator."""

    def __init__(self):
        self.rpc_url = os.getenv('MONAD_WS_URL', 'wss://rpc.testnet.monad.xyz/ws')
        self.registry_address = os.getenv('POSITION_REGISTRY_ADDRESS', '')
        self.gpu_id = int(os.getenv('XGBOOST_GPU_ID', '1'))

        self.blockchain = BlockchainListener(self.rpc_url)
        self.w3 = Web3(Web3.WebsocketProvider(self.rpc_url))
        self.position_loader = PositionLoader(self.registry_address, self.w3)
        self.ai_scorer = AIScorer(
            str(AI_ENGINE_DIR / 'models' / 'xgb_liquidation_predictor_30min.json'),
            gpu_id=self.gpu_id
        )
        self.risk_queue = RiskQueue()

        self.running = False
        self.stats = {
            'positions_monitored': 0,
            'assessments_made': 0,
            'high_risk_detected': 0,
            'start_time': None
        }

    async def start(self):
        """Start the risk monitor."""
        logger.info("=" * 60)
        logger.info("RISK MONITOR STARTING")
        logger.info("=" * 60)

        self.running = True
        self.stats['start_time'] = datetime.now()

        # Initial position load
        await self.position_loader.load_all_positions()

        # Start tasks
        tasks = [
            asyncio.create_task(self._position_refresh_loop()),
            asyncio.create_task(self._risk_scoring_loop()),
            asyncio.create_task(self._queue_processor_loop()),
            asyncio.create_task(self._stats_loop()),
        ]

        logger.info("All monitoring loops started")

        # Wait for shutdown
        await self._wait_for_shutdown()

        # Cancel tasks
        for task in tasks:
            task.cancel()

    async def _position_refresh_loop(self):
        """Periodically refresh position data."""
        while self.running:
            try:
                await self.position_loader.refresh_positions()
            except Exception as e:
                logger.error(f"Position refresh error: {e}")
                await asyncio.sleep(60)

    async def _risk_scoring_loop(self):
        """Score positions using AI model."""
        while self.running:
            try:
                positions = list(self.position_loader.active_positions.values())

                if positions:
                    # Score in batches
                    batch_size = 256
                    for i in range(0, len(positions), batch_size):
                        batch = positions[i:i + batch_size]
                        assessments = self.ai_scorer.score_positions(batch)

                        for assessment in assessments:
                            await self.risk_queue.add_assessment(assessment)
                            self.stats['assessments_made'] += 1

                            if assessment.risk_level in ['high', 'critical']:
                                self.stats['high_risk_detected'] += 1

                self.stats['positions_monitored'] = len(positions)

                # Score every 12 seconds (roughly every block)
                await asyncio.sleep(12)

            except Exception as e:
                logger.error(f"Risk scoring error: {e}")
                await asyncio.sleep(12)

    async def _queue_processor_loop(self):
        """Process high-risk queue and trigger actions."""
        while self.running:
            try:
                assessment = await self.risk_queue.get_high_risk(timeout=1.0)

                if assessment:
                    # Log high risk
                    logger.warning(
                        f"🚨 PROTECTION NEEDED: {assessment.user_address[:20]}... "
                        f"| Score: {assessment.risk_score:.3f} "
                        f"| Action: {assessment.recommended_action}"
                    )

                    # In production, send to Execution Engine here
                    # await self.execution_engine.protect(assessment)

            except Exception as e:
                logger.error(f"Queue processing error: {e}")

    async def _stats_loop(self):
        """Print periodic statistics."""
        while self.running:
            try:
                await asyncio.sleep(60)  # Every minute

                uptime = datetime.now() - self.stats['start_time']
                logger.info("=" * 60)
                logger.info(f"MONITOR STATS (Uptime: {uptime})")
                logger.info(f"  Positions monitored: {self.stats['positions_monitored']}")
                logger.info(f"  Assessments made: {self.stats['assessments_made']}")
                logger.info(f"  High risk detected: {self.stats['high_risk_detected']}")
                logger.info(f"  Queue size: {self.risk_queue.queue.qsize()}")
                logger.info("=" * 60)

            except Exception as e:
                logger.error(f"Stats error: {e}")

    async def _wait_for_shutdown(self):
        """Wait for shutdown signal."""
        shutdown_event = asyncio.Event()

        def signal_handler(sig, frame):
            logger.info("Shutdown signal received")
            shutdown_event.set()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        await shutdown_event.wait()
        self.running = False

    def stop(self):
        """Stop the monitor."""
        self.running = False


async def main():
    """Main entry point."""
    monitor = RiskMonitor()
    await monitor.start()


if __name__ == '__main__':
    asyncio.run(main())
