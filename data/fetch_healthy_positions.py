#!/usr/bin/env python3
"""
Fetch REAL healthy positions from Aave V3 - Class 0

Query userReserves for positions that:
- Have health factor > 1.5 (safe, not at risk)
- Have never been liquidated
- Are active on Aave V3 Ethereum

These become our TRUE negative samples (Class 0).
"""

import os
import requests
import pandas as pd
import numpy as np
from datetime import datetime
import time
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv('THEGRAPH_API_KEY', '656a25a51aac776685925fcaf6acfde7')
SUBGRAPH_URL = f"https://gateway.thegraph.com/api/{API_KEY}/subgraphs/id/Cd2gEDVeqnjBn1hSeqFMitw8Q1iiyV9FYUZkLNRcL87g"


def fetch_healthy_positions(target_count=50000):
    """
    Fetch active userReserves with health factor > 1.5.
    
    These are positions that are healthy and unlikely to be liquidated soon.
    """
    print("="*70)
    print("FETCHING HEALTHY POSITIONS FROM AAVE V3")
    print("="*70)
    print(f"Target: {target_count:,} positions with HF > 1.5")
    print()
    
    healthy_positions = []
    skip = 0
    batch_size = 1000
    
    while len(healthy_positions) < target_count:
        # Query userReserves - the correct entity for current positions
        query = {
            "query": f"""{{
                userReserves(
                    first: {batch_size},
                    skip: {skip},
                    where: {{
                        currentATokenBalance_gt: 0,
                        currentVariableDebt_gt: 0
                    }}
                    orderBy: currentATokenBalance,
                    orderDirection: desc
                ) {{
                    id
                    user {{
                        id
                    }}
                    reserve {{
                        id
                        symbol
                        decimals
                        price {{
                            priceInUSD
                        }}
                        liquidationThreshold
                        baseLTVasCollateral
                    }}
                    currentATokenBalance
                    currentVariableDebt
                    currentStableDebt
                    liquidityRate
                    variableBorrowRate
                    stableBorrowRate
                    usageAsCollateralEnabledOnUser
                }}
            }}"""
        }
        
        try:
            response = requests.post(
                SUBGRAPH_URL, 
                json=query, 
                timeout=60,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                data = response.json()
                
                if 'data' in data and data['data']:
                    batch = data['data'].get('userReserves', [])
                    
                    if not batch:
                        print(f"No more results at skip={skip}")
                        break
                    
                    for pos in batch:
                        try:
                            # Extract position data
                            user = pos['user']['id']
                            reserve = pos['reserve']
                            
                            collateral_raw = int(pos['currentATokenBalance'])
                            debt_var = int(pos['currentVariableDebt'])
                            debt_stable = int(pos['currentStableDebt'])
                            debt_raw = debt_var + debt_stable
                            
                            # Skip if no debt (can't be liquidated)
                            if debt_raw == 0:
                                continue
                            
                            decimals = int(reserve['decimals'])
                            price_usd = float(reserve.get('price', {}).get('priceInUSD', 0))
                            
                            if price_usd == 0:
                                continue
                            
                            liquidation_threshold = float(reserve['liquidationThreshold'])
                            
                            # Calculate USD values
                            collateral_decimals = 10 ** decimals
                            collateral_usd = (collateral_raw / collateral_decimals) * price_usd
                            debt_usd = (debt_raw / collateral_decimals) * price_usd
                            
                            # Calculate health factor
                            if debt_usd > 0:
                                hf = (collateral_usd * liquidation_threshold) / debt_usd
                            else:
                                continue
                            
                            # ONLY keep positions with HF > 1.5 (healthy)
                            if hf > 1.5:
                                healthy_positions.append({
                                    'user_reserve_id': pos['id'],
                                    'user': user,
                                    'reserve_symbol': reserve['symbol'],
                                    'collateral_raw': collateral_raw,
                                    'debt_raw': debt_raw,
                                    'collateral_usd': collateral_usd,
                                    'debt_usd': debt_usd,
                                    'health_factor': hf,
                                    'collateral_to_debt_ratio': collateral_raw / max(debt_raw, 1),
                                    'liquidation_threshold': liquidation_threshold,
                                    'base_ltv': float(reserve['baseLTVasCollateral']),
                                    'liquidity_rate': float(pos.get('liquidityRate', 0)),
                                    'variable_borrow_rate': float(pos.get('variableBorrowRate', 0)),
                                    'price_usd': price_usd,
                                    'decimals': decimals,
                                    'snapshot_timestamp': int(datetime.now().timestamp()),
                                })
                                
                                if len(healthy_positions) % 1000 == 0:
                                    print(f"  Collected {len(healthy_positions):,} healthy positions...")
                                
                                if len(healthy_positions) >= target_count:
                                    break
                        
                        except Exception as e:
                            continue
                    
                    skip += batch_size
                    print(f"  Processed {skip:,} userReserves, found {len(healthy_positions):,} healthy (HF>1.5)")
                    
                    if len(batch) < batch_size:
                        break
                else:
                    print(f"No data in response: {data}")
                    break
            else:
                print(f"HTTP Error {response.status_code}: {response.text[:200]}")
                break
                
        except Exception as e:
            print(f"Exception: {e}")
            time.sleep(2)
            continue
        
        time.sleep(0.5)  # Rate limiting
    
    print(f"\n✅ Collected {len(healthy_positions):,} healthy positions")
    
    if len(healthy_positions) == 0:
        print("❌ No healthy positions found!")
        return None
    
    # Convert to DataFrame
    df = pd.DataFrame(healthy_positions)
    
    print(f"\n" + "="*70)
    print("HEALTHY POSITIONS STATISTICS")
    print("="*70)
    print(f"Total: {len(df):,} positions")
    print(f"\nHealth Factor distribution:")
    print(df['health_factor'].describe())
    print(f"\nReserve symbols:")
    print(df['reserve_symbol'].value_counts().head(10))
    print(f"\nCollateral USD (median): ${df['collateral_usd'].median():,.2f}")
    print(f"Debt USD (median): ${df['debt_usd'].median():,.2f}")
    
    # Save
    output_file = '/home/mobra/protocol/data/aave_healthy_positions_real.parquet'
    df.to_parquet(output_file, index=False, compression='snappy')
    print(f"\n✅ Saved to {output_file}")
    
    return df


if __name__ == '__main__':
    fetch_healthy_positions(50000)
