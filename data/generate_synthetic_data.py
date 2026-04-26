#!/usr/bin/env python3
"""
Synthetic Liquidation Data Generator

Generates realistic synthetic liquidation data for testing the AI pipeline
without requiring TheGraph API access.

This is useful for:
1. Testing the data processing pipeline
2. Developing and validating the ML models
3. Benchmarking GPU performance
4. Integration testing

The synthetic data mimics real Aave V3 liquidation patterns with realistic:
- Health factor distributions
- Collateral/debt value ratios
- Volatility patterns
- Time-based patterns

Usage:
    python generate_synthetic_data.py --num-events 50000 --output synthetic_liquidations.parquet
"""

import os
import json
import logging
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()

# Configuration
OUTPUT_DIR = Path(__file__).parent
DEFAULT_NUM_EVENTS = 50000
DEFAULT_DAYS = 90

# Asset configurations (similar to real Aave V3 markets)
ASSETS = {
    'WETH': {'decimals': 18, 'base_price': 3500, 'volatility': 0.03},
    'WBTC': {'decimals': 8, 'base_price': 65000, 'volatility': 0.025},
    'USDC': {'decimals': 6, 'base_price': 1.0, 'volatility': 0.001},
    'USDT': {'decimals': 6, 'base_price': 1.0, 'volatility': 0.001},
    'DAI': {'decimals': 18, 'base_price': 1.0, 'volatility': 0.001},
    'LINK': {'decimals': 18, 'base_price': 15, 'volatility': 0.04},
    'AAVE': {'decimals': 18, 'base_price': 150, 'volatility': 0.05},
    'UNI': {'decimals': 18, 'base_price': 8, 'volatility': 0.045},
}

# Collateral/Debt pairs (realistic combinations)
COLLATERAL_DEBT_PAIRS = [
    ('WETH', 'USDC'),
    ('WETH', 'USDT'),
    ('WETH', 'DAI'),
    ('WBTC', 'USDC'),
    ('WBTC', 'USDT'),
    ('WBTC', 'DAI'),
    ('LINK', 'USDC'),
    ('AAVE', 'USDC'),
    ('WETH', 'WBTC'),  # Rare but happens
]


def generate_random_address() -> str:
    """Generate a random Ethereum address."""
    return '0x' + ''.join(np.random.choice(list('0123456789abcdef'), 40))


def generate_liquidation_event(
    timestamp: datetime,
    event_id: int,
    rng: Optional[np.random.Generator] = None
) -> Dict:
    """Generate a single synthetic liquidation event."""
    if rng is None:
        rng = np.random.default_rng()

    # Select collateral/debt pair
    collateral_symbol, debt_symbol = rng.choice(COLLATERAL_DEBT_PAIRS)
    collateral_asset = ASSETS[collateral_symbol]
    debt_asset = ASSETS[debt_symbol]

    # Generate prices with some randomness
    collateral_price = collateral_asset['base_price'] * (1 + rng.normal(0, collateral_asset['volatility']))
    debt_price = debt_asset['base_price'] * (1 + rng.normal(0, debt_asset['volatility']))

    # Generate position values
    # Larger positions are rarer (power law distribution)
    position_size_usd = np.exp(rng.normal(12, 1.5))  # Log-normal, median around $160k

    # Collateral amount (typically 1.1-1.5x the debt)
    collateral_ratio = rng.uniform(1.1, 1.5)
    collateral_value_usd = position_size_usd * collateral_ratio
    collateral_amount_raw = int(collateral_value_usd / collateral_price * (10 ** collateral_asset['decimals']))

    # Debt amount
    debt_value_usd = position_size_usd
    debt_amount_raw = int(debt_value_usd / debt_price * (10 ** debt_asset['decimals']))

    # Liquidated collateral (typically 50-100% of collateral)
    liquidation_ratio = rng.beta(3, 2)  # Skewed towards higher values
    liquidated_collateral_raw = int(collateral_amount_raw * liquidation_ratio)

    # Calculate health factor at liquidation (typically 0.95-1.0)
    health_factor = rng.uniform(0.92, 0.98)

    # Generate volatility for both assets
    collateral_vol = rng.uniform(0.01, 0.08)
    debt_vol = rng.uniform(0.001, 0.005)

    # Time features
    hour_of_day = timestamp.hour
    day_of_week = timestamp.weekday()
    is_weekend = day_of_week >= 5

    # Generate addresses
    user_address = generate_random_address()
    liquidator = generate_random_address()
    tx_hash = '0x' + ''.join(rng.choice(list('0123456789abcdef'), 64))

    return {
        'liquidation_id': f'{timestamp.strftime("%Y%m%d")}-{event_id:06d}',
        'tx_hash': tx_hash,
        'timestamp': int(timestamp.timestamp()),
        'datetime': timestamp,
        'block_number': int(18000000 + (timestamp - datetime(2023, 1, 1)).total_seconds() / 12),
        'user_address': user_address,
        'liquidator': liquidator,

        # Collateral details
        'collateral_asset': generate_random_address(),
        'collateral_symbol': collateral_symbol,
        'collateral_decimals': collateral_asset['decimals'],
        'collateral_price_usd': round(collateral_price, 2),

        # Debt details
        'debt_asset': generate_random_address(),
        'debt_symbol': debt_symbol,
        'debt_decimals': debt_asset['decimals'],
        'debt_price_usd': round(debt_price, 4),

        # Amounts
        'collateral_amount_raw': collateral_amount_raw,
        'debt_amount_raw': debt_amount_raw,
        'liquidated_collateral_amount': liquidated_collateral_raw,

        # USD values
        'collateral_amount_usd': round(collateral_value_usd, 2),
        'debt_amount_usd': round(debt_value_usd, 2),
        'liquidated_collateral_usd': round(liquidated_collateral_raw / (10 ** collateral_asset['decimals']) * collateral_price, 2),

        # Risk metrics
        'health_factor_at_liquidation': round(health_factor, 4),
        'collateral_volatility_24h': round(collateral_vol, 4),
        'debt_volatility_24h': round(debt_vol, 4),

        # Time features
        'hour_of_day': hour_of_day,
        'day_of_week': day_of_week,
        'is_weekend': is_weekend,

        # Reserve parameters (synthetic)
        'collateral_liquidation_threshold': round(rng.uniform(0.75, 0.85), 4),
        'collateral_base_ltv': round(rng.uniform(0.70, 0.80), 4),
        'debt_liquidity_rate': round(rng.uniform(0.01, 0.05), 6),
        'debt_variable_rate': round(rng.uniform(0.02, 0.08), 6),

        # Metadata
        'is_synthetic': True,
        'synthetic_version': '1.0',
    }


def generate_dataset(
    num_events: int = DEFAULT_NUM_EVENTS,
    days: int = DEFAULT_DAYS,
    output_file: Optional[str] = None,
    seed: int = 42
) -> pd.DataFrame:
    """Generate a full synthetic dataset."""
    logger.info(f"Generating {num_events} synthetic liquidation events over {days} days...")

    rng = np.random.default_rng(seed)

    # Generate timestamps
    end_time = datetime.now()
    start_time = end_time - timedelta(days=days)

    # Generate events with time clustering (liquidations often cluster during market stress)
    events = []
    current_time = start_time

    # Create some "stress periods" where more liquidations occur
    stress_periods = [
        (start_time + timedelta(days=int(rng.integers(5, days-5))), int(rng.integers(2, 6)))
        for _ in range(int(rng.integers(3, 8)))
    ]

    events_generated = 0
    while events_generated < num_events:
        # Check if we're in a stress period
        is_stress = any(
            period[0] <= current_time <= period[0] + timedelta(hours=period[1])
            for period in stress_periods
        )

        # During stress, generate more events
        if is_stress:
            num_batch = rng.integers(5, 15)
        else:
            num_batch = rng.integers(1, 4)

        for _ in range(min(num_batch, num_events - events_generated)):
            event = generate_liquidation_event(current_time, events_generated, rng)
            events.append(event)
            events_generated += 1

        # Advance time
        if is_stress:
            current_time += timedelta(minutes=int(rng.integers(1, 10)))
        else:
            current_time += timedelta(hours=int(rng.integers(1, 6)))

        if current_time > end_time:
            current_time = start_time  # Loop back (shouldn't happen with proper params)

    # Convert to DataFrame
    df = pd.DataFrame(events)

    # Add derived features for ML
    df['health_factor_velocity_1h'] = rng.normal(-0.02, 0.01, len(df))
    df['health_factor_velocity_4h'] = df['health_factor_velocity_1h'] * rng.uniform(3, 5, len(df))
    df['health_factor_velocity_24h'] = df['health_factor_velocity_1h'] * rng.uniform(15, 25, len(df))

    df['collateral_price_momentum_24h'] = rng.normal(0, 0.05, len(df))
    df['debt_utilization_ratio'] = rng.beta(5, 2, len(df))  # Skewed towards higher utilization
    df['market_volatility_regime'] = rng.choice(['low', 'medium', 'high'], len(df), p=[0.5, 0.35, 0.15])
    df['whale_activity_score'] = rng.exponential(0.3, len(df))
    df['oracle_deviation'] = rng.normal(0, 0.001, len(df))

    # Time to liquidation (target variable for ML)
    # This represents how long before the liquidation the risk was detectable
    df['time_to_liquidation_minutes'] = rng.exponential(30, len(df)) + rng.normal(5, 2, len(df))
    df['time_to_liquidation_minutes'] = df['time_to_liquidation_minutes'].clip(lower=1)

    logger.info(f"Generated {len(df)} synthetic events")
    logger.info(f"Date range: {df['datetime'].min()} to {df['datetime'].max()}")
    logger.info(f"Total value liquidated: ${df['collateral_amount_usd'].sum():,.2f}")

    return df


def save_dataset(df: pd.DataFrame, output_file: Optional[str] = None):
    """Save the dataset to disk."""
    if output_file is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = OUTPUT_DIR / f'synthetic_liquidations_{timestamp}.parquet'
    else:
        output_file = OUTPUT_DIR / output_file

    logger.info(f"Saving to {output_file}...")

    # Convert large integers to Python int to avoid overflow
    large_int_cols = ['collateral_amount_raw', 'debt_amount_raw', 'liquidated_collateral_amount']
    for col in large_int_cols:
        if col in df.columns:
            df[col] = df[col].astype('float64')  # Use float for very large numbers

    # Save as parquet
    df.to_parquet(output_file, index=False, compression='snappy')

    # Save sample as CSV for inspection
    csv_file = str(output_file).replace('.parquet', '_sample.csv')
    df.head(10000).to_csv(csv_file, index=False)

    # Save statistics
    stats = {
        'total_events': len(df),
        'synthetic': True,
        'date_range': {
            'start': df['datetime'].min().isoformat(),
            'end': df['datetime'].max().isoformat()
        },
        'total_collateral_liquidated_usd': float(df['collateral_amount_usd'].sum()),
        'total_debt_repaid_usd': float(df['debt_amount_usd'].sum()),
        'unique_users': df['user_address'].nunique(),
        'collateral_assets': df['collateral_symbol'].value_counts().to_dict(),
        'debt_assets': df['debt_symbol'].value_counts().to_dict(),
        'avg_health_factor': float(df['health_factor_at_liquidation'].mean()),
        'median_time_to_liquidation': float(df['time_to_liquidation_minutes'].median()),
        'columns': list(df.columns)
    }

    stats_file = str(output_file).replace('.parquet', '_stats.json')
    with open(stats_file, 'w') as f:
        json.dump(stats, f, indent=2, default=str)

    logger.info(f"Saved:")
    logger.info(f"  - Parquet: {output_file} ({os.path.getsize(output_file) / 1024 / 1024:.2f} MB)")
    logger.info(f"  - CSV sample: {csv_file}")
    logger.info(f"  - Stats: {stats_file}")

    return stats


def main():
    parser = argparse.ArgumentParser(
        description='Generate synthetic liquidation data for testing'
    )
    parser.add_argument(
        '--num-events',
        type=int,
        default=DEFAULT_NUM_EVENTS,
        help=f'Number of events to generate (default: {DEFAULT_NUM_EVENTS})'
    )
    parser.add_argument(
        '--days',
        type=int,
        default=DEFAULT_DAYS,
        help=f'Number of days to span (default: {DEFAULT_DAYS})'
    )
    parser.add_argument(
        '--output',
        type=str,
        default=None,
        help='Output filename (default: auto-generated)'
    )
    parser.add_argument(
        '--seed',
        type=int,
        default=42,
        help='Random seed for reproducibility (default: 42)'
    )

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("SYNTHETIC LIQUIDATION DATA GENERATOR")
    logger.info("=" * 60)
    logger.info(f"Configuration:")
    logger.info(f"  Events: {args.num_events:,}")
    logger.info(f"  Days: {args.days}")
    logger.info(f"  Seed: {args.seed}")
    logger.info("=" * 60)

    # Generate data
    df = generate_dataset(
        num_events=args.num_events,
        days=args.days,
        seed=args.seed
    )

    # Save
    stats = save_dataset(df, args.output)

    logger.info("\n" + "=" * 60)
    logger.info("GENERATION COMPLETE")
    logger.info("=" * 60)
    logger.info(f"\nDataset statistics:")
    logger.info(f"  Total events: {stats['total_events']:,}")
    logger.info(f"  Total value: ${stats['total_collateral_liquidated_usd']:,.2f}")
    logger.info(f"  Median time to liquidation: {stats['median_time_to_liquidation']:.1f} minutes")
    logger.info(f"  Avg health factor: {stats['avg_health_factor']:.4f}")
    logger.info(f"\nNext steps:")
    logger.info(f"  1. Review sample data: data/synthetic_liquidations_sample.csv")
    logger.info(f"  2. Run feature engineering: python feature_engineering.py")
    logger.info(f"  3. Train model: python train_model.py")


if __name__ == '__main__':
    main()
