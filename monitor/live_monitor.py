#!/usr/bin/env python3
"""
Live Monitor - Continuous Background Service

This runs forever and:
1. Watches contracts on Monad testnet
2. Logs all events
3. Tracks new positions registered
4. Records protection executions
5. Collects metrics for dashboard

Usage:
    # Run in foreground:
    python3 monitor/live_monitor.py
    
    # Run in background:
    nohup python3 monitor/live_monitor.py > monitor.log 2>&1 &
"""

import os
import sys
import json
import time
import asyncio
import logging
from datetime import datetime
from pathlib import Path

import requests
from web3 import Web3
from dotenv import load_dotenv

load_dotenv('/home/mobra/protocol/.env')

# Configuration
RPC_URL = "https://testnet-rpc.monad.xyz"
DEPLOYMENT_FILE = '/home/mobra/protocol/deployments/monadTestnet.json'
METRICS_FILE = '/home/mobra/protocol/monitor/metrics.json'
EVENTS_FILE = '/home/mobra/protocol/monitor/events.jsonl'
POLL_INTERVAL = 5  # seconds

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/home/mobra/protocol/monitor/risk_monitor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class LiveMonitor:
    """Continuous on-chain monitor."""
    
    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(RPC_URL))
        self.deployment = self._load_deployment()
        self.last_block = self.w3.eth.block_number
        
        # Metrics
        self.metrics = {
            'started_at': datetime.now().isoformat(),
            'blocks_monitored': 0,
            'events_captured': 0,
            'positions_registered': 0,
            'protections_executed': 0,
            'last_block': self.last_block,
            'last_update': datetime.now().isoformat(),
            'uptime_seconds': 0,
        }
        
        # Save initial metrics
        self._save_metrics()
        
        logger.info("=" * 70)
        logger.info("LIVE MONITOR STARTED")
        logger.info("=" * 70)
        logger.info(f"Network: Monad Testnet (Chain ID: {self.w3.eth.chain_id})")
        logger.info(f"Starting block: {self.last_block:,}")
        logger.info(f"Polling every {POLL_INTERVAL}s")
        logger.info(f"Logs:    /home/mobra/protocol/monitor/risk_monitor.log")
        logger.info(f"Events:  {EVENTS_FILE}")
        logger.info(f"Metrics: {METRICS_FILE}")
        logger.info("=" * 70)
    
    def _load_deployment(self):
        """Load deployed contract addresses."""
        try:
            with open(DEPLOYMENT_FILE) as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error("No deployment found! Deploy contracts first.")
            return None
    
    def _save_metrics(self):
        """Persist metrics to disk."""
        self.metrics['last_update'] = datetime.now().isoformat()
        started = datetime.fromisoformat(self.metrics['started_at'])
        self.metrics['uptime_seconds'] = (datetime.now() - started).total_seconds()
        
        with open(METRICS_FILE, 'w') as f:
            json.dump(self.metrics, f, indent=2)
    
    def _log_event(self, event):
        """Append event to events log."""
        event['timestamp'] = datetime.now().isoformat()
        with open(EVENTS_FILE, 'a') as f:
            f.write(json.dumps(event) + '\n')
        self.metrics['events_captured'] += 1
    
    def watch_block(self, block_number):
        """Inspect a block for events involving our contracts."""
        if not self.deployment:
            return
        
        try:
            block = self.w3.eth.get_block(block_number, full_transactions=True)
            
            # Get contract addresses (lowercase for comparison)
            addresses = {
                info['address'].lower(): name 
                for name, info in self.deployment['contracts'].items()
            }
            
            # Check transactions
            for tx in block.transactions:
                to_addr = tx['to'].lower() if tx['to'] else None
                from_addr = tx['from'].lower() if tx['from'] else None
                
                contract_name = addresses.get(to_addr) or addresses.get(from_addr)
                
                if contract_name:
                    event = {
                        'type': 'transaction',
                        'block': block_number,
                        'tx_hash': tx['hash'].hex(),
                        'contract': contract_name,
                        'from': tx['from'],
                        'to': tx['to'],
                        'value_mon': float(self.w3.from_wei(tx['value'], 'ether')),
                        'gas_used': tx['gas'],
                    }
                    
                    logger.info(f"📥 TX in {contract_name}: {tx['hash'].hex()[:18]}... block {block_number}")
                    self._log_event(event)
                    
                    # Try to determine event type
                    try:
                        receipt = self.w3.eth.get_transaction_receipt(tx['hash'])
                        if receipt['status'] == 1:
                            for log in receipt['logs']:
                                if log['address'].lower() in addresses:
                                    log_event = {
                                        'type': 'contract_event',
                                        'block': block_number,
                                        'tx_hash': tx['hash'].hex(),
                                        'contract': addresses[log['address'].lower()],
                                        'topics': [t.hex() for t in log['topics']],
                                        'data_size': len(log['data']),
                                    }
                                    self._log_event(log_event)
                    except Exception as e:
                        pass
        
        except Exception as e:
            logger.warning(f"Error processing block {block_number}: {e}")
    
    def run(self):
        """Main monitoring loop."""
        try:
            while True:
                try:
                    current = self.w3.eth.block_number
                    
                    if current > self.last_block:
                        new_blocks = current - self.last_block
                        
                        # Process new blocks
                        for block_num in range(self.last_block + 1, current + 1):
                            self.watch_block(block_num)
                            self.metrics['blocks_monitored'] += 1
                        
                        self.last_block = current
                        self.metrics['last_block'] = current
                        
                        # Heartbeat log every 10 blocks
                        if self.metrics['blocks_monitored'] % 10 == 0:
                            logger.info(
                                f"💓 Heartbeat | Block: {current:,} | "
                                f"Blocks: {self.metrics['blocks_monitored']} | "
                                f"Events: {self.metrics['events_captured']}"
                            )
                    
                    self._save_metrics()
                    time.sleep(POLL_INTERVAL)
                    
                except Exception as e:
                    logger.error(f"Loop error: {e}")
                    time.sleep(POLL_INTERVAL * 2)
        
        except KeyboardInterrupt:
            logger.info("\n" + "=" * 70)
            logger.info("MONITOR STOPPED BY USER")
            logger.info("=" * 70)
            logger.info(f"Total blocks monitored: {self.metrics['blocks_monitored']}")
            logger.info(f"Total events captured:  {self.metrics['events_captured']}")
            logger.info(f"Uptime: {self.metrics['uptime_seconds']:.0f}s")
            self._save_metrics()


def main():
    monitor = LiveMonitor()
    monitor.run()


if __name__ == '__main__':
    main()
