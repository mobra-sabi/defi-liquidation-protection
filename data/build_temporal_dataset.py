#!/usr/bin/env python3
"""
Build Temporal Dataset for Liquidation Prediction

For each liquidation event, creates multiple temporal samples:
- T-0 (at liquidation): label=1
- T-10min before: label=0
- T-30min before: label=0  
- T-1h before: label=0
- T-1day before: label=0

Uses cached liquidation data and interpolates temporal features.
"""

import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import time
from typing import List, Dict, Optional

# Time offsets for samples (in seconds before liquidation)
TIME_OFFSETS = [
    (0, 1, "at_liquidation"),           # At liquidation (label=1)
    (600, 0, "10min_before"),           # 10 min before (label=0)
    (1800, 0, "30min_before"),          # 30 min before (label=0)
    (3600, 0, "1h_before"),             # 1 hour before (label=0)
    (86400, 0, "1day_before"),          # 1 day before (label=0)
]


def load_cached_liquidations(filepath: str = 'data/historical_liquidations.parquet') -> pd.DataFrame:
    """Load cached liquidation data."""
    print(f"Loading cached liquidations from {filepath}...")
    
    if not os.path.exists(filepath):
        # Try alternate paths
        alternate_paths = [
            'data/aave_v3_historical_liquidations_real.parquet',
            'data/aave_real_liquidations_1k.parquet',
        ]
        for alt_path in alternate_paths:
            if os.path.exists(alt_path):
                filepath = alt_path
                print(f"Using alternate path: {filepath}")
                break
    
    df = pd.read_parquet(filepath)
    print(f"✅ Loaded {len(df):,} liquidations")
    
    # Ensure timestamp is numeric
    if 'timestamp' in df.columns:
        df['timestamp'] = pd.to_numeric(df['timestamp'], errors='coerce')
    
    return df


def interpolate_health_factor(
    hf_at_liquidation: float, 
    offset_seconds: int,
    velocity_1h: float = 0,
    velocity_4h: float = 0,
    velocity_24h: float = 0
) -> float:
    """
    Estimate health factor at a time before liquidation.
    
    Uses velocity information to interpolate backwards.
    """
    hours_before = offset_seconds / 3600
    
    # Choose velocity based on time horizon
    if hours_before <= 1:
        velocity = velocity_1h
    elif hours_before <= 4:
        velocity = velocity_4h
    else:
        velocity = velocity_24h
    
    # Health factor was better before liquidation (moving towards liquidation)
    # Velocity is negative (health factor decreasing), so go backwards = add
    estimated_hf = hf_at_liquidation - (velocity * hours_before)
    
    # Add some realistic noise based on time distance
    noise_scale = 0.02 * (hours_before / 24 + 0.1)  # More noise for longer times
    noise = np.random.normal(0, noise_scale)
    
    return max(0.5, min(3.0, estimated_hf + noise))


def build_temporal_sample(
    liquidation: pd.Series, 
    offset_seconds: int, 
    label: int,
    time_label: str
) -> Optional[Dict]:
    """
    Build a sample at a specific time offset from liquidation.
    
    Uses interpolation from existing liquidation features.
    """
    try:
        liq_timestamp = int(liquidation['timestamp'])
        target_timestamp = liq_timestamp - offset_seconds
        
        # Parse datetime if available
        if 'datetime' in liquidation and pd.notna(liquidation['datetime']):
            try:
                liq_dt = pd.to_datetime(liquidation['datetime'])
            except:
                liq_dt = datetime.fromtimestamp(liq_timestamp)
        else:
            liq_dt = datetime.fromtimestamp(liq_timestamp)
        
        target_dt = liq_dt - timedelta(seconds=offset_seconds)
        
        # Get velocities for interpolation
        hf_velocity_1h = liquidation.get('health_factor_velocity_1h', -0.05)
        hf_velocity_4h = liquidation.get('health_factor_velocity_4h', -0.10)
        hf_velocity_24h = liquidation.get('health_factor_velocity_24h', -0.30)
        
        if pd.isna(hf_velocity_1h): hf_velocity_1h = -0.05
        if pd.isna(hf_velocity_4h): hf_velocity_4h = -0.10
        if pd.isna(hf_velocity_24h): hf_velocity_24h = -0.30
        
        # Health factor at liquidation
        hf_at_liq = liquidation.get('health_factor_at_liquidation', 0.95)
        if pd.isna(hf_at_liq): hf_at_liq = 0.95
        
        # Interpolate health factor at target time
        hf = interpolate_health_factor(
            hf_at_liq, 
            offset_seconds,
            hf_velocity_1h,
            hf_velocity_4h,
            hf_velocity_24h
        )
        
        # Collateral and debt values - adjust based on time offset
        # Earlier = generally higher collateral, lower debt (position degrading over time)
        hours_before = offset_seconds / 3600
        degradation_factor = 1 + (hours_before * 0.01)  # 1% improvement per hour back
        
        collateral_usd_liq = liquidation.get('collateral_amount_usd', 0)
        debt_usd_liq = liquidation.get('debt_amount_usd', 0)
        
        if pd.isna(collateral_usd_liq): collateral_usd_liq = 0
        if pd.isna(debt_usd_liq): debt_usd_liq = 0
        
        # Apply degradation factor (position was better before)
        collateral_usd = collateral_usd_liq * degradation_factor * (1 + np.random.normal(0, 0.02))
        debt_usd = debt_usd_liq / degradation_factor * (1 + np.random.normal(0, 0.02))
        
        # Calculate collateral to debt ratio
        cdr = collateral_usd / max(debt_usd, 1)
        
        # Time features
        hour_of_day = target_dt.hour
        day_of_week = target_dt.weekday()
        is_weekend = 1 if day_of_week >= 5 else 0
        is_night = 1 if 0 <= hour_of_day <= 6 else 0
        
        # Volatility - slightly lower before liquidation (market heating up)
        collat_vol = liquidation.get('collateral_volatility_24h', 0.03)
        if pd.isna(collat_vol): collat_vol = 0.03
        collat_vol = collat_vol * (1 - hours_before * 0.001)
        
        # Whale activity score
        whale_score = liquidation.get('whale_activity_score', 0.01)
        if pd.isna(whale_score): whale_score = 0.01
        
        # Market volatility regime
        vol_regime = liquidation.get('market_volatility_regime', 'medium')
        if pd.isna(vol_regime): vol_regime = 'medium'
        
        # Oracle deviation
        oracle_dev = liquidation.get('oracle_deviation', 0)
        if pd.isna(oracle_dev): oracle_dev = 0
        # Oracle deviation was smaller before
        oracle_dev = oracle_dev / max(1, hours_before * 0.1)
        
        # Time to liquidation
        ttl_minutes = None if label == 1 else hours_before * 60
        
        sample = {
            'user_address': liquidation.get('user_address', ''),
            'liquidation_id': liquidation.get('liquidation_id', ''),
            'reserve_symbol': liquidation.get('collateral_symbol', 'UNKNOWN'),
            'sample_timestamp': target_timestamp,
            'sample_datetime': target_dt,
            'liquidation_timestamp': liq_timestamp,
            'time_offset_label': time_label,
            'time_to_liquidation_minutes': ttl_minutes,
            'label': label,
            
            # Position state at this moment
            'collateral_usd': round(collateral_usd, 2),
            'debt_usd': round(debt_usd, 2),
            'health_factor': round(hf, 4),
            'collateral_to_debt_ratio': round(cdr, 4),
            
            # Volatility
            'collateral_volatility_24h': round(collat_vol, 4),
            
            # Market conditions
            'market_volatility_regime': vol_regime,
            'whale_activity_score': round(whale_score, 6),
            'oracle_deviation': round(oracle_dev, 6),
            
            # Velocity (from original liquidation - used as context)
            'health_factor_velocity_1h': round(hf_velocity_1h, 6),
            'health_factor_velocity_4h': round(hf_velocity_4h, 6),
            'health_factor_velocity_24h': round(hf_velocity_24h, 6),
            
            # Time features
            'hour_of_day': hour_of_day,
            'day_of_week': day_of_week,
            'is_weekend': is_weekend,
            'is_night': is_night,
            
            # Original liquidation features for reference
            'liquidation_health_factor': round(hf_at_liq, 4),
            'collateral_liquidation_threshold': liquidation.get('collateral_liquidation_threshold', 0.85),
            'collateral_base_ltv': liquidation.get('collateral_base_ltv', 0.75),
        }
        
        return sample
        
    except Exception as e:
        print(f"Error building sample for {liquidation.get('liquidation_id', 'unknown')}: {e}")
        return None


def build_dataset(max_liquidations: Optional[int] = None):
    """Build complete temporal dataset."""
    print("="*70)
    print("BUILDING TEMPORAL DATASET")
    print("="*70)
    
    # Step 1: Load cached liquidations
    liquidations_df = load_cached_liquidations()
    
    if max_liquidations:
        liquidations_df = liquidations_df.head(max_liquidations)
        print(f"Using first {len(liquidations_df):,} liquidations")
    
    # Step 2: Build temporal samples for each
    print(f"\nBuilding {len(TIME_OFFSETS)} samples per liquidation...")
    print(f"Target: {len(liquidations_df) * len(TIME_OFFSETS):,} total samples")
    all_samples = []
    
    for i, (_, liq) in enumerate(liquidations_df.iterrows()):
        if i % 1000 == 0 and i > 0:
            print(f"  Processed {i:,}/{len(liquidations_df):,} liquidations... ({len(all_samples):,} samples so far)")
        
        for offset_seconds, label, time_label in TIME_OFFSETS:
            sample = build_temporal_sample(liq, offset_seconds, label, time_label)
            if sample:
                all_samples.append(sample)
    
    print(f"\n✅ Total samples generated: {len(all_samples):,}")
    
    # Step 3: Convert to DataFrame
    df = pd.DataFrame(all_samples)
    
    # Statistics
    print("\n" + "="*70)
    print("DATASET STATISTICS")
    print("="*70)
    print(f"Total samples: {len(df):,}")
    print(f"Unique liquidations: {df['liquidation_id'].nunique():,}")
    
    pos_count = (df['label'] == 1).sum()
    neg_count = (df['label'] == 0).sum()
    print(f"Positive (liquidated): {pos_count:,} ({pos_count/len(df):.1%})")
    print(f"Negative (survived): {neg_count:,} ({neg_count/len(df):.1%})")
    
    print(f"\nBy time offset:")
    offset_counts = df.groupby('time_offset_label').size()
    for offset, count in offset_counts.items():
        print(f"  {offset}: {count:,}")
    
    print(f"\nLabel distribution by offset:")
    label_by_offset = df.groupby(['time_offset_label', 'label']).size().unstack(fill_value=0)
    print(label_by_offset)
    
    print(f"\nHealth factor statistics:")
    print(df['health_factor'].describe())
    
    print(f"\nCollateral USD statistics:")
    print(df['collateral_usd'].describe())
    
    print(f"\nDebt USD statistics:")
    print(df['debt_usd'].describe())
    
    # Check date range
    min_dt = df['sample_datetime'].min()
    max_dt = df['sample_datetime'].max()
    print(f"\nDate range: {min_dt} to {max_dt}")
    
    # Save
    output_file = '/home/mobra/protocol/data/aave_temporal_dataset.parquet'
    df.to_parquet(output_file, index=False, compression='snappy')
    print(f"\n✅ Saved full dataset to: {output_file}")
    print(f"   File size: {os.path.getsize(output_file) / (1024*1024):.1f} MB")
    
    # Save CSV sample
    csv_file = '/home/mobra/protocol/data/aave_temporal_dataset_sample.csv'
    sample_size = min(10000, len(df))
    df.head(sample_size).to_csv(csv_file, index=False)
    print(f"✅ Saved sample ({sample_size:,} rows) to: {csv_file}")
    
    # Save statistics
    stats = {
        'total_samples': int(len(df)),
        'unique_liquidations': int(df['liquidation_id'].nunique()),
        'positive_samples': int(pos_count),
        'negative_samples': int(neg_count),
        'samples_per_liquidation': len(TIME_OFFSETS),
        'time_offsets': [t[2] for t in TIME_OFFSETS],
        'offset_counts': {k: int(v) for k, v in offset_counts.items()},
        'health_factor_mean': float(df['health_factor'].mean()),
        'health_factor_std': float(df['health_factor'].std()),
        'date_range': {'min': str(min_dt), 'max': str(max_dt)},
        'columns': list(df.columns),
    }
    
    stats_file = '/home/mobra/protocol/data/aave_temporal_dataset_stats.json'
    with open(stats_file, 'w') as f:
        json.dump(stats, f, indent=2, default=str)
    print(f"✅ Saved statistics to: {stats_file}")
    
    return df


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Build temporal dataset for liquidation prediction')
    parser.add_argument('--max-liquidations', type=int, default=None, 
                        help='Maximum number of liquidations to process (default: all)')
    args = parser.parse_args()
    
    build_dataset(max_liquidations=args.max_liquidations)
