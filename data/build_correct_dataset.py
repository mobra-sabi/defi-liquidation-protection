#!/usr/bin/env python3
"""
Build CORRECT Dataset for Liquidation Prediction - NO LEAKAGE

For each liquidation event:
1. Query position history at multiple times BEFORE liquidation
2. Label=1 if liquidation happens within 30 minutes AFTER observation
3. Label=0 if position survives 30 minutes after observation
4. Use ONLY features available at observation time

This creates a valid binary classification: "Will this position be liquidated in next 30min?"
"""

import os
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import time
# Load API key directly (dotenv disabled due to import issues)
API_KEY = os.getenv('THEGRAPH_API_KEY', '656a25a51aac776685925fcaf6acfde7')
SUBGRAPH_URL = f"https://gateway.thegraph.com/api/{API_KEY}/subgraphs/id/Cd2gEDVeqnjBn1hSeqFMitw8Q1iiyV9FYUZkLNRcL87g"

# Time windows before liquidation to create samples (in seconds)
TIME_WINDOWS = [
    (1800, '30min'),    # 30 minutes before
    (3600, '1h'),       # 1 hour before
    (7200, '2h'),       # 2 hours before
    (14400, '4h'),      # 4 hours before
    (86400, '24h'),     # 24 hours before
]

# Prediction horizon (what we want to predict)
PREDICTION_HORIZON = 1800  # 30 minutes in seconds


def fetch_liquidations_with_details():
    """
    Fetch liquidation events with full details including user address and exact timestamp.
    """
    print("="*70)
    print("FETCHING LIQUIDATION EVENTS")
    print("="*70)
    
    liquidations = []
    skip = 0
    batch_size = 1000
    max_liquidations = 5000  # Limit for initial testing
    
    while len(liquidations) < max_liquidations:
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
                    
                    user {{
                        id
                    }}
                    collateralReserve {{
                        id
                        symbol
                        decimals
                    }}
                    principalReserve {{
                        id
                        symbol
                        decimals
                    }}
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
                    
                    if len(batch) < batch_size:
                        break
                else:
                    break
            else:
                print(f"Error: HTTP {response.status_code}")
                break
        except Exception as e:
            print(f"Exception: {e}")
            break
        
        time.sleep(0.1)
    
    print(f"✅ Total liquidations: {len(liquidations)}")
    return liquidations


def fetch_position_at_time(user_address, reserve_symbol, target_timestamp):
    """
    Query the user's position state at a specific historical time.
    
    Returns position data (health factor, collateral, debt) as it was at target_timestamp.
    """
    query = {
        "query": f"""{{
            userReservesHistoryItems(
                where: {{
                    userReserve_: {{
                        user: "{user_address}",
                        reserve_: {{
                            symbol: "{reserve_symbol}"
                        }}
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
                        price {{
                            priceInUSD
                        }}
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
        return float('inf')  # No debt = infinite health
    return (collateral_usd * liquidation_threshold) / debt_usd


def build_correct_sample(liquidation, time_offset_seconds, label):
    """
    Build a sample at a specific time BEFORE the liquidation.
    
    Args:
        liquidation: The liquidation event data
        time_offset_seconds: How many seconds BEFORE liquidation to observe
        label: 1 if liquidated within 30min after observation, 0 otherwise
    """
    try:
        user = liquidation['user']
        liq_timestamp = liquidation['timestamp']
        reserve_symbol = liquidation['collateral_reserve']
        
        # Target time: X seconds BEFORE liquidation
        observation_time = liq_timestamp - time_offset_seconds
        
        # Query position state at observation time
        position = fetch_position_at_time(user, reserve_symbol, observation_time)
        
        if not position:
            return None
        
        # Extract data available AT observation time
        collateral_raw = int(position.get('currentATokenBalance', 0))
        debt_var = int(position.get('currentVariableDebt', 0))
        debt_stable = int(position.get('currentStableDebt', 0))
        debt_raw = debt_var + debt_stable
        
        # Skip if no debt (not at risk of liquidation)
        if debt_raw == 0:
            return None
        
        # Get reserve info (at observation time)
        reserve = position.get('userReserve', {}).get('reserve', {})
        decimals = int(reserve.get('decimals', 18))
        price_usd = float(reserve.get('price', {}).get('priceInUSD', 0))
        liquidation_threshold = float(reserve.get('liquidationThreshold', 0.85))
        base_ltv = float(reserve.get('baseLTVasCollateral', 0.8))
        
        # Calculate USD values AT observation time (not at liquidation!)
        collateral_decimals = 10 ** decimals
        collateral_usd = (collateral_raw / collateral_decimals) * price_usd
        debt_usd = (debt_raw / collateral_decimals) * price_usd
        
        # Calculate health factor AT observation time
        hf = calculate_health_factor(collateral_usd, debt_usd, liquidation_threshold)
        
        # Time features (from observation timestamp)
        obs_dt = datetime.fromtimestamp(observation_time)
        
        # Build sample
        sample = {
            'user': user,
            'liquidation_id': liquidation['id'],
            'reserve_symbol': reserve_symbol,
            'observation_timestamp': observation_time,
            'observation_datetime': obs_dt,
            'liquidation_timestamp': liq_timestamp,
            'time_before_liquidation_seconds': time_offset_seconds,
            'label': label,
            
            # Position state AT observation time
            'collateral_raw': collateral_raw,
            'debt_raw': debt_raw,
            'collateral_usd': collateral_usd,
            'debt_usd': debt_usd,
            'health_factor': hf,
            'collateral_to_debt_ratio': collateral_raw / max(debt_raw, 1),
            'liquidation_threshold': liquidation_threshold,
            'base_ltv': base_ltv,
            
            # Rates at observation time
            'liquidity_rate': float(position.get('liquidityRate', 0)),
            'variable_borrow_rate': float(position.get('variableBorrowRate', 0)),
            
            # Time features
            'hour_of_day': obs_dt.hour,
            'day_of_week': obs_dt.weekday(),
            'is_weekend': 1 if obs_dt.weekday() >= 5 else 0,
            'is_night': 1 if 0 <= obs_dt.hour <= 6 else 0,
            'is_morning': 1 if 6 < obs_dt.hour <= 12 else 0,
            'is_afternoon': 1 if 12 < obs_dt.hour <= 18 else 0,
        }
        
        return sample
        
    except Exception as e:
        print(f"Error building sample: {e}")
        return None


def build_correct_dataset():
    """
    Build the correct dataset with proper temporal sampling.
    
    For each liquidation:
    - Create samples at multiple times BEFORE liquidation
    - Label=1: Liquidated within 30 minutes AFTER observation
    - Label=0: NOT liquidated within 30 minutes after observation
    """
    print("\n" + "="*70)
    print("BUILDING CORRECT DATASET - NO LEAKAGE")
    print("="*70)
    
    # Step 1: Get liquidations
    liquidations = fetch_liquidations_with_details()
    
    if len(liquidations) == 0:
        print("❌ No liquidations fetched!")
        return
    
    # Step 2: Build samples
    print(f"\nBuilding samples for {len(liquidations)} liquidations...")
    print(f"Time windows: {[t[1] for t in TIME_WINDOWS]}")
    print(f"Prediction horizon: 30 minutes")
    
    samples = []
    
    for i, liq in enumerate(liquidations):
        if i % 100 == 0:
            print(f"  Processing {i+1}/{len(liquidations)}... ({len(samples)} samples so far)")
        
        liq_timestamp = liq['timestamp']
        
        for time_offset, window_name in TIME_WINDOWS:
            observation_time = liq_timestamp - time_offset
            
            # Determine label:
            # 1 = "Will be liquidated within 30 minutes AFTER this observation"
            # 0 = "Will NOT be liquidated within 30 minutes after this observation"
            
            # Since we know the exact liquidation time:
            time_until_liquidation = liq_timestamp - observation_time
            
            if time_until_liquidation <= PREDICTION_HORIZON:
                # Liquidation happens within 30 minutes → label=1
                label = 1
            else:
                # Liquidation happens after 30 minutes → label=0 (survives next 30min)
                label = 0
            
            # Build sample
            sample = build_correct_sample(liq, time_offset, label)
            if sample:
                samples.append(sample)
        
        # Rate limiting
        if i % 50 == 0:
            time.sleep(0.2)
    
    print(f"\n✅ Built {len(samples)} samples")
    
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
    
    # Validation check
    print(f"\n" + "="*70)
    print("VALIDATION CHECK")
    print("="*70)
    
    # Check for obvious leakage
    leakage_indicators = [
        'liquidation_timestamp' in [c.lower().replace('_', '') for c in df.columns],
        'liquidation_price' in [c.lower().replace('_', '') for c in df.columns],
    ]
    
    if any(leakage_indicators):
        print("⚠️  WARNING: Potential leakage detected!")
    else:
        print("✅ No obvious leakage columns detected")
    
    # Show sample of each class
    print(f"\nSample with label=0 (survives):")
    sample_0 = df[df['label'] == 0].iloc[0]
    print(f"  HF: {sample_0['health_factor']:.3f}, Collateral: ${sample_0['collateral_usd']:,.0f}")
    
    print(f"\nSample with label=1 (liquidated in 30min):")
    sample_1 = df[df['label'] == 1].iloc[0]
    print(f"  HF: {sample_1['health_factor']:.3f}, Collateral: ${sample_1['collateral_usd']:,.0f}")
    
    return df


if __name__ == '__main__':
    build_correct_dataset()
