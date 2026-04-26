#!/usr/bin/env python3
"""
Feature Engineering Pipeline for Liquidation Prediction

Transforms raw liquidation data into ML-ready features.

Features generated:
- health_factor_velocity (1h, 4h, 24h)
- collateral_price_momentum
- debt_utilization_ratio
- market_volatility_regime
- whale_activity_score
- oracle_deviation
- time-based features

Usage:
    python feature_engineering.py --input historical_liquidations.parquet --output ml_features.parquet
"""

import os
import json
import logging
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler, LabelEncoder
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()

# Configuration
DATA_DIR = Path(__file__).parent


def calculate_health_factor_velocity(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate rate of change of health factor.
    In real implementation, this would use time-series data.
    For synthetic data, we derive from existing features.
    """
    logger.info("Calculating health factor velocity...")

    # Sort by time for each user
    df = df.sort_values(['user_address', 'timestamp'])

    # Calculate velocity features (already present in synthetic data)
    # In real data, these would be calculated from HF history
    df['hf_velocity_1h'] = df['health_factor_velocity_1h']
    df['hf_velocity_4h'] = df['health_factor_velocity_4h']
    df['hf_velocity_24h'] = df['health_factor_velocity_24h']

    # Additional derived velocity metrics
    df['hf_acceleration'] = df['hf_velocity_1h'].diff().fillna(0)
    df['hf_velocity_magnitude'] = np.sqrt(df['hf_velocity_1h']**2 + df['hf_velocity_4h']**2)

    logger.info("  ✓ Health factor velocity calculated")
    return df


def calculate_price_momentum(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate price momentum indicators."""
    logger.info("Calculating price momentum...")

    # Use existing momentum feature
    df['price_momentum_24h'] = df['collateral_price_momentum_24h']

    # Additional momentum indicators
    df['price_momentum_direction'] = np.sign(df['price_momentum_24h'])
    df['price_momentum_strength'] = np.abs(df['price_momentum_24h'])

    # Categorize momentum
    momentum_bins = [-np.inf, -0.05, -0.02, 0.02, 0.05, np.inf]
    momentum_labels = ['strong_down', 'down', 'neutral', 'up', 'strong_up']
    df['price_momentum_regime'] = pd.cut(
        df['price_momentum_24h'],
        bins=momentum_bins,
        labels=momentum_labels
    )

    logger.info("  ✓ Price momentum calculated")
    return df


def calculate_risk_ratios(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate various risk ratios."""
    logger.info("Calculating risk ratios...")

    # Debt to collateral ratio
    df['debt_collateral_ratio'] = df['debt_amount_usd'] / df['collateral_amount_usd']

    # Loan-to-value ratio
    df['ltv_ratio'] = df['debt_amount_usd'] / (df['collateral_amount_usd'] * df['collateral_base_ltv'])

    # Buffer to liquidation
    df['liquidation_buffer'] = df['health_factor_at_liquidation'] - 1.0

    # Risk score composite
    df['risk_score'] = (
        (1 - df['health_factor_at_liquidation']) * 0.4 +
        df['debt_utilization_ratio'] * 0.3 +
        df['collateral_volatility_24h'] * 5 * 0.2 +
        np.abs(df['price_momentum_24h']) * 0.1
    )

    logger.info("  ✓ Risk ratios calculated")
    return df


def encode_categorical_features(df: pd.DataFrame) -> pd.DataFrame:
    """Encode categorical features for ML."""
    logger.info("Encoding categorical features...")

    # One-hot encode asset symbols
    collateral_dummies = pd.get_dummies(df['collateral_symbol'], prefix='collateral')
    debt_dummies = pd.get_dummies(df['debt_symbol'], prefix='debt')

    # Market volatility regime encoding
    regime_mapping = {'low': 0, 'medium': 1, 'high': 2}
    df['volatility_regime_encoded'] = df['market_volatility_regime'].map(regime_mapping)

    # Price momentum regime encoding
    momentum_mapping = {
        'strong_down': -2, 'down': -1, 'neutral': 0,
        'up': 1, 'strong_up': 2
    }
    df['momentum_regime_encoded'] = df['price_momentum_regime'].map(momentum_mapping)

    # Time cyclical encoding
    df['hour_sin'] = np.sin(2 * np.pi * df['hour_of_day'] / 24)
    df['hour_cos'] = np.cos(2 * np.pi * df['hour_of_day'] / 24)
    df['day_of_week_sin'] = np.sin(2 * np.pi * df['day_of_week'] / 7)
    df['day_of_week_cos'] = np.cos(2 * np.pi * df['day_of_week'] / 7)

    # Concatenate dummies
    df = pd.concat([df, collateral_dummies, debt_dummies], axis=1)

    logger.info(f"  ✓ Categorical features encoded ({len(collateral_dummies.columns)} collateral + {len(debt_dummies.columns)} debt assets)")
    return df


def select_ml_features(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str], List[str]]:
    """
    Select final feature set for ML model.

    Returns:
        - DataFrame with selected features
        - List of feature column names
        - List of target column names
    """
    logger.info("Selecting ML feature set...")

    # Feature columns (predictors)
    feature_cols = [
        # Health factor features
        'health_factor_at_liquidation',
        'hf_velocity_1h', 'hf_velocity_4h', 'hf_velocity_24h',
        'hf_acceleration', 'hf_velocity_magnitude',

        # Price features
        'collateral_price_usd', 'debt_price_usd',
        'price_momentum_24h', 'price_momentum_strength',
        'volatility_regime_encoded', 'momentum_regime_encoded',

        # Volatility
        'collateral_volatility_24h', 'debt_volatility_24h',

        # Risk ratios
        'debt_collateral_ratio', 'ltv_ratio', 'liquidation_buffer',
        'debt_utilization_ratio', 'risk_score',

        # Whale activity
        'whale_activity_score',

        # Oracle
        'oracle_deviation',

        # Reserve parameters
        'collateral_liquidation_threshold', 'collateral_base_ltv',
        'debt_liquidity_rate', 'debt_variable_rate',

        # Time features
        'hour_sin', 'hour_cos', 'day_of_week_sin', 'day_of_week_cos',
        'is_weekend',
    ]

    # Add asset dummy columns
    asset_cols = [col for col in df.columns if col.startswith(('collateral_', 'debt_')) and col not in [
        'collateral_asset', 'collateral_symbol', 'collateral_decimals',
        'collateral_price_usd', 'collateral_amount_raw',
        'collateral_amount_usd', 'collateral_volatility_24h',
        'collateral_liquidation_threshold', 'collateral_base_ltv',
        'debt_asset', 'debt_symbol', 'debt_decimals',
        'debt_price_usd', 'debt_amount_raw', 'debt_amount_usd',
        'debt_volatility_24h', 'debt_liquidity_rate', 'debt_variable_rate'
    ]]
    feature_cols.extend(asset_cols)

    # Target columns (what we want to predict)
    target_cols = [
        'time_to_liquidation_minutes',  # Main target - how long before liquidation
    ]

    # Verify all columns exist
    available_features = [col for col in feature_cols if col in df.columns]
    available_targets = [col for col in target_cols if col in df.columns]

    missing_features = set(feature_cols) - set(df.columns)
    if missing_features:
        logger.warning(f"Missing feature columns: {missing_features}")

    # Select columns
    selected_cols = list(set(available_features + available_targets + ['liquidation_id', 'timestamp']))
    df_ml = df[selected_cols].copy()

    # Handle NaN values - fill with median for numeric columns
    df_ml = df_ml.fillna(df_ml.median(numeric_only=True))
    # Fill any remaining NaN with 0
    df_ml = df_ml.fillna(0)

    logger.info(f"  ✓ Selected {len(available_features)} features, {len(available_targets)} targets")
    logger.info(f"  ✓ Final shape: {df_ml.shape}")

    return df_ml, available_features, available_targets


def create_train_test_split(
    df: pd.DataFrame,
    features: List[str],
    target: str,
    test_size: float = 0.2,
    val_size: float = 0.1
) -> Dict:
    """Create train/validation/test splits with temporal ordering."""
    logger.info("Creating train/val/test splits...")

    # Sort by time
    df = df.sort_values('timestamp')

    n = len(df)
    test_idx = int(n * (1 - test_size))
    val_idx = int(n * (1 - test_size - val_size))

    train_df = df.iloc[:val_idx]
    val_df = df.iloc[val_idx:test_idx]
    test_df = df.iloc[test_idx:]

    splits = {
        'train': {
            'X': train_df[features].values,
            'y': train_df[target].values,
            'df': train_df
        },
        'val': {
            'X': val_df[features].values,
            'y': val_df[target].values,
            'df': val_df
        },
        'test': {
            'X': test_df[features].values,
            'y': test_df[target].values,
            'df': test_df
        }
    }

    logger.info(f"  ✓ Train: {len(train_df)} samples")
    logger.info(f"  ✓ Validation: {len(val_df)} samples")
    logger.info(f"  ✓ Test: {len(test_df)} samples")

    return splits


def save_processed_data(
    df_ml: pd.DataFrame,
    splits: Dict,
    features: List[str],
    target: str,
    output_prefix: str = "ml_ready"
):
    """Save processed data and metadata."""
    logger.info("Saving processed data...")

    output_dir = DATA_DIR / 'processed'
    output_dir.mkdir(exist_ok=True)

    # Save full dataset
    df_ml.to_parquet(output_dir / f'{output_prefix}_data.parquet', compression='snappy')

    # Save splits
    for split_name, split_data in splits.items():
        split_df = split_data['df']
        split_df.to_parquet(output_dir / f'{output_prefix}_{split_name}.parquet', compression='snappy')

    # Save metadata
    metadata = {
        'feature_columns': features,
        'target_column': target,
        'n_features': len(features),
        'dataset_sizes': {
            'total': len(df_ml),
            'train': len(splits['train']['df']),
            'val': len(splits['val']['df']),
            'test': len(splits['test']['df'])
        },
        'feature_stats': {
            col: {
                'mean': float(df_ml[col].mean()),
                'std': float(df_ml[col].std()),
                'min': float(df_ml[col].min()),
                'max': float(df_ml[col].max())
            }
            for col in features[:10]  # Save stats for first 10 features
        },
        'target_stats': {
            'mean': float(df_ml[target].mean()),
            'std': float(df_ml[target].std()),
            'min': float(df_ml[target].min()),
            'max': float(df_ml[target].max()),
            'median': float(df_ml[target].median())
        }
    }

    with open(output_dir / f'{output_prefix}_metadata.json', 'w') as f:
        json.dump(metadata, f, indent=2)

    logger.info(f"  ✓ Saved to {output_dir}")
    logger.info(f"  ✓ Metadata saved")


def main():
    parser = argparse.ArgumentParser(description='Feature Engineering Pipeline')
    parser.add_argument('--input', type=str, default='historical_liquidations.parquet',
                        help='Input parquet file')
    parser.add_argument('--output-prefix', type=str, default='ml_ready',
                        help='Output file prefix')
    parser.add_argument('--target', type=str, default='time_to_liquidation_minutes',
                        help='Target column to predict')

    args = parser.parse_args()

    logger.info("=" * 70)
    logger.info("FEATURE ENGINEERING PIPELINE")
    logger.info("=" * 70)

    # Load data
    input_path = DATA_DIR / args.input
    logger.info(f"Loading data from {input_path}...")
    df = pd.read_parquet(input_path)
    logger.info(f"Loaded {len(df)} rows, {len(df.columns)} columns")

    # Apply feature engineering
    df = calculate_health_factor_velocity(df)
    df = calculate_price_momentum(df)
    df = calculate_risk_ratios(df)
    df = encode_categorical_features(df)

    # Select ML features
    df_ml, features, targets = select_ml_features(df)

    # Create splits
    splits = create_train_test_split(df_ml, features, args.target)

    # Save
    save_processed_data(df_ml, splits, features, args.target, args.output_prefix)

    logger.info("\n" + "=" * 70)
    logger.info("FEATURE ENGINEERING COMPLETE")
    logger.info("=" * 70)
    logger.info(f"\nNext step: Train the model")
    logger.info(f"  python train_model.py --data-prefix {args.output_prefix}")


if __name__ == '__main__':
    main()
