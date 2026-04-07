# Broadcast Pool

> Electrum proxy with scheduled Bitcoin transaction broadcast

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/docker-ghcr.io-blue)](https://github.com/semillabitcoin/broadcast-pool/pkgs/container/broadcast-pool)
[![Umbrel](https://img.shields.io/badge/umbrel-app-purple)](https://github.com/semillabitcoin/umbrel-app-store)
[![Start9](https://img.shields.io/badge/start9-app-orange)](https://github.com/semillabitcoin/broadcast-pool-startos)

Inspired by Craig Raw's [Broadcast Pool proposal](https://github.com/bitcoin/bitcoin/issues/30471).

🇪🇸 [Léeme en español](README.es.md)

---

## What is it?

Broadcast Pool (BP) is an Electrum proxy that runs on your node and sits between your wallet and your Electrum server. When your wallet broadcasts a transaction, BP **retains** it instead of forwarding it immediately and schedules it to be broadcast later — at the block, date or Bitcoin price you decide.

Built for bitcoiners who want to manage their signed transactions with fine-grained control over when and how they reach the mempool. All without leaving your node.

---

## Use cases

- **Wallet migrations**: spread the moves across blocks or days so there's no obvious "everything moved at once" footprint
- **Cycle today what you'd cycle a year from now**, with `nLockTime` set for anti-fee-sniping (privacy indistinguishable from regular wallets)
- **Emergency collateral for Bitcoin loans**: schedule automatic collateral if the price drops below a threshold, to avoid liquidations
- **UTXO management distributed over time**: scheduled sweeps, consolidations and batches

---

## Features

- **Compatible with any Electrum wallet**: Sparrow, Liana, Nunchuk, Electrum, etc.
- **Mainnet, testnet and signet**
- **Three scheduling modes**:
  - By **block** (height)
  - By **date** (MTP — Median Time Past)
  - By **Bitcoin price** (via CoinGecko or local on-chain oracle)
- **Auto-discovery** of local Electrum servers and price oracles (Umbrel, Start9)
- **Auto-scheduling** when a wallet signs with future `nLockTime`
- **NIP-44 encrypted vault (Nostr)** for history: only decryptable with your nsec key
- **Responsive web UI** (mobile and desktop)
- **No telemetry, no tracking**: your node, your data, your transactions

### Experimental features

- **Faking blockheight for Liana**: BP can show Liana (and other wallets) a fake block height so they sign transactions with `nLockTime` months — or years — in the future, improving on-chain privacy. Liana doesn't validate PoW (only chain continuity), so this works without breaking the flow.

---

## Installation

### Umbrel

1. Open the Umbrel App Store
2. Go to **Community App Stores** → **Add Store**
3. Paste: `https://github.com/semillabitcoin/umbrel-app-store`
4. Install **Broadcast Pool**

### Start9

Broadcast Pool is not yet in the official Start9 marketplace, so installation is via manual **sideload**:

1. Download the `.s9pk` for your architecture from [releases](https://github.com/semillabitcoin/broadcast-pool-startos/releases/latest):
   - `broadcast-pool_x86_64.s9pk` (Intel/AMD PCs / servers)
   - `broadcast-pool_aarch64.s9pk` (Raspberry Pi / ARM)
2. In StartOS: **Marketplace > Sideload** → upload the `.s9pk`

> ⚠️ **About updates on Start9:** sideloaded apps don't auto-update. Each new version requires downloading the updated `.s9pk` and sideloading it again. We're working on getting into the official Start9 registry to fix this.

### Docker

```bash
docker run -d \
  --name broadcast-pool \
  -p 4040:4040 \
  -p 50005:50005 \
  -v $(pwd)/data:/data \
  -e ELECTRUM_HOST=your-electrum-server \
  -e ELECTRUM_PORT=50001 \
  -e APP_SEED=your-32-char-random-seed \
  ghcr.io/semillabitcoin/broadcast-pool:latest
```

### Local (development)

```bash
git clone https://github.com/semillabitcoin/broadcast-pool
cd broadcast-pool
pip install -r requirements.txt
python3 -m src.main
```

Environment variables:

| Variable | Default | Description |
|---|---|---|
| `WEB_PORT` | `4040` | Web dashboard port |
| `PROXY_PORT` | `50005` | Electrum proxy port (TCP) |
| `WEB_BIND` | `127.0.0.1` | Web interface bind address |
| `ELECTRUM_HOST` | `127.0.0.1` | Upstream Electrum server host |
| `ELECTRUM_PORT` | `50001` | Upstream Electrum server port |
| `ELECTRUM_SSL` | `false` | Use SSL with upstream |
| `DB_PATH` | `data/pool.db` | SQLite database path |
| `APP_SEED` | _(empty)_ | Key to encrypt txs at rest |
| `BP_AUTH_TOKEN` | _(empty)_ | API auth token (optional) |

---

## How it works

```
       ┌──────────┐                    ┌──────────────┐
       │  Wallet  │  ──── Electrum ───▶│  BP proxy    │
       │ (Sparrow │  ◀──── return ─────│  :50005      │
       │  Liana)  │                    └──────┬───────┘
       └──────────┘                           │
                                              │ broadcast intercepted
                                              ▼
                                       ┌──────────────┐
                                       │  Retention   │
                                       │  (SQLite)    │
                                       └──────┬───────┘
                                              │
                            ┌─────────────────┼─────────────────┐
                            ▼                 ▼                 ▼
                       ┌─────────┐      ┌─────────┐      ┌──────────┐
                       │  Block  │      │   MTP   │      │  Price   │
                       │ trigger │      │ trigger │      │ trigger  │
                       └────┬────┘      └────┬────┘      └────┬─────┘
                            └─────────────────┴─────────────────┘
                                              │
                                              ▼
                                    ┌────────────────────┐
                                    │ Electrum upstream  │
                                    │ (your node)        │
                                    └────────────────────┘
```

1. Your wallet connects to BP's proxy (port 50005) instead of directly to your Electrum server
2. When you broadcast a transaction, BP **intercepts** it, saves it to its database and returns the `txid` to the wallet (which thinks it was broadcast)
3. The wallet sees the tx as pending in its virtual mempool (BP serves it consistently to the Electrum server)
4. You decide from the dashboard when to broadcast it: at a specific block, a date (MTP), or when the price crosses a threshold
5. When the condition is met, BP broadcasts the tx to the network via your node's Electrum

---

## Configuration

All configuration is done from the **Settings** tab of the web dashboard:

1. **Electrum server connection**: auto-detects local servers (Electrs, Fulcrum) or configure one manually
2. **How to accumulate transactions**: shows the address your wallet should connect to
3. **Behavior**: auto-scheduling, price-based broadcast, faking blockheight
4. **Encrypted vault (Nostr)**: configure an `npub` to store the encrypted history
5. **Other preferences**: language (ES/EN), unit (BTC/sats)

---

## Technical architecture

- **Stack**: Python 3.12 + asyncio + aiohttp + SQLite (WAL mode)
- **Three components**: Electrum TCP proxy (`src/proxy/`), block/price scheduler (`src/scheduler/`), web API + dashboard (`src/web/`)
- **Encryption**:
  - `APP_SEED` encrypts retained transactions at rest (AES + HMAC)
  - NIP-44 encrypts confirmed history in the Nostr vault
- **No external runtime dependencies**: everything runs inside the container
- **Persistence**: SQLite with WAL for concurrency between proxy, scheduler and API
- **Multi-arch**: amd64 + arm64 builds (Raspberry Pi compatible)

---

## Security and privacy

- **Zero trust with upstream**: BP doesn't send any sensitive data to the Electrum server beyond what's strictly required by the protocol
- **No telemetry, no tracking, no analytics**
- **Encrypted `raw_hex`** in SQLite when `APP_SEED` is set
- **Optional API auth** via `BP_AUTH_TOKEN` (Umbrel/Start9 already handle proxy-level auth)
- **Vault only decryptable by the user**: BP uses asymmetric cryptography based on Nostr keys
- **Audited**: ongoing security review. Report issues at [GitHub Issues](https://github.com/semillabitcoin/broadcast-pool/issues)

### Recommendations

- Set `APP_SEED` to a strong random value (Umbrel and Start9 generate it automatically)
- Use a **burner npub** for the Nostr vault, not your main identity
- **Don't expose the Electrum proxy (50005) over Tor or public networks**

---

## Contributing

Pull requests welcome. Issues and feedback at [GitHub Issues](https://github.com/semillabitcoin/broadcast-pool/issues).

```bash
git clone https://github.com/semillabitcoin/broadcast-pool
cd broadcast-pool
pip install -r requirements.txt
python3 -m src.main
# Dashboard at http://localhost:4040
```

---

## Credits

- **[Craig Raw](https://github.com/craigraw)** — original [Broadcast Pool proposal](https://github.com/bitcoin/bitcoin/issues/30471) and Sparrow Wallet author
- **[Wizardsardine](https://wizardsardine.com)** — Liana Wallet (Miniscript pioneer)
- **[Start9 Labs](https://start9.com)** — StartOS and SDK
- **[Umbrel](https://umbrel.com)** — umbrelOS and App Framework
- **Bitcoin community**

---

## License

[MIT](LICENSE) — Built in [Semilla Bitcoin](https://semillabitcoin.com)'s rabbit hole 🕳️🐇
