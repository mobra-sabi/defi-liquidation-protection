#!/usr/bin/env python3
"""
Live Status Dashboard - Terminal View

Run this anytime to see what's happening with your protocol.

Usage:
    python3 monitor/status.py           # One-shot status
    python3 monitor/status.py --watch   # Auto-refresh every 10s
"""

import os
import sys
import json
import time
import argparse
from datetime import datetime
from pathlib import Path

try:
    from web3 import Web3
except ImportError:
    print("Installing web3...")
    os.system("pip install web3 -q")
    from web3 import Web3

import requests
from dotenv import load_dotenv

load_dotenv('/home/mobra/protocol/.env')

# Colors for terminal
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    END = '\033[0m'


# Configuration
RPC_URL = "https://testnet-rpc.monad.xyz"
EXPLORER_URL = "https://testnet.monadexplorer.com"
DEPLOYMENT_FILE = '/home/mobra/protocol/deployments/monadTestnet.json'
DATA_FILE = '/home/mobra/protocol/data/testnet_collected_data.parquet'


def clear_screen():
    """Clear terminal."""
    os.system('clear' if os.name == 'posix' else 'cls')


def print_header(title):
    """Print section header."""
    print(f"\n{Colors.CYAN}{'═' * 70}{Colors.END}")
    print(f"{Colors.CYAN}{Colors.BOLD}  {title}{Colors.END}")
    print(f"{Colors.CYAN}{'═' * 70}{Colors.END}")


def print_section(title):
    """Print subsection."""
    print(f"\n{Colors.BLUE}{Colors.BOLD}▸ {title}{Colors.END}")
    print(f"{Colors.DIM}{'─' * 70}{Colors.END}")


def status_dot(status):
    """Return colored status dot."""
    if status == 'active':
        return f"{Colors.GREEN}●{Colors.END}"
    elif status == 'warning':
        return f"{Colors.YELLOW}●{Colors.END}"
    elif status == 'error':
        return f"{Colors.RED}●{Colors.END}"
    else:
        return f"{Colors.DIM}○{Colors.END}"


def get_blockchain_status():
    """Get current blockchain state."""
    try:
        w3 = Web3(Web3.HTTPProvider(RPC_URL))
        if w3.is_connected():
            block = w3.eth.block_number
            chain_id = w3.eth.chain_id
            gas_price = w3.eth.gas_price
            return {
                'connected': True,
                'block': block,
                'chain_id': chain_id,
                'gas_price_gwei': w3.from_wei(gas_price, 'gwei')
            }
    except Exception as e:
        return {'connected': False, 'error': str(e)}
    return {'connected': False}


def get_wallet_status():
    """Get deployer wallet status."""
    try:
        address = os.getenv('EXECUTOR_ADDRESS')
        if not address:
            return None
        
        w3 = Web3(Web3.HTTPProvider(RPC_URL))
        balance = w3.eth.get_balance(address)
        nonce = w3.eth.get_transaction_count(address)
        
        return {
            'address': address,
            'balance_mon': float(w3.from_wei(balance, 'ether')),
            'tx_count': nonce
        }
    except Exception as e:
        return None


def get_contracts_status():
    """Get deployed contracts status."""
    try:
        with open(DEPLOYMENT_FILE) as f:
            deployment = json.load(f)
        
        w3 = Web3(Web3.HTTPProvider(RPC_URL))
        contracts = {}
        
        for name, info in deployment['contracts'].items():
            address = info['address']
            try:
                code = w3.eth.get_code(address)
                deployed = len(code) > 2  # More than '0x'
                balance = w3.eth.get_balance(address)
                contracts[name] = {
                    'address': address,
                    'deployed': deployed,
                    'balance_mon': float(w3.from_wei(balance, 'ether'))
                }
            except Exception as e:
                contracts[name] = {'address': address, 'error': str(e)}
        
        return {
            'network': deployment['network'],
            'chain_id': deployment['chainId'],
            'deployed_at': deployment['deploymentTime'],
            'contracts': contracts
        }
    except FileNotFoundError:
        return {'error': 'Deployment not found'}


def get_monitor_status():
    """Check if risk monitor is running."""
    try:
        # Check log file age
        log_file = '/home/mobra/protocol/monitor/risk_monitor.log'
        if os.path.exists(log_file):
            mtime = os.path.getmtime(log_file)
            age_seconds = time.time() - mtime
            return {
                'log_exists': True,
                'last_update_seconds': age_seconds,
                'log_size_kb': os.path.getsize(log_file) / 1024
            }
    except Exception as e:
        pass
    return {'log_exists': False}


def get_collected_data_stats():
    """Get statistics on collected testnet data."""
    try:
        if os.path.exists(DATA_FILE):
            import pandas as pd
            df = pd.read_parquet(DATA_FILE)
            return {
                'exists': True,
                'count': len(df),
                'columns': list(df.columns)[:5],
                'last_timestamp': df['timestamp'].max() if 'timestamp' in df.columns else None
            }
    except Exception as e:
        pass
    return {'exists': False}


def get_recent_transactions(address, limit=5):
    """Get recent transactions for address (using RPC)."""
    try:
        w3 = Web3(Web3.HTTPProvider(RPC_URL))
        latest = w3.eth.block_number
        # Look back 100 blocks
        start = max(0, latest - 100)
        
        txs = []
        for block_num in range(latest, start, -1):
            try:
                block = w3.eth.get_block(block_num, full_transactions=True)
                for tx in block.transactions:
                    if (tx['from'].lower() == address.lower() or 
                        (tx['to'] and tx['to'].lower() == address.lower())):
                        txs.append({
                            'hash': tx['hash'].hex(),
                            'block': block_num,
                            'from': tx['from'],
                            'to': tx['to'],
                            'value_mon': float(w3.from_wei(tx['value'], 'ether'))
                        })
                        if len(txs) >= limit:
                            return txs
            except:
                continue
        return txs
    except Exception as e:
        return []


def display_status():
    """Display complete status."""
    clear_screen()
    
    print_header("DEFI LIQUIDATION PROTECTION - LIVE STATUS")
    print(f"  {Colors.DIM}Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC{Colors.END}")
    
    # 1. Blockchain
    print_section("1. BLOCKCHAIN (Monad Testnet)")
    chain = get_blockchain_status()
    if chain.get('connected'):
        print(f"  {status_dot('active')} Connected to RPC")
        print(f"  {Colors.DIM}└── Block:     {chain['block']:,}")
        print(f"  └── Chain ID:  {chain['chain_id']}")
        print(f"  └── Gas Price: {chain['gas_price_gwei']:.1f} gwei{Colors.END}")
    else:
        print(f"  {status_dot('error')} Disconnected: {chain.get('error', 'Unknown error')}")
    
    # 2. Wallet
    print_section("2. EXECUTOR WALLET")
    wallet = get_wallet_status()
    if wallet:
        print(f"  {status_dot('active')} Wallet active")
        print(f"  {Colors.DIM}├── Address:    {wallet['address']}")
        balance_color = Colors.GREEN if wallet['balance_mon'] > 1 else Colors.YELLOW if wallet['balance_mon'] > 0.1 else Colors.RED
        print(f"  ├── Balance:    {balance_color}{wallet['balance_mon']:.4f} MON{Colors.END}")
        print(f"  {Colors.DIM}└── TX Count:   {wallet['tx_count']}{Colors.END}")
    else:
        print(f"  {status_dot('error')} No wallet configured")
    
    # 3. Contracts
    print_section("3. DEPLOYED CONTRACTS")
    contracts_info = get_contracts_status()
    if 'contracts' in contracts_info:
        print(f"  {Colors.DIM}Network: {contracts_info['network']}")
        print(f"  Deployed: {contracts_info['deployed_at']}{Colors.END}")
        print()
        for name, info in contracts_info['contracts'].items():
            if info.get('deployed'):
                print(f"  {status_dot('active')} {Colors.BOLD}{name}{Colors.END}")
                print(f"  {Colors.DIM}└── {info['address']}{Colors.END}")
                print(f"  {Colors.DIM}└── Explorer: {EXPLORER_URL}/address/{info['address']}{Colors.END}")
            else:
                print(f"  {status_dot('error')} {name}: NOT DEPLOYED")
    else:
        print(f"  {status_dot('error')} {contracts_info.get('error', 'Unknown')}")
    
    # 4. Risk Monitor
    print_section("4. RISK MONITOR")
    monitor = get_monitor_status()
    if monitor.get('log_exists'):
        age = monitor['last_update_seconds']
        if age < 60:
            print(f"  {status_dot('active')} {Colors.GREEN}Active{Colors.END} (last update {age:.0f}s ago)")
        elif age < 600:
            print(f"  {status_dot('warning')} {Colors.YELLOW}Idle{Colors.END} (last update {age/60:.1f} min ago)")
        else:
            print(f"  {status_dot('error')} {Colors.RED}Inactive{Colors.END} (last update {age/3600:.1f}h ago)")
        print(f"  {Colors.DIM}└── Log size: {monitor['log_size_kb']:.1f} KB{Colors.END}")
    else:
        print(f"  {status_dot('warning')} Not started yet")
        print(f"  {Colors.DIM}└── Run: python3 monitor/risk_monitor.py{Colors.END}")
    
    # 5. Data Collection
    print_section("5. DATA COLLECTION")
    data = get_collected_data_stats()
    if data.get('exists'):
        print(f"  {status_dot('active')} Collecting data")
        print(f"  {Colors.DIM}└── Records: {data['count']:,}")
        print(f"  └── File: {DATA_FILE}{Colors.END}")
    else:
        print(f"  {status_dot('warning')} No data yet")
        print(f"  {Colors.DIM}└── Will start collecting when monitor runs{Colors.END}")
    
    # 6. Recent activity
    print_section("6. RECENT ACTIVITY")
    if wallet and wallet.get('address'):
        txs = get_recent_transactions(wallet['address'], 3)
        if txs:
            for tx in txs:
                short_hash = tx['hash'][:10] + '...'
                short_to = tx['to'][:10] + '...' if tx['to'] else 'Contract creation'
                print(f"  {Colors.DIM}└── Block {tx['block']}: {short_hash}")
                print(f"      To: {short_to} | {tx['value_mon']:.4f} MON{Colors.END}")
        else:
            print(f"  {Colors.DIM}└── No recent transactions in last 100 blocks{Colors.END}")
    
    # 7. Quick links
    print_section("7. QUICK LINKS")
    print(f"  {Colors.CYAN}🔗 Explorer:{Colors.END} {EXPLORER_URL}")
    if wallet:
        print(f"  {Colors.CYAN}🔗 Your wallet:{Colors.END} {EXPLORER_URL}/address/{wallet['address']}")
    if 'contracts' in contracts_info:
        for name, info in contracts_info['contracts'].items():
            if info.get('deployed'):
                print(f"  {Colors.CYAN}🔗 {name}:{Colors.END} {EXPLORER_URL}/address/{info['address']}")
    
    # 8. Useful commands
    print_section("8. USEFUL COMMANDS")
    print(f"  {Colors.YELLOW}# Start risk monitor:{Colors.END}")
    print(f"    python3 /home/mobra/protocol/monitor/risk_monitor.py")
    print()
    print(f"  {Colors.YELLOW}# View live logs:{Colors.END}")
    print(f"    tail -f /home/mobra/protocol/monitor/risk_monitor.log")
    print()
    print(f"  {Colors.YELLOW}# Run dashboard:{Colors.END}")
    print(f"    cd /home/mobra/protocol/dashboard && npm run dev")
    print()
    print(f"  {Colors.YELLOW}# Watch this status:{Colors.END}")
    print(f"    python3 /home/mobra/protocol/monitor/status.py --watch")
    
    print(f"\n{Colors.CYAN}{'═' * 70}{Colors.END}\n")


def main():
    parser = argparse.ArgumentParser(description='Protocol Status Dashboard')
    parser.add_argument('--watch', action='store_true', help='Auto-refresh every 10 seconds')
    parser.add_argument('--interval', type=int, default=10, help='Refresh interval in seconds')
    args = parser.parse_args()
    
    if args.watch:
        try:
            while True:
                display_status()
                print(f"{Colors.DIM}Auto-refresh in {args.interval}s. Press Ctrl+C to exit.{Colors.END}")
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\n\nExiting...")
    else:
        display_status()


if __name__ == '__main__':
    main()
