# DeFi AI Liquidation Protection Protocol

> **Live on Monad Testnet** • Non-custodial liquidation protection for DeFi users

[![Status](https://img.shields.io/badge/status-live%20on%20testnet-green)](https://testnet.monadexplorer.com)
[![Network](https://img.shields.io/badge/network-Monad%20Testnet-purple)](https://testnet.monad.xyz)
[![Built In](https://img.shields.io/badge/built%20in-2%20days-blue)](README.md)

A protocol that protects DeFi users from forced liquidations on Aave/Morpho by monitoring health factors in real-time and executing protective actions before liquidation occurs.

---

## 🚀 Live Contracts (Monad Testnet)

| Contract | Address |
|----------|---------|
| **PositionRegistry** | [`0x242Eb426481d3C1C2b635bcC8BF801ebC678a4E9`](https://testnet.monadexplorer.com/address/0x242Eb426481d3C1C2b635bcC8BF801ebC678a4E9) |
| **ProtectionExecutor** | [`0xd5A4caD8e174e09420A9BF51C71A8CA176040C6f`](https://testnet.monadexplorer.com/address/0xd5A4caD8e174e09420A9BF51C71A8CA176040C6f) |
| **FeeCollector** | [`0x911A050728D684018dAaE15164267e72F52a9A81`](https://testnet.monadexplorer.com/address/0x911A050728D684018dAaE15164267e72F52a9A81) |

**Network:** Monad Testnet (Chain ID: 10143)

---

## 🎯 Why This Exists

DeFi liquidations cost users **billions** every year. When a user's health factor drops below 1.0, liquidators take 5-10% of their collateral as a penalty.

**Existing solutions:**
- ❌ CEX-style automated bots (require keys, not trustless)
- ❌ Manual monitoring (requires watching constantly)
- ❌ Liquidation insurance (expensive, slow payouts)

**Our solution:**
- ✅ **Non-custodial** — you keep your keys
- ✅ **Real-time** — monitors every block
- ✅ **Automated** — executes before liquidation
- ✅ **Transparent** — open source, on-chain

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    On-Chain (Monad)                       │
│                                                            │
│  ┌─────────────────┐  ┌──────────────────┐  ┌──────────┐ │
│  │ PositionRegistry │  │ ProtectionExec.  │  │FeeCollect│ │
│  │  - User config   │  │  - Rebalance     │  │  - Fees  │ │
│  │  - Permissions   │  │  - Flash loans   │  │          │ │
│  └─────────────────┘  └──────────────────┘  └──────────┘ │
└──────────────────────────────────────────────────────────┘
                              ▲
                              │ Events / Calls
                              ▼
┌──────────────────────────────────────────────────────────┐
│                    Off-Chain (Server)                     │
│                                                            │
│  ┌─────────────────┐  ┌──────────────────┐  ┌──────────┐ │
│  │  Risk Monitor   │  │ Execution Engine │  │ AI Model │ │
│  │  - HF tracking  │  │  - Tx signing    │  │ (XGBoost)│ │
│  │  - Rule-based   │  │  - Gas optim.    │  │ Disabled │ │
│  └─────────────────┘  └──────────────────┘  └──────────┘ │
│                              │                             │
│                              ▼                             │
│                      ┌─────────────┐                       │
│                      │  Dashboard  │ (Next.js)             │
│                      └─────────────┘                       │
└──────────────────────────────────────────────────────────┘
```

---

## 🛡️ Risk Scoring Logic

Currently using **rule-based** scoring (transparent and predictable):

| Health Factor | Risk Level | Action |
|---------------|------------|--------|
| > 1.30 | **SAFE** | No action needed |
| 1.15 – 1.30 | **WARNING** | Notify user |
| 1.05 – 1.15 | **ALERT** | Prepare rebalancing |
| < 1.05 | **CRITICAL** | Execute protection immediately |

> **Why not ML?** We trained an XGBoost model on 28,434 real Aave V3 positions, but ML adds only 1-2% over rule-based. Once we collect testnet data, we'll re-evaluate. ML model code is preserved at [`monitor/risk_monitor_ml_backup.py`](monitor/risk_monitor_ml_backup.py).

---

## 📊 Data Used

All data sourced from real Aave V3 Ethereum via TheGraph (paid subscription):

| Dataset | Count | Description |
|---------|-------|-------------|
| Historical liquidations | 24,525 | Real liquidation events |
| Active positions | 17,491 | Real users with active borrows |
| Class 0 (HF 1.0-1.5) | 4,084 | Critical zone - the hard cases |
| Total training samples | 28,434 | Balanced 50/50 |

---

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- Node.js 18+
- Hardhat
- ~20 MON testnet tokens for deployment

### Installation

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/defi-liquidation-protection
cd defi-liquidation-protection

# Install Python dependencies
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Install Node dependencies (Hardhat + Dashboard)
npm install
cd dashboard && npm install && cd ..

# Configure environment
cp .env.example .env
# Edit .env with your API keys
```

### Generate Testnet Wallet

```bash
npx hardhat run scripts/generate-wallet.js
# Add the generated private key to .env
```

### Get Testnet Tokens

Visit [Monad Faucet](https://testnet.monad.xyz/faucet) and request tokens for your address.

### Deploy Contracts

```bash
npx hardhat run scripts/deploy.js --network monadTestnet
```

### Start Risk Monitor

```bash
python monitor/live_monitor.py
```

### Start Dashboard

```bash
cd dashboard && npm run dev
# Open http://localhost:3000
```

### Check Status

```bash
python monitor/status.py
# or watch mode
python monitor/status.py --watch
```

---

## 📂 Project Structure

```
protocol/
├── contracts/              # Solidity smart contracts
│   ├── PositionRegistry.sol
│   ├── ProtectionExecutor.sol
│   └── FeeCollector.sol
├── monitor/                # Off-chain risk monitor
│   ├── risk_monitor.py     # Rule-based scoring (active)
│   ├── live_monitor.py     # Continuous block monitor
│   ├── status.py           # CLI status dashboard
│   └── risk_monitor_ml_backup.py  # ML model (disabled)
├── ai-engine/              # ML training scripts
│   ├── train_real_model.py
│   ├── train_clean_real_model.py
│   └── *.json              # Trained models
├── data/                   # Data collection scripts
│   ├── fetch_liquidations.py
│   ├── fetch_real_class_0.py
│   └── build_*.py
├── dashboard/              # Next.js dashboard
│   ├── app/
│   │   ├── page.tsx
│   │   └── api/status/route.ts
│   └── ...
├── executor/               # Transaction execution
├── scripts/                # Deployment scripts
│   ├── deploy.js
│   ├── generate-wallet.js
│   └── check-balance.js
├── deployments/            # Deployment records
│   └── monadTestnet.json
├── hardhat.config.cjs
├── package.json
├── requirements.txt
├── README.md               # This file
├── MONITORING.md           # Monitoring guide
└── DEPLOY_READINESS.md     # Deployment notes
```

---

## 🧪 Testing on Testnet

Want to test? Here's how:

1. **Get a Monad testnet wallet** with some test tokens
2. **Register a position** in the PositionRegistry contract
3. **Set your protection thresholds**
4. **Watch the dashboard** for activity

> Detailed user guide coming soon. For now, [DM me](https://twitter.com/yourusername) for test access.

---

## 📈 Status

- ✅ Contracts deployed on Monad testnet
- ✅ Live monitoring active
- ✅ Public dashboard
- ⏳ User testing
- ⏳ Real ML model (after data collection)
- ⏳ Mainnet deployment (after audit)

---

## 🤝 Contributing

This is an early-stage project looking for:
- 🧪 **Beta testers** with DeFi experience
- 🛠️ **Smart contract devs** for code review
- 📊 **Data scientists** to improve the ML model
- 🎨 **Designers** for the dashboard UX

[Open an issue](https://github.com/YOUR_USERNAME/defi-liquidation-protection/issues) or DM on Twitter.

---

## 📝 Roadmap

### ✅ Phase 1: Foundation (DONE)
- [x] Smart contracts deployed
- [x] Risk monitor live
- [x] Dashboard built
- [x] 28k real positions analyzed

### ⏳ Phase 2: Testing (CURRENT)
- [ ] First 10 testers
- [ ] Collect real testnet data
- [ ] Iterate on UX
- [ ] User feedback

### 🔜 Phase 3: ML Re-training
- [ ] Collect 10k+ testnet data points
- [ ] Train ML model on real testnet data
- [ ] A/B test ML vs rule-based
- [ ] Deploy winning approach

### 🚀 Phase 4: Mainnet
- [ ] Security audit
- [ ] Bug bounty program
- [ ] Mainnet deployment
- [ ] Marketing & growth

---

## 🛡️ Security

This is **alpha software** on **testnet**. Do NOT use with real funds.

- Never use the testnet wallet for mainnet
- Generate a new wallet for production
- All contracts are unaudited

---

## 📜 License

MIT License - see [LICENSE](LICENSE)

---

## 🙏 Acknowledgements

- [Aave](https://aave.com/) — for the protocol we're building on
- [Monad](https://monad.xyz/) — for the high-performance L1
- [TheGraph](https://thegraph.com/) — for the data infrastructure

---

## 📬 Contact

- **Twitter:** [@yourusername](https://twitter.com/yourusername)
- **Email:** your.email@example.com
- **Discord:** yourusername

---

**Built with ❤️ in 2 days. Now growing slowly with real users.**
