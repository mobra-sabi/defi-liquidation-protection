# 📊 Cum vezi ce se întâmplă - Ghid Complet

Ai 4 moduri să vezi ce se întâmplă cu protocolul tău, în ordinea utilității:

---

## 1. 🌐 Dashboard Web (cel mai vizual)

**URL:** http://localhost:3000

Arată în timp real:
- Status blockchain (block actual, gas price)
- Balanța wallet-ului
- Contractele deployate
- Status monitor (activ/idle)
- Evenimente recente capturate
- Update automat la fiecare 5 secunde

**Pornire:**
```bash
cd /home/mobra/protocol/dashboard && npm run dev
```

**Oprire:**
```bash
pkill -f "next dev"
```

---

## 2. 💻 Status CLI (rapid din terminal)

**One-shot:**
```bash
python3 /home/mobra/protocol/monitor/status.py
```

**Auto-refresh (la 10s):**
```bash
python3 /home/mobra/protocol/monitor/status.py --watch
```

Arată:
- Conexiune blockchain
- Wallet info (adresă, balanță, nonce)
- Status fiecare contract
- Status monitor (activ/idle)
- Tranzacții recente
- Link-uri rapide la explorer

---

## 3. 📜 Live Logs (vezi tot ce se întâmplă)

**Live tail al log-urilor:**
```bash
tail -f /home/mobra/protocol/monitor/risk_monitor.log
```

**Vezi ultimele evenimente capturate:**
```bash
tail -20 /home/mobra/protocol/monitor/events.jsonl | python3 -m json.tool
```

**Vezi metrice curente:**
```bash
cat /home/mobra/protocol/monitor/metrics.json | python3 -m json.tool
```

---

## 4. 🔗 Block Explorer (verificare independentă)

**Wallet-ul tău:**
https://testnet.monadexplorer.com/address/0x8Bc0a39981A5B259696a0854EA6984FDE81A3232

**Contracte:**
- PositionRegistry: https://testnet.monadexplorer.com/address/0x242Eb426481d3C1C2b635bcC8BF801ebC678a4E9
- ProtectionExecutor: https://testnet.monadexplorer.com/address/0xd5A4caD8e174e09420A9BF51C71A8CA176040C6f
- FeeCollector: https://testnet.monadexplorer.com/address/0x911A050728D684018dAaE15164267e72F52a9A81

---

## 🚀 Pornire Completă (toate componentele)

```bash
# 1. Pornește live monitor în background
cd /home/mobra/protocol
nohup python3 monitor/live_monitor.py > monitor/nohup.log 2>&1 &

# 2. Pornește dashboard în background
cd /home/mobra/protocol/dashboard
nohup npm run dev > dashboard.log 2>&1 &

# 3. Verifică status
python3 /home/mobra/protocol/monitor/status.py
```

---

## 🛑 Oprire Completă

```bash
# Oprește monitor
pkill -f "live_monitor.py"

# Oprește dashboard
pkill -f "next dev"

# Verifică că s-au oprit
ps aux | grep -E "live_monitor|next dev" | grep -v grep
```

---

## 📁 Fișiere Importante

| Fișier | Conținut |
|--------|----------|
| `monitor/risk_monitor.log` | Log-urile detaliate ale monitorului |
| `monitor/metrics.json` | Metrici curente (blocks monitored, events) |
| `monitor/events.jsonl` | Toate evenimentele capturate |
| `monitor/nohup.log` | Output-ul procesului background |
| `dashboard/dashboard.log` | Log-ul dashboard-ului |
| `data/testnet_collected_data.parquet` | Date colectate pentru ML viitor |

---

## 🔍 Debugging Frecvent

**Q: Dashboard nu se încarcă?**
```bash
# Verifică că rulează
ps aux | grep "next dev" | grep -v grep
# Dacă nu, repornește
cd /home/mobra/protocol/dashboard && npm run dev
```

**Q: Monitor pare oprit?**
```bash
# Verifică ultimul update
cat /home/mobra/protocol/monitor/metrics.json | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['last_update'])"
# Repornește dacă e oprit
nohup python3 /home/mobra/protocol/monitor/live_monitor.py > /home/mobra/protocol/monitor/nohup.log 2>&1 &
```

**Q: Cum verific că contractele sunt OK?**
```bash
python3 /home/mobra/protocol/monitor/status.py
# Sau direct pe explorer:
# https://testnet.monadexplorer.com/address/0x242Eb426481d3C1C2b635bcC8BF801ebC678a4E9
```

**Q: Cum văd ce date am colectat?**
```python
import pandas as pd
df = pd.read_parquet('/home/mobra/protocol/data/testnet_collected_data.parquet')
print(df.tail(10))
```

---

## 📈 Metrice Cheie de Urmărit

În următoarele zile/săptămâni:
- **blocks_monitored** - cât de continuu rulează monitorul
- **events_captured** - cât de multă activitate e pe contracte
- **uptime_seconds** - stabilitatea sistemului
- **positions_registered** - când utilizatorii încep să se înregistreze
- **protections_executed** - prima protecție executată!

---

## 🎯 Următorii Pași

1. ✅ Pornește dashboard-ul (acum)
2. ⏳ Postează pe Twitter cu link la dashboard
3. ⏳ Așteaptă primii testeri
4. ⏳ Vezi primele tranzacții apărând în events.jsonl
5. ⏳ După 1-2 săptămâni: analizează datele și antrenează ML
