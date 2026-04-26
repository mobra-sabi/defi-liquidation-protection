#!/usr/bin/env python3
"""Test TheGraph query for user reserves."""
import os
import json
import requests

# Try the working hex API key
API_KEY = "656a25a51aac776685925fcaf6acfde7"
SUBGRAPH_ID = "Cd2gEDVeqnjBn1hSeqFMitw8Q1iiyV9FYUZkLNRcL87g"
URL = f"https://gateway.thegraph.com/api/{API_KEY}/subgraphs/id/{SUBGRAPH_ID}"

print(f"Testing URL: {URL[:80]}...")

# Test query - simple first
query = """{
  _meta {
    block {
      number
      timestamp
    }
    deployment
  }
}"""

response = requests.post(URL, json={"query": query}, timeout=30)
print(f"\n[1] Meta query status: {response.status_code}")
print(f"Response: {response.text[:300]}")

# Now test userReserves
query2 = """{
  userReserves(first: 3, where: {currentTotalDebt_gt: "0"}) {
    id
    user { id }
    reserve {
      symbol
      decimals
      reserveLiquidationThreshold
      baseLTVasCollateral
      price { priceInEth }
    }
    currentATokenBalance
    currentVariableDebt
    currentStableDebt
    currentTotalDebt
    usageAsCollateralEnabledOnUser
  }
}"""

response = requests.post(URL, json={"query": query2}, timeout=30)
print(f"\n[2] userReserves query status: {response.status_code}")

if response.status_code == 200:
    data = response.json()
    if 'errors' in data:
        print(f"Errors: {data['errors']}")
    else:
        print(f"✅ Got {len(data['data']['userReserves'])} user reserves")
        if data['data']['userReserves']:
            print("\nFirst sample:")
            print(json.dumps(data['data']['userReserves'][0], indent=2))
