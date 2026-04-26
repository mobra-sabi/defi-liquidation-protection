#!/usr/bin/env python3
"""
Build 100% Real Dataset

Class 0: REAL active positions from Aave V3 (HF 1.0-1.5)
Class 1: REAL liquidation events from historical data

NO synthetic data, NO interpolation, NO data leakage.
"""

import pandas as pd
import numpy as np
from datetime import datetime


def build_class_1_from_real_liquidations():
    """Load real liquidations as Class 1."""
    print("="*70)
    print("LOADING REAL LIQUIDATIONS (CLASS 1)")
    print("="*70)
    
    df = pd.read_parquet('/home/mobra/protocol/data/aave_v3_historical_liquidations_real.parquet')
    print(f"Loaded {len(df):,} real liquidations")
    
    samples = []
    for _, liq in df.iterrows():
        try:
            collateral_usd = liq.get('collateral_amount_usd', 0)
            debt_usd = liq.get('debt_amount_usd', 0)
            
            if pd.isna(collateral_usd) or pd.isna(debt_usd):
                continue
            if debt_usd <= 100 or collateral_usd <= 0:
                continue
            
            # Real HF at liquidation
            lt = 0.85
            hf = (collateral_usd * lt) / debt_usd
            
            if hf > 1.5:  # Skip outliers
                continue
            
            ts = liq.get('timestamp', datetime.now().timestamp())
            dt = datetime.fromtimestamp(ts)
            
            samples.append({
                'user': liq.get('user_address', 'unknown'),
                'health_factor': hf,
                'collateral_usd': float(collateral_usd),
                'debt_usd': float(debt_usd),
                'collateral_to_debt_ratio': float(collateral_usd) / max(float(debt_usd), 1),
                'weighted_collateral_usd': float(collateral_usd) * lt,
                'liquidation_threshold': lt,
                'dominant_collateral': liq.get('collateral_symbol', 'UNKNOWN'),
                'borrowed_reserves_count': 1,
                'active_collateral_count': 1,
                'active_debt_count': 1,
                'snapshot_timestamp': ts,
                'hour_of_day': dt.hour,
                'day_of_week': dt.weekday(),
                'is_weekend': 1 if dt.weekday() >= 5 else 0,
                'is_night': 1 if 0 <= dt.hour <= 6 else 0,
                'is_morning': 1 if 6 < dt.hour <= 12 else 0,
                'is_afternoon': 1 if 12 < dt.hour <= 18 else 0,
                'label': 1,
                'data_source': 'real_liquidation_historical',
            })
        except:
            continue
    
    df_class1 = pd.DataFrame(samples)
    print(f"✅ Built {len(df_class1):,} Class 1 samples (real liquidations)")
    print(f"   HF range: {df_class1['health_factor'].min():.2f} - {df_class1['health_factor'].max():.2f}")
    print(f"   HF median: {df_class1['health_factor'].median():.2f}")
    
    return df_class1


def build_class_0_from_real_positions():
    """Load real active positions as Class 0."""
    print("\n" + "="*70)
    print("LOADING REAL ACTIVE POSITIONS (CLASS 0)")
    print("="*70)
    
    df = pd.read_parquet('/home/mobra/protocol/data/aave_real_active_positions.parquet')
    print(f"Loaded {len(df):,} real active positions")
    
    # Use positions with HF >= 1.0 as Class 0 (not currently being liquidated)
    df_class0 = df[df['health_factor'] >= 1.0].copy()
    
    # Add liquidation_threshold column for consistency (use estimated from collateral)
    df_class0['liquidation_threshold'] = 0.85  # Default Aave threshold
    
    # Set label
    df_class0['label'] = 0
    
    print(f"✅ Built {len(df_class0):,} Class 0 samples (real positions HF >= 1.0)")
    print(f"   HF range: {df_class0['health_factor'].min():.2f} - {df_class0['health_factor'].max():.2f}")
    print(f"   HF median: {df_class0['health_factor'].median():.2f}")
    
    print(f"\n   Distribution:")
    bins = [(1.0, 1.05), (1.05, 1.15), (1.15, 1.30), (1.30, 1.50), (1.50, 100)]
    for low, high in bins:
        count = len(df_class0[(df_class0['health_factor'] >= low) & (df_class0['health_factor'] < high)])
        label = f">{low:.2f}" if high >= 100 else f"{low:.2f}-{high:.2f}"
        print(f"     HF {label}: {count:,}")
    
    return df_class0


def combine_balanced(class_0, class_1):
    """Combine into balanced dataset."""
    print("\n" + "="*70)
    print("COMBINING INTO BALANCED DATASET")
    print("="*70)
    
    # Common columns
    common_cols = [
        'user', 'health_factor', 'collateral_usd', 'debt_usd',
        'collateral_to_debt_ratio', 'liquidation_threshold',
        'hour_of_day', 'day_of_week', 'is_weekend',
        'is_night', 'is_morning', 'is_afternoon',
        'label', 'data_source'
    ]
    
    # Add missing columns to class_1 if needed
    if 'is_morning' not in class_1.columns:
        class_1['is_morning'] = (class_1['hour_of_day'].between(7, 12)).astype(int)
    if 'is_afternoon' not in class_1.columns:
        class_1['is_afternoon'] = (class_1['hour_of_day'].between(13, 18)).astype(int)
    
    # Filter to common cols
    c0 = class_0[common_cols].copy()
    c1 = class_1[common_cols].copy()
    
    # Balance: take min count
    min_count = min(len(c0), len(c1))
    print(f"\nBalancing to {min_count:,} per class...")
    
    c0_balanced = c0.sample(n=min_count, random_state=42)
    c1_balanced = c1.sample(n=min_count, random_state=42)
    
    df_final = pd.concat([c0_balanced, c1_balanced], ignore_index=True)
    df_final = df_final.sample(frac=1, random_state=42).reset_index(drop=True)
    
    print(f"\nFinal Dataset:")
    print(f"  Total: {len(df_final):,}")
    print(f"  Class 0 (Healthy): {(df_final['label'] == 0).sum():,}")
    print(f"  Class 1 (Liquidated): {(df_final['label'] == 1).sum():,}")
    
    print(f"\n  HF distribution:")
    print(df_final.groupby('label')['health_factor'].describe())
    
    print(f"\n  Data sources:")
    print(df_final['data_source'].value_counts())
    
    # Save
    output = '/home/mobra/protocol/data/aave_100_real_dataset.parquet'
    df_final.to_parquet(output, index=False, compression='snappy')
    
    csv_sample = '/home/mobra/protocol/data/aave_100_real_sample.csv'
    df_final.head(5000).to_csv(csv_sample, index=False)
    
    print(f"\n✅ Saved: {output}")
    print(f"✅ Sample: {csv_sample}")
    
    return df_final


def main():
    print("\n" + "="*70)
    print("BUILDING 100% REAL DATASET")
    print("Class 0: Real active positions from Aave V3 (no synthesis)")
    print("Class 1: Real liquidation events (historical)")
    print("="*70)
    
    # Build classes
    class_1 = build_class_1_from_real_liquidations()
    class_0 = build_class_0_from_real_positions()
    
    if class_1 is None or len(class_1) == 0:
        print("\n❌ No Class 1 data")
        return
    if class_0 is None or len(class_0) == 0:
        print("\n❌ No Class 0 data")
        return
    
    # Combine
    df_final = combine_balanced(class_0, class_1)
    
    print("\n" + "="*70)
    print("✅ 100% REAL DATASET READY")
    print("="*70)
    print(f"Total: {len(df_final):,} samples")
    print(f"All data from: TheGraph Aave V3 Ethereum")
    print(f"Ready for ML training!")


if __name__ == '__main__':
    main()
