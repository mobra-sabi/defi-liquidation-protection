#!/usr/bin/env python3
"""
Fetch REAL Class 0 from Aave V3 - Active Positions with HF 1.0-1.5

Uses paid TheGraph subscription to extract:
- All users with active borrows
- Calculate REAL health factor across all their positions
- Filter for HF 1.0-1.5 (real "at-risk" healthy positions)
- These are the missing Class 0 samples

Health Factor formula (Aave V3):
HF = Σ(collateral_i × liquidationThreshold_i × price_i) / Σ(debt_j × price_j)
"""

import os
import requests
import pandas as pd
import numpy as np
from datetime import datetime
import time
import json
from dotenv import load_dotenv

load_dotenv('/home/mobra/protocol/.env')

API_KEY = "656a25a51aac776685925fcaf6acfde7"
SUBGRAPH_ID = "Cd2gEDVeqnjBn1hSeqFMitw8Q1iiyV9FYUZkLNRcL87g"
URL = f"https://gateway.thegraph.com/api/{API_KEY}/subgraphs/id/{SUBGRAPH_ID}"


def calculate_health_factor(reserves):
    """
    Calculate health factor from a user's reserves.
    
    HF = Σ(weighted_collateral_usd) / Σ(debt_usd)
    where weighted_collateral = collateral × liquidationThreshold
    
    Returns:
        (health_factor, total_collateral_usd, total_debt_usd, weighted_collateral_usd)
    """
    weighted_collateral = 0.0
    total_collateral = 0.0
    total_debt = 0.0
    
    for r in reserves:
        try:
            decimals = int(r['reserve']['decimals'])
            price_raw = float(r['reserve']['price']['priceInEth'])
            
            # Skip if no price data
            if price_raw == 0:
                continue
            
            # priceInEth is actually priceInUSD × 10^8
            price_usd = price_raw / 1e8
            
            # Liquidation threshold in basis points (8300 = 83%)
            liq_threshold = float(r['reserve']['reserveLiquidationThreshold']) / 10000.0
            
            # Collateral (only if used as collateral)
            atoken_balance = float(r['currentATokenBalance'])
            if r['usageAsCollateralEnabledOnUser'] and atoken_balance > 0:
                collateral_usd = (atoken_balance / 10**decimals) * price_usd
                total_collateral += collateral_usd
                weighted_collateral += collateral_usd * liq_threshold
            
            # Debt
            total_debt_amount = float(r['currentTotalDebt'])
            if total_debt_amount > 0:
                debt_usd = (total_debt_amount / 10**decimals) * price_usd
                total_debt += debt_usd
                
        except (KeyError, ValueError, TypeError) as e:
            continue
    
    # Calculate HF
    if total_debt > 0:
        hf = weighted_collateral / total_debt
    else:
        hf = float('inf')  # No debt = infinite HF
    
    return hf, total_collateral, total_debt, weighted_collateral


def get_dominant_collateral(reserves):
    """Get the largest collateral asset."""
    largest = None
    largest_value = 0
    
    for r in reserves:
        try:
            if not r['usageAsCollateralEnabledOnUser']:
                continue
            
            decimals = int(r['reserve']['decimals'])
            price_raw = float(r['reserve']['price']['priceInEth'])
            atoken_balance = float(r['currentATokenBalance'])
            
            if atoken_balance == 0 or price_raw == 0:
                continue
            
            value_usd = (atoken_balance / 10**decimals) * (price_raw / 1e8)
            
            if value_usd > largest_value:
                largest_value = value_usd
                largest = r['reserve']['symbol']
        except:
            continue
    
    return largest or 'UNKNOWN', largest_value


def fetch_users_with_debt(target_count=50000, batch_size=500):
    """
    Fetch users with active debt and calculate their real HF.
    
    Strategy: Paginate through users, calculate HF, classify by HF range.
    """
    print("="*70)
    print("FETCHING REAL POSITIONS FROM AAVE V3 (PAID THEGRAPH)")
    print("="*70)
    print(f"Target: {target_count:,} positions analyzed")
    print(f"Batch size: {batch_size}")
    print()
    
    samples = []
    skip = 0
    processed = 0
    consecutive_empty = 0
    
    # Stats
    hf_distribution = {
        'hf_lt_1': 0,        # < 1.0 (would be liquidated already)
        'hf_1_to_1_05': 0,   # 1.0-1.05 (critical)
        'hf_1_05_to_1_15': 0, # 1.05-1.15 (alert)
        'hf_1_15_to_1_3': 0,  # 1.15-1.30 (warning)
        'hf_1_3_to_1_5': 0,   # 1.30-1.50 (safe-ish)
        'hf_gt_1_5': 0,       # > 1.5 (healthy)
        'no_debt': 0,
        'no_collateral': 0,
    }
    
    while processed < target_count and consecutive_empty < 3:
        query = """{
          users(first: %d, skip: %d, where: {borrowedReservesCount_gt: 0}) {
            id
            borrowedReservesCount
            reserves(first: 20) {
              currentATokenBalance
              currentTotalDebt
              currentVariableDebt
              currentStableDebt
              usageAsCollateralEnabledOnUser
              reserve {
                symbol
                decimals
                reserveLiquidationThreshold
                baseLTVasCollateral
                price { priceInEth }
              }
            }
          }
        }""" % (batch_size, skip)
        
        try:
            response = requests.post(URL, json={"query": query}, timeout=60)
            
            if response.status_code != 200:
                print(f"HTTP error {response.status_code}: {response.text[:200]}")
                break
            
            data = response.json()
            
            if 'errors' in data:
                print(f"GraphQL errors: {data['errors']}")
                break
            
            users = data.get('data', {}).get('users', [])
            
            if not users:
                consecutive_empty += 1
                print(f"Empty batch at skip={skip} (consecutive: {consecutive_empty})")
                # Try jumping ahead
                skip += batch_size * 10
                continue
            
            consecutive_empty = 0
            
            for user in users:
                processed += 1
                reserves = user.get('reserves', [])
                
                if not reserves:
                    continue
                
                hf, collateral_usd, debt_usd, weighted_collateral = calculate_health_factor(reserves)
                
                # Skip impossible cases
                if debt_usd == 0:
                    hf_distribution['no_debt'] += 1
                    continue
                if collateral_usd == 0:
                    hf_distribution['no_collateral'] += 1
                    continue
                
                # Classify
                if hf < 1.0:
                    hf_distribution['hf_lt_1'] += 1
                elif hf < 1.05:
                    hf_distribution['hf_1_to_1_05'] += 1
                elif hf < 1.15:
                    hf_distribution['hf_1_05_to_1_15'] += 1
                elif hf < 1.30:
                    hf_distribution['hf_1_15_to_1_3'] += 1
                elif hf < 1.50:
                    hf_distribution['hf_1_3_to_1_5'] += 1
                else:
                    hf_distribution['hf_gt_1_5'] += 1
                
                # Skip absurd HF values (data errors)
                if hf > 100 or hf < 0:
                    continue
                
                # Get dominant collateral asset
                dominant_collateral, dominant_value = get_dominant_collateral(reserves)
                
                # Get active reserves count
                active_collateral_count = sum(1 for r in reserves 
                                              if float(r['currentATokenBalance']) > 0 
                                              and r['usageAsCollateralEnabledOnUser'])
                active_debt_count = sum(1 for r in reserves 
                                        if float(r['currentTotalDebt']) > 0)
                
                # Calculate ratio
                collateral_to_debt = collateral_usd / max(debt_usd, 1)
                
                samples.append({
                    'user': user['id'],
                    'health_factor': hf,
                    'collateral_usd': collateral_usd,
                    'debt_usd': debt_usd,
                    'weighted_collateral_usd': weighted_collateral,
                    'collateral_to_debt_ratio': collateral_to_debt,
                    'dominant_collateral': dominant_collateral,
                    'dominant_collateral_usd': dominant_value,
                    'borrowed_reserves_count': int(user['borrowedReservesCount']),
                    'active_collateral_count': active_collateral_count,
                    'active_debt_count': active_debt_count,
                    'snapshot_timestamp': int(datetime.now().timestamp()),
                    'data_source': 'thegraph_aave_v3_real',
                })
            
            skip += batch_size
            
            # Progress
            if processed % 2000 == 0 or processed == target_count:
                print(f"\nProgress: {processed:,} users processed")
                print(f"  HF < 1.00:        {hf_distribution['hf_lt_1']:,}")
                print(f"  HF 1.00 - 1.05:   {hf_distribution['hf_1_to_1_05']:,}")
                print(f"  HF 1.05 - 1.15:   {hf_distribution['hf_1_05_to_1_15']:,}")
                print(f"  HF 1.15 - 1.30:   {hf_distribution['hf_1_15_to_1_3']:,}")
                print(f"  HF 1.30 - 1.50:   {hf_distribution['hf_1_3_to_1_5']:,}")
                print(f"  HF > 1.50:        {hf_distribution['hf_gt_1_5']:,}")
                print(f"  No debt:          {hf_distribution['no_debt']:,}")
                print(f"  No collateral:    {hf_distribution['no_collateral']:,}")
            
            time.sleep(0.1)  # Rate limiting
            
        except requests.exceptions.RequestException as e:
            print(f"Request error: {e}")
            time.sleep(2)
            continue
        except Exception as e:
            print(f"Error processing: {e}")
            continue
    
    print(f"\n{'='*70}")
    print(f"COMPLETED - Processed {processed:,} users")
    print(f"{'='*70}")
    print(f"\nValid samples extracted: {len(samples):,}")
    
    return samples, hf_distribution


def save_results(samples):
    """Save extracted positions to parquet."""
    if not samples:
        print("No samples to save")
        return None
    
    df = pd.DataFrame(samples)
    
    # Add label based on HF
    # Class 0: HF >= 1.0 (currently healthy/at-risk but not liquidated)
    # Class 1 reserved for actual liquidation events (joined later)
    df['label'] = 0  # All these are Class 0 (not currently being liquidated)
    
    # Time features (current snapshot)
    now = datetime.now()
    df['hour_of_day'] = now.hour
    df['day_of_week'] = now.weekday()
    df['is_weekend'] = 1 if now.weekday() >= 5 else 0
    df['is_night'] = 1 if 0 <= now.hour <= 6 else 0
    df['is_morning'] = 1 if 6 < now.hour <= 12 else 0
    df['is_afternoon'] = 1 if 12 < now.hour <= 18 else 0
    
    # Save full dataset
    output_full = '/home/mobra/protocol/data/aave_real_active_positions.parquet'
    df.to_parquet(output_full, index=False, compression='snappy')
    print(f"\n✅ Saved {len(df):,} positions to:")
    print(f"   {output_full}")
    
    # Save subsets by HF range
    print("\n📊 Distribution by HF range:")
    
    ranges = [
        ('hf_critical', df[df['health_factor'] < 1.05], '< 1.05'),
        ('hf_alert', df[(df['health_factor'] >= 1.05) & (df['health_factor'] < 1.15)], '1.05 - 1.15'),
        ('hf_warning', df[(df['health_factor'] >= 1.15) & (df['health_factor'] < 1.30)], '1.15 - 1.30'),
        ('hf_safe_low', df[(df['health_factor'] >= 1.30) & (df['health_factor'] < 1.50)], '1.30 - 1.50'),
        ('hf_healthy', df[df['health_factor'] >= 1.50], '>= 1.50'),
    ]
    
    for name, subset, label in ranges:
        print(f"  {label:>14s}: {len(subset):>6,} positions ({len(subset)/len(df)*100:.1f}%)")
    
    # Save key Class 0 subset (HF 1.0-1.5 - the "at risk but healthy" range)
    class_0_real = df[(df['health_factor'] >= 1.0) & (df['health_factor'] < 1.5)]
    if len(class_0_real) > 0:
        output_class0 = '/home/mobra/protocol/data/aave_class_0_real.parquet'
        class_0_real.to_parquet(output_class0, index=False)
        print(f"\n✅ Real Class 0 (HF 1.0-1.5): {len(class_0_real):,} samples")
        print(f"   Saved to: {output_class0}")
    
    return df


def main():
    print("\n" + "="*70)
    print("EXTRACTING REAL CLASS 0 FROM AAVE V3 (PAID THEGRAPH)")
    print("="*70)
    print()
    print("Goal: Get real positions with HF 1.0-1.5")
    print("Method: Calculate real HF across all user reserves")
    print()
    
    # Process up to 50,000 users
    samples, distribution = fetch_users_with_debt(target_count=50000, batch_size=500)
    
    if samples:
        df = save_results(samples)
        
        print("\n" + "="*70)
        print("✅ SUCCESS - REAL CLASS 0 EXTRACTED")
        print("="*70)
        print(f"\nThis data combined with the 24,525 real liquidations gives")
        print(f"you a fully REAL dataset for ML training.")
        print(f"\nNext: Train XGBoost on real Class 0 + real Class 1")
    else:
        print("\n❌ No samples extracted")


if __name__ == '__main__':
    main()
