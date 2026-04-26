#!/usr/bin/env python3
"""Explore TheGraph schema to find health factor data."""
import json
import requests

API_KEY = "656a25a51aac776685925fcaf6acfde7"
SUBGRAPH_ID = "Cd2gEDVeqnjBn1hSeqFMitw8Q1iiyV9FYUZkLNRcL87g"
URL = f"https://gateway.thegraph.com/api/{API_KEY}/subgraphs/id/{SUBGRAPH_ID}"

# Introspect to find User type
introspect = """{
  __type(name: "User") {
    name
    fields {
      name
      type {
        name
        kind
      }
    }
  }
}"""

response = requests.post(URL, json={"query": introspect}, timeout=30)
print("USER type fields:")
data = response.json()
if 'data' in data and data['data']['__type']:
    for field in data['data']['__type']['fields']:
        type_name = field['type']['name'] or field['type'].get('kind', '?')
        print(f"  {field['name']}: {type_name}")

print("\n" + "="*60)

# Try query users with reserves
query = """{
  users(first: 3, where: {borrowedReservesCount_gt: 0}) {
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
}"""

response = requests.post(URL, json={"query": query}, timeout=30)
print("\nUSER query result:")
data = response.json()
if 'errors' in data:
    print(f"Errors: {data['errors']}")
else:
    print(json.dumps(data['data']['users'][0] if data['data']['users'] else {}, indent=2))
