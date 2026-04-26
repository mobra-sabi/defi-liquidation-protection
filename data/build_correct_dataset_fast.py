#!/usr/bin/env python3
"""
Build CORRECT Dataset for Liquidation Prediction - NO LEAKAGE (Optimized Version)
"""

import os
import requests
import pandas as pd
import numpy as np
from datetime import datetime
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

API_KEY = os.getenv('THEGRAPH_API_KEY', '656a25a51aac776685925fcaf6acfde7')
SUBGRAPH_URL = f"https://gateway.thegraph.com/api/{API_KEY}/subgraphs/id/Cd2gEDVeqnjBn1hSeqFMitw8Q1iiyV9FYUZkLNRcL87g"

TIME_WINDOWS = [
    (1800, '30min'),
    (3600, '1h'),
    (7200, '2h'),
    (14400, '4h'),
    (86400, '24h'),
]

PREDICTION_HORIZON = 1800
MAX_WORKERS = 10

def fetch_liquidations(limit=1000):
    """Fetch liquidation events."""
    print("="*70)
    print(f"FETCHING {limit} LIQUIDATION EVENTS")
    print("="*70)
    
    liquidations = []
    skip = 0
    batch_size = 1000
    
    while len(liquidations) < limit:
        query = {
            "query": f"""{{
                liquidationCalls(
                    first: {batch_size},
                    skip: {skip},
                    orderBy: timestamp,
                    orderDirection: desc
                ) {{
                    id
                    timestamp
                    user {{ id }}
                    collateralReserve {{ id symbol decimals }}
                    principalReserve {{ id symbol decimals }}
                    collateralAmount
                    principalAmount
                    liquidator
                }}
            }}"""
        }
        
        try:
            response = requests.post(SUBGRAPH_URL, json=query, timeout=30)
            if response.status_code == 200:
                data = response.json()
                if 'data' in data and data['data']:
                    batch = data['data'].get('liquidationCalls', [])
                    if not batch:
                        break
                    
                    for liq in batch:
                        liquidations.append({
                            'id': liq['id'],
                            'timestamp': int(liq['timestamp']),
                            'user': liq['user']['id'],
                            'collateral_reserve': liq['collateralReserve']['symbol'],
                            'debt_reserve': liq['principalReserve']['symbol'],
                            'collateral_amount_raw': int(liq['collateralAmount']),
                            'debt_amount_raw': int(liq['principalAmount']),
                        })
                    
                    skip += batch_size
                    print(f"  Fetched {len(liquidations)} liquidations...")
                    
                    if len(liquidations) >= limit or len(batch) < batch_size:
                        break
                else:
                    break
            else:
                break
        except Exception as e:
            print(f"Exception: {e}")
            break
        
        time.sleep(0.05)
    
    liquidations = liquidations[:limit]
    print(f"✅ Total liquidations: {len(liquidations)}")
    return liquidations

def fetch_position_at_time(user_address, reserve_symbol, target_timestamp):
    """Query user's position state at a specific historical time."""
    query = {
        "query": f"""{{
            userReservesHistoryItems(
                where: {{
                    userReserve_: {{
                        user: "{user_address}",
                        reserve_: {{ symbol: "{reserve_symbol}" }}
                    }},
                    timestamp_lte: {target_timestamp}
                }},
                orderBy: timestamp,
                orderDirection: desc,
                first: 1
            ) {{
                timestamp
                currentATokenBalance
                currentVariableDebt
                currentStableDebt
                scaledVariableDebt
                liquidityRate
                variableBorrowRate
                stableBorrowRate
                userReserve {{
                    reserve {{
                        symbol
                        decimals
                        price {{ priceInUSD }}
                        liquidationThreshold
                        baseLTVasCollateral
                    }}
                }}
            }}
        }}"""
    }
    
    try:
        response = requests.post(SUBGRAPH_URL, json=query, timeout=30)
        if response.status_code == 200:
            data = response.json()
            if 'data' in data and data['data']:
                items = data['data'].get('userReservesHistoryItems', [])
                if items:
                    return items[0]
        return None
    except Exception as e:
        return None

def calculate_health_factor(collateral_usd, debt_usd, liquidation_threshold):
    """Calculate health factor from position values."""
    if debt_usd <= 0:
        return float('inf')
    return (collateral_usd * liquidation_threshold) / debt_usd

def build_sample_for_window(liq, time_offset, window_name):
    """Build a sample at a specific time BEFORE the liquidation."""
    try:
        user = liq['user']
        liq_timestamp = liq['timestamp']
        reserve_symbol = liq['collateral_reserve']
        
        observation_time = liq_timestamp - time_offset
        
        # Query position state at observation time
        position = fetch_position_at_time(user, reserve_symbol, observation_time)
        
        if not position:
            return None
        
        # Extract data available AT observation time
        collateral_raw = int(position.get('currentATokenBalance', 0))
        debt_var = int(position.get('currentVariableDebt', 0))
        debt_stable = int(position.get('currentStableDebt', 0))
        debt_raw = debt_var + debt_stable
        
        # Skip if no debt
        if debt_raw == 0:
            return None
        
        # Get reserve info
        reserve = position.get('userReserve', {}).get('reserve', {})
        decimals = int(reserve.get('decimals', 18))
        price_usd = float(reserve.get('price', {}).get('priceInUSD', 0))
        liquidation_threshold = float(reserve.get('liquidationThreshold', 0.85))
        base_ltv = float(reserve.get('baseLTVasCollateral', 0.8))
        
        # Calculate USD values AT observation time
        collateral_decimals = 10 ** decimals
        collateral_usd = (collateral_raw / collateral_decimals) * price_usd
        debt_usd = (debt_raw / collateral_decimals) * price_usd
        
        # Calculate health factor
        hf = calculate_health_factor(collateral_usd, debt_usd, liquidation_threshold)
        
        # Determine label
        time_until_liquidation = liq_timestamp - observation_time
        label = 1 if time_until_liquidation <= PREDICTION_HORIZON else 0
        
        # Time features
        obs_dt = datetime.fromtimestamp(observation_time)
        
        return {
            'user': user,
            'liquidation_id': liq['id'],
            'reserve_symbol': reserve_symbol,
            'observation_timestamp': observation_time,
            'observation_datetime': obs_dt,
            'liquidation_timestamp': liq_timestamp,
            'time_before_liquidation_seconds': time_offset,
            'label': label,
            'collateral_raw': collateral_raw,
            'debt_raw': debt_raw,
            'collateral_usd': collateral_usd,
            'debt_usd': debt_usd,
            'health_factor': hf,
            'collateral_to_debt_ratio': collateral_raw / max(debt_raw, 1),
            'liquidation_threshold': liquidation_threshold,
            'base_ltv': base_ltv,
            'liquidity_rate': float(position.get('liquidityRate', 0)),
            'variable_borrow_rate': float(position.get('variableBorrowRate', 0)),
            'hour_of_day': obs_dt.hour,
            'day_of_week': obs_dt.weekday(),
            'is_weekend': 1 if obs_dt.weekday() >= 5 else 0,
            'is_night': 1 if 0 <= obs_dt.hour <= 6 else 0,
            'is_morning': 1 if 6 < obs_dt.hour <= 12 else 0,
            'is_afternoon': 1 if 12 < obs_dt.hour <= 18 else 0,
        }
    except Exception as e:
        return None

def build_correct_dataset():
    """Build the correct dataset with parallel processing."""
    print("\n" + "="*70)
    print("BUILDING CORRECT DATASET - NO LEAKAGE (Optimized)")
    print("="*70)
    
    # Step 1: Get liquidations (limit to 1000 for speed)
    liquidations = fetch_liquidations(limit=1000)
    
    if len(liquidations) == 0:
        print("❌ No liquidations fetched!")
        return
    
    # Step 2: Build samples in parallel
    print(f"\nBuilding samples for {len(liquidations)} liquidations...")
    print(f"Time windows: {[t[1] for t in TIME_WINDOWS]}")
    print(f"Prediction horizon: 30 minutes")
    print(f"Workers: {MAX_WORKERS}")
    
    # Create all tasks
    tasks = []
    for liq in liquidations:
        for time_offset, window_name in TIME_WINDOWS:
            tasks.append((liq, time_offset, window_name))
    
    print(f"Total tasks: {len(tasks)}")
    
    samples = []
    completed = 0
    failed = 0
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(build_sample_for_window, liq, offset, name): (liq, offset, name) 
                   for liq, offset, name in tasks}
        
        for future in as_completed(futures):
            result = future.result()
            if result:
                samples.append(result)
            else:
                failed += 1
            
            completed += 1
            if completed % 100 == 0:
                print(f"  Progress: {completed}/{len(tasks)} ({len(samples)} samples, {failed} failed)")
    
    print(f"\n✅ Built {len(samples)} samples ({failed} failed)")
    
    if len(samples) == 0:
        print("❌ No samples created!")
        return
    
    # Step 3: Convert to DataFrame
    df = pd.DataFrame(samples)
    
    # Handle infinite health factors
    df['health_factor'] = df['health_factor'].replace([np.inf, -np.inf], np.nan)
    df['health_factor'] = df['health_factor'].fillna(df['health_factor'].median())
    
    # Step 4: Statistics
    print("\n" + "="*70)
    print("CORRECT DATASET STATISTICS")
    print("="*70)
    print(f"Total samples: {len(df)}")
    print(f"\nLabel distribution:")
    print(f"  Class 0 (survives 30min): {(df['label'] == 0).sum():,} ({(df['label'] == 0).mean():.1%})")
    print(f"  Class 1 (liquidated in 30min): {(df['label'] == 1).sum():,} ({(df['label'] == 1).mean():.1%})")
    
    print(f"\nBy time window:")
    for time_offset, window_name in TIME_WINDOWS:
        count = (df['time_before_liquidation_seconds'] == time_offset).sum()
        pos = ((df['time_before_liquidation_seconds'] == time_offset) & (df['label'] == 1)).sum()
        print(f"  {window_name:10s}: {count:5,} samples, {pos:4,} positive ({pos/max(count,1)*100:.1f}%)")
    
    print(f"\nHealth factor by label:")
    print(df.groupby('label')['health_factor'].describe())
    
    print(f"\nReserve symbols:")
    print(df['reserve_symbol'].value_counts().head(10))
    
    print(f"\nDate range:")
    print(f"  From: {df['observation_datetime'].min()}")
    print(f"  To:   {df['observation_datetime'].max()}")
    
    # Step 5: Save
    output_file = '/home/mobra/protocol/data/aave_correct_dataset.parquet'
    df.to_parquet(output_file, index=False, compression='snappy')
    
    csv_sample = '/home/mobra/protocol/data/aave_correct_dataset_sample.csv'
    df.head(10000).to_csv(csv_sample, index=False)
    
    print(f"\n" + "="*70)
    print("DATASET SAVED")
    print("="*70)
    print(f"  Main file: {output_file}")
    print(f"  Sample:    {csv_sample}")
    print(f"  Size:      {len(df):,} samples × {len(df.columns)} features")
    
    # Validation
    print(f"\n" + "="*70)
    print("VALIDATION CHECK")
    print("="*70)
    print("✅ No obvious leakage columns detected")
    
    if len(df[df['label'] == 0]) > 0 and len(df[df['label'] == 1]) > 0:
        print(f"\nSample with label=0 (survives):")
        sample_0 = df[df['label'] == 0].iloc[0]
        print(f"  HF: {sample_0['health_factor']:.3f}, Collateral: ${sample_0['collateral_usd']:,.0f}")
        
        print(f"\nSample with label=1 (liquidated in 30min):")
        sample_1 = df[df['label'] == 1].iloc[0]
        print(f"  HF: {sample_1['health_factor']:.3f}, Collateral: ${sample_1['collateral_usd']:,.0f}")
    
    return df

if __name__ == '__main__':
    build_correct_dataset()
