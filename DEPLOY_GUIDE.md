# Deployment REAL pe Monad Testnet - Ghid Complet

## ⚠️ IMPORTANT: Fără Simulare, Totul Real

### Pașii necesari pentru deployment real:

---

## 1. Creează Wallet pentru Testnet (5 minute)

### Opțiunea A: MetaMask
1. Deschide MetaMask
2. Click pe icon profil → "Create Account"
3. Salvează seed phrase și cheia privată
4. Exportă cheia privată: click pe ⋮ → "Account Details" → "Export Private Key"

### Opțiunea B: Monad Testnet Explorer
1. Mergi la https://testnet.monadexplorer.com
2. Click "Connect Wallet"
3. Creează wallet nou
4. Copiază adresa și cheia privată

---

## 2. Obține MONAD Testnet Tokens (Faucet)

### Faucet Monad (gratis):
1. Mergi la https://testnet.faucet.monad.xyz/
2. Lipește adresa walletului tău
3. Click "Request 1 MON"
4. Așteaptă ~30 secunde
5. Verifică balanța pe https://testnet.monadexplorer.com

### Alternative:
- Discord Monad: https://discord.gg/monad (canalul #faucet)
- Poți cere de la alți utilizatori

---

## 3. Configurează .env (1 minut)

Editează fișierul `/home/mobra/protocol/.env`:

```bash
# Înlocuiește cu datele tale reale:
EXECUTOR_PRIVATE_KEY=0xabc123... (cheia privată cu 0x)
EXECUTOR_ADDRESS=0xYourRealAddress
```

**⚠️  ATENȚIE:**
- Folosește doar wallet de testnet, fără fonduri reale
- Cheia privată trebuie să înceapă cu 0x
- Nu commite această cheie în git niciodată

---

## 4. Deploy Contracte (2 minute)

### În terminal, rulează:

```bash
cd /home/mobra/protocol
source venv/bin/activate

# Setează cheia privată temporar
export PRIVATE_KEY=0xYOUR_PRIVATE_KEY_HERE

# Deploy pe Monad Testnet
npx hardhat run scripts/deploy.js --network monadTestnet
```

### Ce se întâmplă:
1. Hardhat compilează contractele
2. Trimite tranzacții de deploy la https://rpc.testnet.monad.xyz
3. Așteaptă confirmare (~5-10 secunde)
4. Salvează adresele în `deployments/monadTestnet.json`

---

## 5. Verifică pe Explorer (1 minut)

După deploy, vei vedea:

```
✅ PositionRegistry deployed: 0x1234...
✅ ProtectionExecutor deployed: 0xABCD...
✅ FeeCollector deployed: 0x5678...
```

Verifică pe explorer:
1. Mergi la https://testnet.monadexplorer.com
2. Caută adresa contractului
3. Ar trebui să vezi codul sursă și tranzacțiile

---

## 6. Test Interacțiune (2 minute)

### În terminal:

```bash
# Pornește console Hardhat
npx hardhat console --network monadTestnet

# În console, rulează:
const registry = await ethers.getContractAt("PositionRegistry", "0xYOUR_ADDRESS")
await registry.isProtected("0xSOME_USER_ADDRESS")
```

---

## 7. Rulează Risk Monitor Real (24/7)

### În terminal nou:

```bash
cd /home/mobra/protocol
source venv/bin/activate

# Setează variabilele de mediu
export EXECUTOR_PRIVATE_KEY=0xYOUR_PRIVATE_KEY
export EXECUTOR_ADDRESS=0xYOUR_ADDRESS

# Pornește monitorul
python monitor/risk_monitor.py
```

Monitorul va:
- Conecta la Monad Testnet via WebSocket
- Query-ui TheGraph API pentru poziții active
- Scor-ează riscul cu modelul XGBoost pe GPU
- Log-ează predicții (fără să execute încă)

---

## Troubleshooting

### Eroare: "insufficient funds"
- Soluție: Obține mai mult MON de la faucet

### Eroare: "replacement fee too low"
- Soluție: Așteaptă 30 secunde și reîncearcă

### Eroare: "could not detect network"
- Soluție: Verifică conexiunea la internet și RPC URL

---

## Costuri Reale (Testnet)

| Operațiune | Cost Aproximativ |
|-----------|------------------|
| Deploy 3 contracte | ~0.01 MON |
| Test tranzacții | ~0.001 MON per tx |
| Monitor 24/7 o săptămână | ~0.05 MON |

Total: **Sub $1** (testnet tokens sunt gratis)

---

## Verificare Succes

După deploy, ar trebui să ai:
- [ ] 3 adrese de contracte pe Monad Testnet
- [ ] Contracte verificate pe explorer
- [ ] Risk Monitor care rulează și log-ează predicții
- [ ] Dashboard care arată date reale

---

## Suport

Dacă ai probleme:
1. Verifică balanța pe explorer
2. Asigură-te că folosești testnet, nu mainnet
3. Verifică că cheia privată are 0x la început

---

**Ești gata să faci deploymentul real?** 🚀
