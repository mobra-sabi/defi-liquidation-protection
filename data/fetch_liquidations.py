"""
Aave V3 Liquidation Data Collector

This script fetches historical liquidation data from Aave V3 via TheGraph API.
Target: Minimum 50,000 liquidation events with full position context.

Data collected per liquidation:
- health_factor history (30 days prior)
- collateral_value in USD
- debt_value in USD
- asset_volatility (24h std deviation)
- time_to_liquidation (target variable)

Output: data/historical_liquidations.parquet
"""

import os
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import json

import requests
import pandas as pd
import numpy as np
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('data_collection.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Configuration
# Aave V3 Subgraph URLs
#
# OPTION 1: TheGraph Network (recommended)
# URL format: https://gateway.thegraph.com/api/{API_KEY}/subgraphs/id/{SUBGRAPH_ID}
# Subgraph ID for Aave V3 Ethereum: Cd2gEDVeqnjBn1hSeqFMitw8Q1iiyV9FYUZkLNRcL87g
#
# OPTION 2: Dfuse/StreamingFast (your API key format)
# URL: https://eth.dfuse.eosnation.io/graphql (for Ethereum)
#
# OPTION 3: Hosted Service (legacy, free)
# Ethereum: https://api.thegraph.com/subgraphs/name/aave/protocol-v3

# API Key (supports multiple formats)
THEGRAPH_API_KEY = os.getenv('THEGRAPH_API_KEY', '')

# Build URL with API key
# Use configured URL directly (contains API key in path)
AAVE_V3_SUBGRAPH_URL = os.getenv(
    'AAVE_V3_SUBGRAPH_URL',
    'https://api.goldsky.com/api/public/project_clgs8gq30eo9o01ud9jt2f2c7/subgraphs/aave-v3-ethereum/3.0.0/gn'
)
REQUEST_TIMEOUT = int(os.getenv('REQUEST_TIMEOUT', '60'))
MAX_RETRIES = int(os.getenv('MAX_RETRIES', '5'))
BATCH_SIZE = int(os.getenv('BATCH_SIZE', '1000'))
DAYS_TO_FETCH = int(os.getenv('DAYS_TO_FETCH', '90'))
MIN_LIQUIDATIONS = int(os.getenv('MIN_LIQUIDATIONS', '50000'))
RATE_LIMIT_DELAY = float(os.getenv('RATE_LIMIT_DELAY', '0.1'))

# Output paths
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(OUTPUT_DIR, 'historical_liquidations.parquet')
RAW_DATA_FILE = os.path.join(OUTPUT_DIR, 'raw_liquidations.json')


class AaveDataCollector:
    """Collects liquidation data from Aave V3 subgraph."""

    def __init__(self, subgraph_url: str = AAVE_V3_SUBGRAPH_URL, api_key: str = THEGRAPH_API_KEY):
        self.subgraph_url = subgraph_url
        self.api_key = api_key
        self.session = requests.Session()
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        # Add API key if available (required for TheGraph Network)
        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'
        self.session.headers.update(headers)
        self.total_fetched = 0

    def _execute_query(self, query: str, variables: Optional[Dict] = None) -> Dict:
        """Execute GraphQL query with retry logic."""
        payload = {'query': query}
        if variables:
            payload['variables'] = variables

        for attempt in range(MAX_RETRIES):
            try:
                response = self.session.post(
                    self.subgraph_url,
                    json=payload,
                    timeout=REQUEST_TIMEOUT
                )
                response.raise_for_status()
                data = response.json()

                if 'errors' in data:
                    logger.error(f"GraphQL errors: {data['errors']}")
                    raise Exception(f"GraphQL errors: {data['errors']}")

                return data['data']

            except requests.exceptions.RequestException as e:
                logger.warning(f"Request failed (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                else:
                    raise

    def get_latest_block_timestamp(self) -> int:
        """Get the latest block timestamp from the subgraph."""
        query = """
        {
            _meta {
                block {
                    number
                    timestamp
                }
            }
        }
        """
        result = self._execute_query(query)
        return int(result['_meta']['block']['timestamp'])

    def fetch_liquidation_events(
        self,
        start_timestamp: int,
        end_timestamp: int,
        skip: int = 0
    ) -> List[Dict]:
        """Fetch liquidation events within a time range."""
        query = """
        query GetLiquidations($startTime: Int!, $endTime: Int!, $skip: Int!, $batchSize: Int!) {
            liquidationCalls(
                where: {
                    blockTimestamp_gte: $startTime
                    blockTimestamp_lte: $endTime
                }
                orderBy: blockTimestamp
                orderDirection: asc
                first: $batchSize
                skip: $skip
            ) {
                id
                txHash
                blockTimestamp
                blockNumber
                collateralAsset {
                    id
                    symbol
                    decimals
                    price {
                        priceInUSD
                    }
                }
                debtAsset {
                    id
                    symbol
                    decimals
                    price {
                        priceInUSD
                    }
                }
                user {
                    id
                }
                liquidator
                collateralAmount
                debtAmount
                liquidatedCollateralAmount
                accruedCollateralAmount
            }
        }
        """

        variables = {
            'startTime': start_timestamp,
            'endTime': end_timestamp,
            'skip': skip,
            'batchSize': BATCH_SIZE
        }

        result = self._execute_query(query, variables)
        return result.get('liquidationCalls', [])

    def fetch_user_position_history(
        self,
        user_address: str,
        collateral_asset: str,
        debt_asset: str,
        liquidation_timestamp: int
    ) -> Optional[Dict]:
        """Fetch user's position history leading up to liquidation."""
        # Look back 30 days before liquidation
        lookback_seconds = 30 * 24 * 60 * 60
        start_time = liquidation_timestamp - lookback_seconds

        query = """
        query GetUserPosition($userId: String!, $collateralId: String!, $debtId: String!,
                              $startTime: Int!, $endTime: Int!) {
            userReserves(
                where: {
                    user: $userId
                    reserve_in: [$collateralId, $debtId]
                }
                block: {number: 0}
            ) {
                reserve {
                    id
                    symbol
                    decimals
                    price {
                        priceInUSD
                    }
                }
                currentATokenBalance
                currentVariableDebt
                currentStableDebt
                scaledVariableDebt
                principalStableDebt
                stableBorrowRate
                variableBorrowRate
                liquidityRate
                usageAsCollateralEnabledOnUser
                lastUpdateTimestamp
            }
            userReservesHistoryItems(
                where: {
                    userReserve: $userId
                    timestamp_gte: $startTime
                    timestamp_lte: $endTime
                }
                orderBy: timestamp
                orderDirection: asc
            ) {
                timestamp
                currentATokenBalance
                currentVariableDebt
                currentStableDebt
                liquidityRate
                variableBorrowRate
                stableBorrowRate
            }
        }
        """

        variables = {
            'userId': user_address,
            'collateralId': collateral_asset,
            'debtId': debt_asset,
            'startTime': start_time,
            'endTime': liquidation_timestamp
        }

        try:
            result = self._execute_query(query, variables)
            return result
        except Exception as e:
            logger.warning(f"Failed to fetch position history for {user_address}: {e}")
            return None

    def fetch_reserve_data(self, asset_address: str) -> Optional[Dict]:
        """Fetch reserve data including liquidity and rates."""
        query = """
        query GetReserveData($assetId: ID!) {
            reserve(id: $assetId) {
                id
                symbol
                decimals
                liquidityRate
                variableBorrowRate
                stableBorrowRate
                totalATokenSupply
                totalCurrentVariableDebt
                totalCurrentStableDebt
                availableLiquidity
                price {
                    priceInUSD
                }
                reserveFactor
                liquidationThreshold
                liquidationBonus
                optimalUtilizationRate
                baseVariableBorrowRate
                variableRateSlope1
                variableRateSlope2
                stableRateSlope1
                stableRateSlope2
                baseLTVasCollateral
            }
        }
        """

        variables = {'assetId': asset_address}

        try:
            result = self._execute_query(query, variables)
            return result.get('reserve')
        except Exception as e:
            logger.warning(f"Failed to fetch reserve data for {asset_address}: {e}")
            return None

    def calculate_volatility(
        self,
        asset_address: str,
        end_timestamp: int,
        window_hours: int = 24
    ) -> Optional[float]:
        """Calculate price volatility (std dev) for an asset."""
        window_seconds = window_hours * 60 * 60
        start_time = end_timestamp - window_seconds

        query = """
        query GetPriceHistory($assetId: String!, $startTime: Int!, $endTime: Int!) {
            reserveParamsHistoryItems(
                where: {
                    reserve: $assetId
                    timestamp_gte: $startTime
                    timestamp_lte: $endTime
                }
                orderBy: timestamp
                orderDirection: asc
            ) {
                timestamp
                priceInUSD
            }
        }
        """

        variables = {
            'assetId': asset_address,
            'startTime': start_time,
            'endTime': end_timestamp
        }

        try:
            result = self._execute_query(query, variables)
            items = result.get('reserveParamsHistoryItems', [])

            if len(items) < 2:
                return None

            prices = [float(item['priceInUSD']) for item in items]
            returns = np.diff(np.log(prices))
            volatility = np.std(returns) * np.sqrt(365 * 24)  # Annualized hourly vol

            return float(volatility)

        except Exception as e:
            logger.warning(f"Failed to calculate volatility for {asset_address}: {e}")
            return None

    def fetch_all_liquidations(
        self,
        days: int = DAYS_TO_FETCH
    ) -> pd.DataFrame:
        """Fetch all liquidation events for the specified time period."""
        logger.info(f"Starting liquidation data collection for last {days} days...")

        # Calculate time range
        end_timestamp = self.get_latest_block_timestamp()
        start_timestamp = end_timestamp - (days * 24 * 60 * 60)

        logger.info(f"Time range: {datetime.fromtimestamp(start_timestamp)} to {datetime.fromtimestamp(end_timestamp)}")

        all_liquidations = []
        skip = 0

        while True:
            logger.info(f"Fetching batch: skip={skip}, total so far={self.total_fetched}")

            try:
                batch = self.fetch_liquidation_events(
                    start_timestamp,
                    end_timestamp,
                    skip
                )

                if not batch:
                    logger.info("No more liquidation events found.")
                    break

                all_liquidations.extend(batch)
                self.total_fetched += len(batch)
                skip += BATCH_SIZE

                logger.info(f"Fetched {len(batch)} events (total: {self.total_fetched})")

                # Rate limiting
                time.sleep(RATE_LIMIT_DELAY)

                # Check if we have enough data
                if self.total_fetched >= MIN_LIQUIDATIONS:
                    logger.info(f"Reached target of {MIN_LIQUIDATIONS} liquidations.")
                    break

            except Exception as e:
                logger.error(f"Error fetching batch: {e}")
                time.sleep(5)
                continue

        logger.info(f"Total liquidations fetched: {len(all_liquidations)}")

        # Convert to DataFrame
        df = self._process_liquidations(all_liquidations)
        return df

    def _process_liquidations(self, liquidations: List[Dict]) -> pd.DataFrame:
        """Process raw liquidation data into structured format."""
        processed = []

        for idx, liq in enumerate(liquidations):
            if idx % 100 == 0:
                logger.info(f"Processing liquidation {idx + 1}/{len(liquidations)}...")

            try:
                # Extract basic liquidation data
                record = {
                    'liquidation_id': liq['id'],
                    'tx_hash': liq['txHash'],
                    'timestamp': int(liq['blockTimestamp']),
                    'datetime': datetime.fromtimestamp(int(liq['blockTimestamp'])),
                    'block_number': int(liq['blockNumber']),
                    'user_address': liq['user']['id'],
                    'liquidator': liq['liquidator'],

                    # Collateral asset details
                    'collateral_asset': liq['collateralAsset']['id'],
                    'collateral_symbol': liq['collateralAsset']['symbol'],
                    'collateral_decimals': int(liq['collateralAsset']['decimals']),

                    # Debt asset details
                    'debt_asset': liq['debtAsset']['id'],
                    'debt_symbol': liq['debtAsset']['symbol'],
                    'debt_decimals': int(liq['debtAsset']['decimals']),

                    # Amounts (raw)
                    'collateral_amount_raw': int(liq['liquidatedCollateralAmount']),
                    'debt_amount_raw': int(liq['debtAmount']),

                    # Prices at liquidation
                    'collateral_price_usd': float(liq['collateralAsset']['price']['priceInUSD']),
                    'debt_price_usd': float(liq['debtAsset']['price']['priceInUSD']),
                }

                # Calculate USD values
                collateral_decimals = 10 ** record['collateral_decimals']
                debt_decimals = 10 ** record['debt_decimals']

                record['collateral_amount_usd'] = (
                    record['collateral_amount_raw'] / collateral_decimals * record['collateral_price_usd']
                )
                record['debt_amount_usd'] = (
                    record['debt_amount_raw'] / debt_decimals * record['debt_price_usd']
                )

                # Calculate volatility for both assets
                record['collateral_volatility_24h'] = self.calculate_volatility(
                    record['collateral_asset'],
                    record['timestamp'],
                    24
                )
                record['debt_volatility_24h'] = self.calculate_volatility(
                    record['debt_asset'],
                    record['timestamp'],
                    24
                )

                # Fetch reserve data for additional context
                collateral_reserve = self.fetch_reserve_data(record['collateral_asset'])
                if collateral_reserve:
                    record['collateral_liquidation_threshold'] = float(collateral_reserve.get('liquidationThreshold', 0))
                    record['collateral_base_ltv'] = float(collateral_reserve.get('baseLTVasCollateral', 0))

                debt_reserve = self.fetch_reserve_data(record['debt_asset'])
                if debt_reserve:
                    record['debt_liquidity_rate'] = float(debt_reserve.get('liquidityRate', 0))
                    record['debt_variable_rate'] = float(debt_reserve.get('variableBorrowRate', 0))

                # Time-based features
                dt = record['datetime']
                record['hour_of_day'] = dt.hour
                record['day_of_week'] = dt.weekday()
                record['is_weekend'] = dt.weekday() >= 5

                processed.append(record)
                time.sleep(RATE_LIMIT_DELAY)  # Rate limiting

            except Exception as e:
                logger.error(f"Error processing liquidation {liq.get('id', 'unknown')}: {e}")
                continue

        df = pd.DataFrame(processed)
        logger.info(f"Processed {len(df)} liquidations successfully")
        return df

    def save_data(self, df: pd.DataFrame, output_path: str = OUTPUT_FILE):
        """Save processed data to parquet format."""
        logger.info(f"Saving {len(df)} records to {output_path}...")

        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Save to parquet
        df.to_parquet(output_path, index=False, compression='snappy')

        # Also save to CSV for easy inspection
        csv_path = output_path.replace('.parquet', '.csv')
        df.head(10000).to_csv(csv_path, index=False)

        logger.info(f"Data saved successfully:")
        logger.info(f"  - Parquet: {output_path} ({os.path.getsize(output_path) / 1024 / 1024:.2f} MB)")
        logger.info(f"  - CSV (sample): {csv_path}")

        # Save statistics
        stats = {
            'total_liquidations': len(df),
            'date_range': {
                'start': df['datetime'].min().isoformat(),
                'end': df['datetime'].max().isoformat()
            },
            'total_collateral_liquidated_usd': float(df['collateral_amount_usd'].sum()),
            'total_debt_repaid_usd': float(df['debt_amount_usd'].sum()),
            'unique_users': df['user_address'].nunique(),
            'unique_collateral_assets': df['collateral_symbol'].nunique(),
            'unique_debt_assets': df['debt_symbol'].nunique(),
            'columns': list(df.columns)
        }

        stats_path = output_path.replace('.parquet', '_stats.json')
        with open(stats_path, 'w') as f:
            json.dump(stats, f, indent=2, default=str)

        logger.info(f"Statistics saved to {stats_path}")
        return stats


def main():
    """Main entry point."""
    logger.info("=" * 60)
    logger.info("AAVE V3 LIQUIDATION DATA COLLECTOR")
    logger.info("=" * 60)
    logger.info(f"Subgraph URL: {AAVE_V3_SUBGRAPH_URL}")
    logger.info(f"Days to fetch: {DAYS_TO_FETCH}")
    logger.info(f"Target minimum: {MIN_LIQUIDATIONS} liquidations")
    logger.info(f"Batch size: {BATCH_SIZE}")
    logger.info("=" * 60)

    # Check for API key
    if 'gateway.thegraph.com' in AAVE_V3_SUBGRAPH_URL and not THEGRAPH_API_KEY:
        logger.warning("=" * 60)
        logger.warning("API KEY REQUIRED!")
        logger.warning("=" * 60)
        logger.warning("TheGraph Network requires an API key for access.")
        logger.warning("Get your FREE API key at: https://thegraph.com/studio/")
        logger.warning("")
        logger.warning("Then set it in your .env file:")
        logger.warning("  THEGRAPH_API_KEY=your_api_key_here")
        logger.warning("")
        logger.warning("Or use an alternative data source:")
        logger.warning("  1. Dune Analytics (export liquidation data)")
        logger.warning("  2. Goldsky subgraph")
        logger.warning("  3. Custom Ethereum node with event logs")
        logger.warning("=" * 60)
        logger.info("")
        response = input("Continue anyway? (y/n): ")
        if response.lower() != 'y':
            logger.info("Exiting. Please configure your API key and try again.")
            return

    collector = AaveDataCollector()

    try:
        # Fetch all liquidations
        df = collector.fetch_all_liquidations(DAYS_TO_FETCH)

        if len(df) == 0:
            logger.error("No liquidations fetched. Check the subgraph URL and parameters.")
            return

        # Display summary
        logger.info("\n" + "=" * 60)
        logger.info("DATA SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Total liquidations: {len(df)}")
        logger.info(f"Date range: {df['datetime'].min()} to {df['datetime'].max()}")
        logger.info(f"Total collateral liquidated: ${df['collateral_amount_usd'].sum():,.2f}")
        logger.info(f"Total debt repaid: ${df['debt_amount_usd'].sum():,.2f}")
        logger.info(f"Unique users: {df['user_address'].nunique()}")
        logger.info(f"Top collateral assets:\n{df['collateral_symbol'].value_counts().head()}")
        logger.info(f"Top debt assets:\n{df['debt_symbol'].value_counts().head()}")

        # Save data
        stats = collector.save_data(df)

        logger.info("\n" + "=" * 60)
        logger.info("DATA COLLECTION COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Output file: {OUTPUT_FILE}")
        logger.info(f"\nNext steps:")
        logger.info(f"  1. Verify data quality: python -c \"import pandas as pd; df = pd.read_parquet('{OUTPUT_FILE}'); print(df.head())\"")
        logger.info(f"  2. Run feature engineering: python feature_engineering.py")
        logger.info(f"  3. Start model training: python train_model.py")

    except Exception as e:
        logger.exception("Fatal error during data collection")
        raise


if __name__ == '__main__':
    main()
