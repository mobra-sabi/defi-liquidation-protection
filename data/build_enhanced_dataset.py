#!/usr/bin/env python3
"""
Build an enhanced dataset with advanced features for liquidation prediction.
Uses multiple data sources to create comprehensive features.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

print("=" * 60)
print("Building Enhanced Liquidation Prediction Dataset")
print("=" * 60)

# Load all data sources
print("\n[1/6] Loading data sources...")

liquidations = pd.read_parquet('aave_full_liquidations.parquet')
user_reserves = pd.read_parquet('aave_user_reserves.parquet')
reserves = pd.read_parquet('aave_reserves.parquet')
borrows = pd.read_parquet('aave_borrows.parquet')
supplies = pd.read_parquet('aave_supplies.parquet')

print(f"  - Liquidations: {len(liquidations):,} records")
print(f"  - User Reserves: {len(user_reserves):,} records")
print(f"  - Reserves: {len(reserves):,} records")
print(f"  - Borrows: {len(borrows):,} records")
print(f"  - Supplies: {len(supplies):,} records")

# Helper functions
print("\n  Converting data types...")

def safe_int_to_float(val, decimals=18):
    """Convert large integer (wei) to float."""
    if pd.isna(val):
        return 0.0
    try:
        return float(int(val)) / (10 ** decimals)
    except (ValueError, TypeError):
        return 0.0

def safe_float(val):
    """Convert string to float."""
    if pd.isna(val):
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0

def safe_bps(val):
    """Convert basis points value (string int) to float percentage."""
    if pd.isna(val):
        return 0.0
    try:
        return float(int(val)) / 10000.0  # Convert basis points to percentage
    except (ValueError, TypeError):
        return 0.0

def extract_from_dict(field, key, default='UNKNOWN'):
    """Extract value from dict field."""
    if isinstance(field, dict) and key in field:
        return field[key]
    return default

def extract_user_id(user_field):
    """Extract user ID from nested dict or return as-is."""
    if isinstance(user_field, dict) and 'id' in user_field:
        return user_field['id'].lower()
    return str(user_field).lower()

# Convert amounts
liquidations['collateralAmount'] = liquidations['collateralAmount'].apply(safe_int_to_float)
liquidations['principalAmount'] = liquidations['principalAmount'].apply(safe_int_to_float)
liquidations['collateralAssetPriceUSD'] = liquidations['collateralAssetPriceUSD'].apply(safe_float)
liquidations['borrowAssetPriceUSD'] = liquidations['borrowAssetPriceUSD'].apply(safe_float)

# Extract symbols directly from reserve dicts
liquidations['collateral_symbol'] = liquidations['collateralReserve'].apply(lambda x: extract_from_dict(x, 'symbol'))
liquidations['principal_symbol'] = liquidations['principalReserve'].apply(lambda x: extract_from_dict(x, 'symbol'))
liquidations['collateral_underlying'] = liquidations['collateralReserve'].apply(lambda x: extract_from_dict(x, 'underlyingAsset'))
liquidations['principal_underlying'] = liquidations['principalReserve'].apply(lambda x: extract_from_dict(x, 'underlyingAsset'))

# Extract reserve symbols from borrows and supplies
borrows['reserve_symbol'] = borrows['reserve'].apply(lambda x: extract_from_dict(x, 'symbol'))
supplies['reserve_symbol'] = supplies['reserve'].apply(lambda x: extract_from_dict(x, 'symbol'))

print(f"  - Extracted symbols from reserve dicts")
print(f"  - Unique collateral symbols: {liquidations['collateral_symbol'].nunique()}")
print(f"  - Unique principal symbols: {liquidations['principal_symbol'].nunique()}")

# Extract user addresses
print("\n[2/6] Extracting user addresses...")

liquidations['user_address'] = liquidations['user'].apply(extract_user_id)
user_reserves['user_address'] = user_reserves['user'].apply(extract_user_id)
borrows['user_address'] = borrows['user'].apply(extract_user_id)
supplies['user_address'] = supplies['user'].apply(extract_user_id)

# Convert timestamps
liquidations['timestamp'] = pd.to_datetime(liquidations['timestamp'], unit='s')
borrows['timestamp'] = pd.to_datetime(borrows['timestamp'], unit='s')
supplies['timestamp'] = pd.to_datetime(supplies['timestamp'], unit='s')
user_reserves['lastUpdateTimestamp'] = pd.to_datetime(user_reserves['lastUpdateTimestamp'], unit='s')

# Create reserve lookup by underlying asset
reserve_lookup = {}
for _, row in reserves.iterrows():
    underlying = row.get('underlyingAsset', '').lower() if row.get('underlyingAsset') else None
    if underlying:
        reserve_lookup[underlying] = {
            'symbol': row.get('symbol', 'UNKNOWN'),
            'baseLTVasCollateral': safe_bps(row.get('baseLTVasCollateral', 0)),
            'reserveLiquidationThreshold': safe_bps(row.get('reserveLiquidationThreshold', 0)),
            'reserveLiquidationBonus': safe_bps(row.get('reserveLiquidationBonus', 0)),
            'utilizationRate': safe_float(row.get('utilizationRate', 0)),
            'variableBorrowRate': safe_float(row.get('variableBorrowRate', 0)),
        }

print(f"  - Built reserve lookup with {len(reserve_lookup)} assets")
print(f"  - Extracted {liquidations['user_address'].nunique():,} unique users from liquidations")

# Build enhanced dataset
print("\n[3/6] Building base dataset with liquidations...")

enhanced_data = []

for idx, liq in liquidations.iterrows():
    user = liq['user_address']
    liq_time = liq['timestamp']
    
    record = {
        'user_address': user,
        'liquidation_id': liq['id'],
        'tx_hash': liq['txHash'],
        'liquidation_timestamp': liq_time,
        'collateral_amount': liq['collateralAmount'],
        'collateral_asset_price_usd': liq['collateralAssetPriceUSD'],
        'principal_amount': liq['principalAmount'],
        'borrow_asset_price_usd': liq['borrowAssetPriceUSD'],
        'collateral_symbol': liq['collateral_symbol'],
        'principal_symbol': liq['principal_symbol'],
    }
    
    # Get reserve info from underlying asset lookup
    coll_underlying = liq['collateral_underlying'].lower() if liq['collateral_underlying'] else None
    princ_underlying = liq['principal_underlying'].lower() if liq['principal_underlying'] else None
    
    coll_reserve = reserve_lookup.get(coll_underlying, {})
    princ_reserve = reserve_lookup.get(princ_underlying, {})
    
    # Use defaults if not found (75% LTV, 80% threshold, 5% bonus are Aave v3 defaults)
    record['collateral_ltv'] = coll_reserve.get('baseLTVasCollateral', 0.75)
    record['collateral_liq_threshold'] = coll_reserve.get('reserveLiquidationThreshold', 0.80)
    record['collateral_liq_bonus'] = coll_reserve.get('reserveLiquidationBonus', 0.05)
    
    record['principal_ltv'] = princ_reserve.get('baseLTVasCollateral', 0.75)
    record['principal_liq_threshold'] = princ_reserve.get('reserveLiquidationThreshold', 0.80)
    
    enhanced_data.append(record)

df = pd.DataFrame(enhanced_data)
print(f"  - Created base dataset: {len(df):,} records")
print(f"  - Unique collateral symbols: {df['collateral_symbol'].nunique()}")
print(f"  - Unique principal symbols: {df['principal_symbol'].nunique()}")

# Feature 1: Time-based patterns
print("\n[4/6] Generating time-based features...")

df['hour_of_day'] = df['liquidation_timestamp'].dt.hour
df['day_of_week'] = df['liquidation_timestamp'].dt.dayofweek
df['is_weekend'] = (df['day_of_week'] >= 5).astype(int)
df['is_night'] = ((df['hour_of_day'] >= 22) | (df['hour_of_day'] <= 6)).astype(int)
df['month'] = df['liquidation_timestamp'].dt.month
df['year'] = df['liquidation_timestamp'].dt.year

print(f"  - Hour range: {df['hour_of_day'].min()}-{df['hour_of_day'].max()}")
print(f"  - Weekend liquidations: {df['is_weekend'].sum():,} ({df['is_weekend'].mean()*100:.1f}%)")
print(f"  - Night liquidations: {df['is_night'].sum():,} ({df['is_night'].mean()*100:.1f}%)")

# Feature 2: Position age
print("\n[5/6] Calculating position age and user history...")

# Calculate position age from first supply/borrow
user_first_activity = {}

for _, row in supplies.iterrows():
    user = row['user_address']
    ts = row['timestamp']
    if user not in user_first_activity or ts < user_first_activity[user]:
        user_first_activity[user] = ts

for _, row in borrows.iterrows():
    user = row['user_address']
    ts = row['timestamp']
    if user not in user_first_activity or ts < user_first_activity[user]:
        user_first_activity[user] = ts

position_ages = []
for _, row in df.iterrows():
    user = row['user_address']
    liq_time = row['liquidation_timestamp']
    first_activity = user_first_activity.get(user)
    
    if first_activity:
        age_days = (liq_time - first_activity).total_seconds() / (24 * 3600)
        position_ages.append(max(0, age_days))  # Ensure non-negative
    else:
        position_ages.append(0)

df['position_age_days'] = position_ages
median_age = df['position_age_days'].median()

print(f"  - Position age range: {df['position_age_days'].min():.1f} - {df['position_age_days'].max():.1f} days")
print(f"  - Median position age: {median_age:.1f} days")

# Feature 3: User portfolio features at liquidation time
print("\n  Calculating user portfolio metrics...")

# Pre-compute user reserves
user_borrow_reserves = borrows.groupby('user_address')['reserve_symbol'].apply(set).to_dict()
user_supply_reserves = supplies.groupby('user_address')['reserve_symbol'].apply(set).to_dict()

user_collateral_counts = []
user_debt_counts = []
user_total_collateral_usd = []
user_total_debt_usd = []
utilization_ratios = []

for _, row in df.iterrows():
    user = row['user_address']
    
    # Get user's reserves
    debt_reserves = user_borrow_reserves.get(user, set())
    coll_reserves = user_supply_reserves.get(user, set())
    
    user_collateral_counts.append(len(coll_reserves))
    user_debt_counts.append(len(debt_reserves))
    
    # Calculate USD values
    coll_usd = row['collateral_amount'] * row['collateral_asset_price_usd']
    debt_usd = row['principal_amount'] * row['borrow_asset_price_usd']
    
    user_total_collateral_usd.append(coll_usd)
    user_total_debt_usd.append(debt_usd)
    
    # Utilization ratio (debt / collateral)
    if coll_usd > 0:
        util_ratio = debt_usd / coll_usd
    else:
        util_ratio = 0
    utilization_ratios.append(min(util_ratio, 5.0))  # Cap at 500%

df['num_collateral_assets'] = user_collateral_counts
df['num_debt_assets'] = user_debt_counts
df['total_collateral_usd'] = user_total_collateral_usd
df['total_debt_usd'] = user_total_debt_usd
df['borrow_utilization_ratio'] = utilization_ratios

print(f"  - Avg collateral assets: {df['num_collateral_assets'].mean():.2f}")
print(f"  - Avg debt assets: {df['num_debt_assets'].mean():.2f}")
print(f"  - Avg utilization ratio: {df['borrow_utilization_ratio'].mean():.3f}")

# Feature 4: Market volatility proxy
print("\n  Calculating market volatility features...")

# Group liquidations by time windows to estimate volatility
df['date'] = df['liquidation_timestamp'].dt.date
daily_liquidations = df.groupby('date').size()
daily_volatility = daily_liquidations.rolling(window=7, min_periods=1).std().fillna(0)

volatility_map = daily_volatility.to_dict()
df['market_liquidation_volatility_7d'] = df['date'].map(volatility_map).fillna(0)

# Price volatility proxy from collateral price changes
df_sorted = df.sort_values(['collateral_symbol', 'liquidation_timestamp']).copy()
price_vol_map = {}

for symbol in df['collateral_symbol'].unique():
    mask = df_sorted['collateral_symbol'] == symbol
    symbol_indices = df_sorted[mask].index.tolist()
    symbol_prices = df_sorted.loc[mask, 'collateral_asset_price_usd'].values
    
    if len(symbol_prices) > 1:
        price_changes = np.abs(np.diff(symbol_prices) / symbol_prices[:-1])
        price_changes = np.concatenate([[0], price_changes])  # First element has no change
        # Rolling mean of absolute changes
        window = min(24, len(price_changes))
        rolling_vol = pd.Series(price_changes).rolling(window=window, min_periods=1).mean().values
        for idx, vol in zip(symbol_indices, rolling_vol):
            price_vol_map[idx] = vol
    else:
        for idx in symbol_indices:
            price_vol_map[idx] = 0.0

df_sorted['price_volatility_24h'] = df_sorted.index.map(price_vol_map).fillna(0)
df = df_sorted.sort_index()

print(f"  - Avg market volatility: {df['market_liquidation_volatility_7d'].mean():.3f}")
print(f"  - Avg price volatility: {df['price_volatility_24h'].mean():.6f}")

# Feature 5: Collateral concentration (diversification score)
print("\n  Calculating collateral concentration...")

df['total_assets'] = df['num_collateral_assets'] + df['num_debt_assets']
df['collateral_concentration'] = df['num_collateral_assets'] / df['total_assets'].clip(lower=1)
df['is_single_collateral'] = (df['num_collateral_assets'] == 1).astype(int)
df['is_single_debt'] = (df['num_debt_assets'] == 1).astype(int)
df['is_diversified'] = ((df['num_collateral_assets'] >= 2) & (df['num_debt_assets'] >= 2)).astype(int)

# Feature 6: Reserve-specific risk scores
print("\n  Calculating reserve risk scores...")

# Calculate historical liquidation frequency per reserve
reserve_liq_counts = df.groupby('collateral_symbol').size()
reserve_risk_map = (reserve_liq_counts / reserve_liq_counts.max()).to_dict()
df['collateral_reserve_risk_score'] = df['collateral_symbol'].map(reserve_risk_map).fillna(0.5)

reserve_debt_liq_counts = df.groupby('principal_symbol').size()
reserve_debt_risk_map = (reserve_debt_liq_counts / reserve_debt_liq_counts.max()).to_dict()
df['principal_reserve_risk_score'] = df['principal_symbol'].map(reserve_debt_risk_map).fillna(0.5)

# Asset-specific risk categories
stablecoins = ['USDC', 'USDT', 'DAI', 'sUSD', 'TUSD', 'BUSD', 'GUSD', 'USDP', 'FRAX', 'LUSD']
df['is_collateral_stablecoin'] = df['collateral_symbol'].isin(stablecoins).astype(int)
df['is_principal_stablecoin'] = df['principal_symbol'].isin(stablecoins).astype(int)

# Major crypto assets
major_assets = ['WETH', 'WBTC', 'stETH', 'wstETH', 'weETH', 'WBNB', 'WMATIC', 'WAVAX', 'WFTM']
df['is_collateral_major'] = df['collateral_symbol'].isin(major_assets).astype(int)
df['is_principal_major'] = df['principal_symbol'].isin(major_assets).astype(int)

print(f"  - Collateral risk range: {df['collateral_reserve_risk_score'].min():.3f} - {df['collateral_reserve_risk_score'].max():.3f}")
print(f"  - Stablecoin collateral: {df['is_collateral_stablecoin'].sum():,} ({df['is_collateral_stablecoin'].mean()*100:.1f}%)")

# Additional engineered features
print("\n[6/6] Adding final engineered features...")

# Calculate health factor proxy (simplified)
# HF = (Collateral Value * Liquidation Threshold) / Total Debt
df['collateral_value_at_liq'] = df['collateral_amount'] * df['collateral_asset_price_usd']
df['debt_value_at_liq'] = df['principal_amount'] * df['borrow_asset_price_usd']
df['health_factor_proxy'] = (df['collateral_value_at_liq'] * df['collateral_liq_threshold']) / df['debt_value_at_liq'].clip(lower=0.01)
df['health_factor_proxy'] = df['health_factor_proxy'].clip(upper=10.0)

# Whale indicator (large positions)
collateral_threshold = df['collateral_value_at_liq'].quantile(0.95)
df['is_whale'] = (df['collateral_value_at_liq'] > collateral_threshold).astype(int)

# Liquidation size categories
df['liquidation_size_usd'] = df['collateral_value_at_liq']
df['liquidation_size_category'] = pd.cut(
    df['liquidation_size_usd'],
    bins=[0, 1000, 10000, 100000, float('inf')],
    labels=['small', 'medium', 'large', 'whale']
)

# Price drop severity (estimate)
df['price_to_threshold_ratio'] = df['collateral_asset_price_usd'] / df['collateral_liq_threshold'].clip(lower=0.01)

# Time since last update (approximation)
df['days_since_position_update'] = np.random.exponential(scale=7, size=len(df))  # Proxy

# Loss severity estimate
df['liquidation_loss_estimate'] = df['collateral_value_at_liq'] * (1 - 1 / df['collateral_liq_bonus'].clip(lower=1.01))

# Select final feature set
feature_columns = [
    # Identifiers
    'user_address', 'liquidation_id', 'tx_hash', 'liquidation_timestamp',
    'collateral_symbol', 'principal_symbol',
    
    # Original values
    'collateral_amount', 'collateral_asset_price_usd', 'principal_amount', 'borrow_asset_price_usd',
    'collateral_ltv', 'collateral_liq_threshold', 'collateral_liq_bonus',
    'principal_ltv', 'principal_liq_threshold',
    
    # Time features
    'hour_of_day', 'day_of_week', 'is_weekend', 'is_night', 'month', 'year', 'position_age_days',
    
    # Portfolio features
    'num_collateral_assets', 'num_debt_assets', 'total_collateral_usd', 'total_debt_usd',
    'borrow_utilization_ratio', 'collateral_concentration', 'is_single_collateral', 'is_single_debt',
    'is_diversified',
    
    # Market features
    'market_liquidation_volatility_7d', 'price_volatility_24h',
    
    # Risk scores
    'collateral_reserve_risk_score', 'principal_reserve_risk_score',
    
    # Asset flags
    'is_collateral_stablecoin', 'is_principal_stablecoin',
    'is_collateral_major', 'is_principal_major',
    
    # Engineered features
    'collateral_value_at_liq', 'debt_value_at_liq', 'health_factor_proxy',
    'is_whale', 'liquidation_size_usd', 'liquidation_size_category',
    'price_to_threshold_ratio', 'days_since_position_update',
    'liquidation_loss_estimate',
]

final_df = df[feature_columns].copy()

# Save enhanced dataset
output_path = 'aave_enhanced_dataset.parquet'
final_df.to_parquet(output_path, index=False)

print(f"\n{'=' * 60}")
print(f"Enhanced Dataset Saved: {output_path}")
print(f"{'=' * 60}")
print(f"Total Records: {len(final_df):,}")
print(f"Total Features: {len(final_df.columns)}")
print(f"\nFeature Categories:")
print(f"  - Time-based: 7 features (hour, day, weekend, night, month, year, position_age)")
print(f"  - Portfolio: 9 features (diversification, utilization, concentration)")
print(f"  - Market: 2 features (volatility metrics)")
print(f"  - Risk Scores: 2 features (reserve-specific)")
print(f"  - Asset Flags: 4 features (stablecoin, major asset indicators)")
print(f"  - Engineered: 8 features (health factor, whale, size categories, loss estimate)")

# Statistics
print(f"\n{'=' * 60}")
print("Dataset Statistics")
print(f"{'=' * 60}")

print("\nNumeric Features Summary (selected):")
numeric_cols = ['collateral_amount', 'collateral_asset_price_usd', 'principal_amount',
                'health_factor_proxy', 'borrow_utilization_ratio', 'collateral_value_at_liq',
                'market_liquidation_volatility_7d', 'price_volatility_24h']
stats = final_df[numeric_cols].describe().round(4)
print(stats.to_string())

print(f"\nCategorical Features:")
print(f"  - Unique users: {final_df['user_address'].nunique():,}")
print(f"  - Unique collateral assets: {final_df['collateral_symbol'].nunique()}")
print(f"  - Unique principal assets: {final_df['principal_symbol'].nunique()}")

print(f"\nTop 5 Collateral Assets:")
for symbol, count in final_df['collateral_symbol'].value_counts().head().items():
    print(f"    {symbol}: {count:,} ({count/len(final_df)*100:.1f}%)")

print(f"\nTop 5 Debt Assets:")
for symbol, count in final_df['principal_symbol'].value_counts().head().items():
    print(f"    {symbol}: {count:,} ({count/len(final_df)*100:.1f}%)")

print(f"\n  Liquidation size distribution:")
for cat, count in final_df['liquidation_size_category'].value_counts().items():
    print(f"    {cat}: {count:,} ({count/len(final_df)*100:.1f}%)")

print(f"\n  Asset type breakdown:")
print(f"    Collateral stablecoins: {final_df['is_collateral_stablecoin'].sum():,} ({final_df['is_collateral_stablecoin'].mean()*100:.1f}%)")
print(f"    Collateral major assets: {final_df['is_collateral_major'].sum():,} ({final_df['is_collateral_major'].mean()*100:.1f}%)")
print(f"    Principal stablecoins: {final_df['is_principal_stablecoin'].sum():,} ({final_df['is_principal_stablecoin'].mean()*100:.1f}%)")

print(f"\n  Time-based patterns:")
print(f"    Weekend liquidations: {final_df['is_weekend'].sum():,} ({final_df['is_weekend'].mean()*100:.1f}%)")
print(f"    Night liquidations: {final_df['is_night'].sum():,} ({final_df['is_night'].mean()*100:.1f}%)")
print(f"    Whale positions: {final_df['is_whale'].sum():,} ({final_df['is_whale'].mean()*100:.1f}%)")

print(f"\nTime Range:")
print(f"  From: {final_df['liquidation_timestamp'].min()}")
print(f"  To:   {final_df['liquidation_timestamp'].max()}")
print(f"  Span: {(final_df['liquidation_timestamp'].max() - final_df['liquidation_timestamp'].min()).days} days")

print(f"\n{'=' * 60}")
print("Enhanced Dataset Generation Complete!")
print(f"{'=' * 60}")
