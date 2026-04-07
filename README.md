# Broadcast Pool

> Proxy Electrum con retransmisión programada de transacciones Bitcoin

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/docker-ghcr.io-blue)](https://github.com/semillabitcoin/broadcast-pool/pkgs/container/broadcast-pool)
[![Umbrel](https://img.shields.io/badge/umbrel-app-purple)](https://github.com/semillabitcoin/umbrel-app-store)
[![Start9](https://img.shields.io/badge/start9-app-orange)](https://github.com/semillabitcoin/broadcast-pool-startos)

Inspirado en la propuesta [Broadcast Pool de Craig Raw](https://github.com/bitcoin/bitcoin/issues/30471).

---

## ¿Qué es?

Broadcast Pool (BP) es un proxy Electrum en tu nodo que se interpone entre tu wallet y tu servidor Electrum. Cuando tu wallet emite una transacción, BP la **retiene** en lugar de retransmitirla inmediatamente y la programa para retransmitirla más tarde, en el bloque, fecha o precio de bitcoin que tú decidas.

Pensado para bitcoiners que quieren gestionar sus transacciones firmadas, con control fino sobre cuándo y cómo se retransmitirán a la mempool. Y todo sin salir de tu nodo.

---

## Casos de uso

- **Migraciones de wallet**: distribuye los movimientos en bloques o días para no dejar una huella obvia de "todo se movió a la vez"
- **Ciclar hoy lo que tendrías que ciclar de aquí 1 año**, con nLockTime ajustado para anti-fee-sniping (privacidad indistinguible de wallets normales)
- **Colateral de emergencia para préstamos Bitcoin**: programa el envío automático de colateral si el precio cae por debajo de un umbral, para evitar liquidaciones
- **Gestión de UTXOs distribuidos en el tiempo**: barridos, consolidaciones y batchs programados

---

## Características

- **Compatible con cualquier wallet Electrum**: Sparrow, Liana, Nunchuk, Electrum, etc.
- **Mainnet, testnet y signet**
- **Tres modos de programación**:
  - Por **bloque** (altura)
  - Por **fecha** (MTP — Median Time Past)
  - Por **precio** de Bitcoin (vía CoinGecko o oráculo on-chain local)
- **Auto-detección** de servidores Electrum y oráculos de precio en la red local (Umbrel, Start9)
- **Auto-programación** cuando una wallet firma con `nLockTime` futuro
- **Bóveda cifrada NIP-44 (Nostr)** para historial: solo descifrable con tu clave nsec
- **UI web responsive** (móvil y escritorio)
- **Sin telemetría, sin tracking**: tu nodo, tus datos, tus transacciones

### Características experimentales

- **Faking blockheight para Liana**: BP puede mostrar a Liana y otras wallets una altura de bloque fingida para que firme transacciones con `nLockTime` meses (o años) en el futuro, mejorando la privacidad on-chain. Liana no valida PoW (solo continuidad de cadena), por lo que esto funciona sin romper el flujo.

---

## Instalación

### Umbrel

1. Abre la App Store de Umbrel
2. Ve a **Community App Stores** → **Add Store**
3. Pega: `https://github.com/semillabitcoin/umbrel-app-store`
4. Instala **Broadcast Pool**

### Start9

Broadcast Pool aún no está en el marketplace oficial de Start9, así que la instalación se hace por **sideload** manual:

1. Descarga el `.s9pk` correspondiente a tu arquitectura desde [releases](https://github.com/semillabitcoin/broadcast-pool-startos/releases/latest):
   - `broadcast-pool_x86_64.s9pk` (PCs / servidores Intel/AMD)
   - `broadcast-pool_aarch64.s9pk` (Raspberry Pi / ARM)
2. En StartOS: **Marketplace > Sideload** → sube el `.s9pk`

> ⚠️ **Sobre las actualizaciones en Start9:** las apps sideloadeadas no se actualizan automáticamente. Cada nueva versión hay que descargar el `.s9pk` actualizado y volver a sideloadearlo. Estamos trabajando para entrar en el registry oficial de Start9 y resolver esto.

### Docker

```bash
docker run -d \
  --name broadcast-pool \
  -p 4040:4040 \
  -p 50005:50005 \
  -v $(pwd)/data:/data \
  -e ELECTRUM_HOST=tu-servidor-electrum \
  -e ELECTRUM_PORT=50001 \
  -e APP_SEED=tu-seed-aleatorio-de-32-chars \
  ghcr.io/semillabitcoin/broadcast-pool:latest
```

### Local (desarrollo)

```bash
git clone https://github.com/semillabitcoin/broadcast-pool
cd broadcast-pool
pip install -r requirements.txt
python3 -m src.main
```

Variables de entorno:

| Variable | Default | Descripción |
|---|---|---|
| `WEB_PORT` | `4040` | Puerto del dashboard web |
| `PROXY_PORT` | `50005` | Puerto del proxy Electrum (TCP) |
| `WEB_BIND` | `127.0.0.1` | Interface del web |
| `ELECTRUM_HOST` | `127.0.0.1` | Host del servidor Electrum upstream |
| `ELECTRUM_PORT` | `50001` | Puerto del servidor Electrum |
| `ELECTRUM_SSL` | `false` | Usar SSL contra el upstream |
| `DB_PATH` | `data/pool.db` | Ruta de la base de datos SQLite |
| `APP_SEED` | _(vacío)_ | Clave para cifrar tx en reposo |
| `BP_AUTH_TOKEN` | _(vacío)_ | Token de autenticación de la API (opcional) |

---

## Cómo funciona

```
       ┌──────────┐                    ┌──────────────┐
       │  Wallet  │  ──── Electrum ───▶│  BP proxy    │
       │ (Sparrow │  ◀──── retorno ────│  :50005      │
       │  Liana)  │                    └──────┬───────┘
       └──────────┘                           │
                                              │ broadcast interceptado
                                              ▼
                                       ┌──────────────┐
                                       │  Retención   │
                                       │  (SQLite)    │
                                       └──────┬───────┘
                                              │
                            ┌─────────────────┼─────────────────┐
                            ▼                 ▼                 ▼
                       ┌─────────┐      ┌─────────┐      ┌──────────┐
                       │ Bloque  │      │  MTP    │      │ Precio   │
                       │ trigger │      │ trigger │      │ trigger  │
                       └────┬────┘      └────┬────┘      └────┬─────┘
                            └─────────────────┴─────────────────┘
                                              │
                                              ▼
                                    ┌────────────────────┐
                                    │ Electrum upstream  │
                                    │ (tu nodo)          │
                                    └────────────────────┘
```

1. Tu wallet se conecta al proxy de BP (puerto 50005) en lugar de directamente a tu servidor Electrum
2. Cuando emites una transacción, BP la **intercepta**, la guarda en su base de datos y devuelve el `txid` a la wallet (que cree que se ha emitido)
3. La wallet ve la tx como pendiente en su mempool virtual (BP la sirve consistentemente al servidor Electrum)
4. Tú decides desde el dashboard cuándo emitirla: en un bloque concreto, una fecha (MTP), o cuando el precio cruce un umbral
5. Cuando se cumple la condición, BP retransmite la tx a la red vía el electrum de tu nodo

---

## Configuración

Toda la configuración se hace desde la pestaña **Ajustes** del dashboard web:

1. **Conexión a servidor Electrum**: auto-detecta servidores locales (Electrs, Fulcrum) o configura uno manual
2. **Cómo acumular transacciones**: muestra la dirección a la que tu wallet debe conectarse
3. **Comportamiento**: auto-scheduling, retransmisión por precio, faking blockheight
4. **Bóveda cifrada (Nostr)**: configura una `npub` para guardar el historial cifrado
5. **Otras preferencias**: idioma (ES/EN), unidad (BTC/sats)

---

## Arquitectura técnica

- **Stack**: Python 3.12 + asyncio + aiohttp + SQLite (WAL mode)
- **Tres componentes**: proxy TCP Electrum (`src/proxy/`), scheduler de bloques/precio (`src/scheduler/`), web API + dashboard (`src/web/`)
- **Cifrado**:
  - `APP_SEED` cifra las transacciones retenidas en reposo (AES + HMAC)
  - NIP-44 cifra el historial ya confirmado en la bóveda Nostr
- **Sin dependencias externas en runtime**: todo corre dentro del container
- **Persistencia**: SQLite con WAL para concurrencia entre el proxy, el scheduler y la API
- **Multi-arquitectura**: builds amd64 + arm64 (Raspberry Pi compatible)

---

## Seguridad y privacidad

- **Zero trust con upstream**: BP no envía ningún dato sensible al servidor Electrum más allá de lo estrictamente necesario para el protocolo
- **Sin telemetría, sin tracking, sin analytics**
- **`raw_hex` cifrado** en SQLite cuando `APP_SEED` está configurado
- **API de auth opcional** con `BP_AUTH_TOKEN` (Umbrel/Start9 ya gestionan auth a nivel de proxy)
- **Bóveda solo descifrable por el usuario**: BP usa criptografía asimétrica basada en claves Nostr
- **Auditado**: revisión de seguridad continua. Reporta issues en [GitHub Issues](https://github.com/semillabitcoin/broadcast-pool/issues)

### Recomendaciones

- Configura `APP_SEED` con un valor aleatorio fuerte (Umbrel y Start9 lo generan automáticamente)
- Usa una **npub burner** para la bóveda Nostr, no tu identidad principal
- **No expongas el proxy Electrum (50005) a Tor ni a redes públicas**

---

## Contribuir

Pull requests bienvenidas. Issues y feedback en [GitHub Issues](https://github.com/semillabitcoin/broadcast-pool/issues).

```bash
git clone https://github.com/semillabitcoin/broadcast-pool
cd broadcast-pool
pip install -r requirements.txt
python3 -m src.main
# Dashboard en http://localhost:4040
```

---

## Créditos

- **[Craig Raw](https://github.com/craigraw)** — propuesta original [Broadcast Pool](https://github.com/bitcoin/bitcoin/issues/30471) y autor de Sparrow Wallet
- **[Wizardsardine](https://wizardsardine.com)** — Liana Wallet (Miniscript pioneer)
- **[Start9 Labs](https://start9.com)** — StartOS y SDK
- **[Umbrel](https://umbrel.com)** — umbrelOS y App Framework
- **Bitcoin community**

---

## Licencia

[MIT](LICENSE) — Hecho en la madriguera de [Semilla Bitcoin](https://semillabitcoin.com) 🕳️🐇
