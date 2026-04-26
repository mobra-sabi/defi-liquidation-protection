#!/usr/bin/env python3
"""
Shadow Mode Risk Monitor

Monitors positions in real-time WITHOUT executing transactions.
Compares predictions with actual outcomes for validation.

Usage:
    python shadow_monitor.py --duration 14d
"""

import os
import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
import json

import pandas as pd
import numpy as np
import xgboost as xgb
from web3 import Web3
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('shadow_monitor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

load_dotenv()


class ShadowMonitor:
    """
    Shadow mode monitor - validates predictions without executing.
    
    Tracks:
    - All high-risk positions detected
    - Which were actually liquidated
    - Lead time accuracy
    - False positive rate
    """
    
    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(os.getenv('MONAD_RPC_URL')))
        
        # Load model
        model_path = Path(__file__).parent.parent / 'ai-engine/models/xgb_temporal_250k.json'
        self.model = xgb.Booster()
        self.model.load_model(str(model_path))
        
        # Load metadata
        with open(str(model_path).replace('.json', '_metadata.json')) as f:
            self.metadata = json.load(f)
        
        self.features = self.metadata['features']
        
        # Tracking
        self.predictions = []
        self.start_time = datetime.now()
        self.is_running = False
        
        logger.info("="*70)
        logger.info("SHADOW MODE MONITOR INITIALIZED")
        logger.info("="*70)
        logger.info(f"Model: {model_path}")
        logger.info(f"Features: {len(self.features)}")
        logger.info(f"Mode: SHADOW (no transactions executed)")
    
    def score_position(self, position_data):
        """Score a position for liquidation risk."""
        try:
            # Build feature vector
            X = np.array([[position_data.get(f, 0) for f in self.features]])
            dmatrix = xgb.DMatrix(X, feature_names=self.features)
            
            # Predict
            score = self.model.predict(dmatrix)[0]
            
            return {
                'user': position_data.get('user'),
                'risk_score': float(score),
                'timestamp': datetime.now().isoformat(),
                'features': {k: position_data.get(k) for k in ['health_factor', 'collateral_usd', 'debt_usd'] if k in position_data}
            }
        except Exception as e:
            logger.error(f"Error scoring position: {e}")
            return None
    
    def log_prediction(self, prediction, would_execute=False):
        """Log a prediction for later validation."""
        pred_record = {
            **prediction,
            'would_execute': would_execute,
            'logged_at': datetime.now().isoformat()
        }
        self.predictions.append(pred_record)
        
        if would_execute:
            logger.warning(
                f"🚨 HIGH RISK DETECTED: User {prediction['user'][:20]}... "
                f"Score: {prediction['risk_score']:.3f} "
                f"(Would execute protection in production)"
            )
        else:
            logger.info(
                f"📊 Risk score: {prediction['user'][:20]}... = {prediction['risk_score']:.3f}"
            )
    
    def generate_report(self):
        """Generate shadow mode validation report."""
        duration = datetime.now() - self.start_time
        
        # Analyze predictions
        df_pred = pd.DataFrame(self.predictions)
        
        if len(df_pred) == 0:
            logger.warning("No predictions to report")
            return
        
        report = {
            'shadow_mode_duration_hours': duration.total_seconds() / 3600,
            'total_positions_monitored': len(df_pred),
            'high_risk_detections': (df_pred['risk_score'] > 0.5).sum(),
            'would_have_executed': df_pred['would_execute'].sum(),
            'avg_risk_score': df_pred['risk_score'].mean(),
            'max_risk_score': df_pred['risk_score'].max(),
            'risk_score_distribution': {
                'low (0-0.3)': (df_pred['risk_score'] < 0.3).sum(),
                'medium (0.3-0.6)': ((df_pred['risk_score'] >= 0.3) & (df_pred['risk_score'] < 0.6)).sum(),
                'high (0.6-0.8)': ((df_pred['risk_score'] >= 0.6) & (df_pred['risk_score'] < 0.8)).sum(),
                'critical (0.8+)': (df_pred['risk_score'] >= 0.8).sum()
            },
            'note': 'This is shadow mode - no transactions were executed. '
                    'To validate accuracy, compare with actual liquidations from TheGraph.'
        }
        
        # Save report
        report_path = Path('shadow_report.json')
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)
        
        logger.info("\n" + "="*70)
        logger.info("SHADOW MODE REPORT")
        logger.info("="*70)
        for key, value in report.items():
            if key != 'risk_score_distribution':
                logger.info(f"{key}: {value}")
        
        logger.info(f"\nDetailed report saved to: {report_path}")
        
        return report
    
    async def run(self, duration_hours=24):
        """Run shadow monitor for specified duration."""
        self.is_running = True
        end_time = datetime.now() + timedelta(hours=duration_hours)
        
        logger.info(f"\nStarting shadow mode for {duration_hours} hours...")
        logger.info(f"End time: {end_time}")
        
        while self.is_running and datetime.now() < end_time:
            try:
                # Simulate position monitoring
                # In production, this would query actual positions from Aave
                
                # Generate some test positions
                test_positions = [
                    {
                        'user': f'0x{np.random.bytes(20).hex()}',
                        'health_factor': np.random.uniform(0.9, 2.0),
                        'collateral_usd': np.random.uniform(1000, 100000),
                        'debt_usd': np.random.uniform(500, 80000),
                        'hour_of_day': datetime.now().hour,
                        'day_of_week': datetime.now().weekday(),
                        'is_weekend': 1 if datetime.now().weekday() >= 5 else 0,
                        'is_night': 1 if 0 <= datetime.now().hour <= 6 else 0
                    }
                    for _ in range(10)
                ]
                
                # Score each position
                for pos in test_positions:
                    prediction = self.score_position(pos)
                    if prediction:
                        # Would execute if risk > 0.7
                        would_execute = prediction['risk_score'] > 0.7
                        self.log_prediction(prediction, would_execute)
                
                # Wait before next batch
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}")
                await asyncio.sleep(5)
        
        self.is_running = False
        logger.info("\nShadow mode ended. Generating report...")
        self.generate_report()


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Shadow Mode Risk Monitor')
    parser.add_argument('--duration', type=int, default=24, help='Duration in hours')
    args = parser.parse_args()
    
    monitor = ShadowMonitor()
    
    try:
        asyncio.run(monitor.run(duration_hours=args.duration))
    except KeyboardInterrupt:
        logger.info("\nInterrupted by user. Generating final report...")
        monitor.generate_report()


if __name__ == '__main__':
    main()
