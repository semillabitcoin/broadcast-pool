# Anti-fee-sniping vía `nLockTime` — Estado del arte por wallet

> **Fecha**: 2026-05-17
> **Contexto**: Reporte derivado para Broadcast Pool. Investiga qué wallets Bitcoin
> aplican `nLockTime` como protección anti-fee-sniping (AFS) por defecto, qué valor
> exacto eligen, y qué implicaciones tiene a nivel de fingerprinting.
> **Audiencia**: técnica-deep. Toda afirmación lleva fuente; las dudas se marcan
> explícitamente.

---

## 1. Executive summary

1. Sólo un subconjunto pequeño de wallets implementa AFS por defecto; la mayoría
   pone `locktime = 0`.
2. **Bitcoin Core** y **Electrum** comparten algoritmo: `locktime = current_height`
   con un 10% de probabilidad de restar `rand(0, 99)` bloques. Si el nodo lleva
   >8 h sin ver bloque nuevo, deshabilitan AFS (`locktime = 0`).
3. **Sparrow** es el único wallet conocido que además implementa
   **[BIP-326](https://bips.dev/326/)** (50% nLockTime / 50% nSequence en inputs
   taproot). Es la implementación más completa.
4. **Liana** añadió AFS en v7.0 (sept 2024); el detalle del randomizado no es
   público.
5. **Trezor Suite** y **Ledger Live** **no** aplican AFS por defecto — locktime
   manual del usuario, default `0`. Sorprende dado su volumen.
6. **Coinjoins** (Wasabi v1/v2, JoinMarket, Whirlpool) usan `locktime = 0` por
   necesidad de coordinación; es su fingerprint característica.
7. **Lightning** (LND, Core Lightning, LDK) aplica AFS en sus txs on-chain de
   sweep/funding desde 2018-2022.
8. **BIP-326 en Bitcoin Core** (PR #24128) sigue cerrado/"up-for-grabs" desde
   febrero 2025: no está en ninguna release de Core hasta esta fecha.

---

## 2. Tabla resumen

De "más estricto AFS" a "sin AFS".

| Wallet                 | Default       | Valor exacto de locktime                                               | Configurable          | Fuente verificable                                                                          |
| ---------------------- | ------------- | ---------------------------------------------------------------------- | --------------------- | ------------------------------------------------------------------------------------------- |
| **Bitcoin Core**       | ON            | `current_height` (90 %) o `current_height - rand(0, 99)` (10 %). Desactivado si tip >8 h stale. | No (fijo en wallet)   | PR [#2340], PR [#6216], PR [#15039]; `src/wallet/wallet.cpp::GetLocktimeForNewTransaction()` |
| **Electrum**           | ON            | Idéntico a Core. Toma `min(chain_height, server_height)`. Devuelve 0 si stale. | No (en UI)            | `electrum/wallet.py::get_locktime_for_new_transaction()`                                    |
| **Sparrow**            | ON + BIP-326  | `current_height` + 50/50 nLockTime/nSequence en taproot                | No                    | [Issue #161 (sparrowwallet/sparrow)][sparrow-161]; BIP-326 acredita a Craig Raw             |
| **Specter Desktop**    | ON            | `current_height` (nearest block). Fix tras [Issue #1101][specter-1101] / PR #1411 (2021) | No confirmado         | Issue #1101; fingerprinting analysis (consentonchain)                                       |
| **Liana**              | ON (≥ v7.0)   | `current_height`. Randomizado al estilo Core no documentado.           | No confirmado         | Release notes v7.0 (2024-09-18)                                                             |
| **BDK** (lib)          | ON (≥ PR #611)| `current_height`; PR #65 (bdk-tx) arregló bugs con inputs CLTV.        | Sí (`enable_anti_fee_sniping`) | [BDK PR #611][bdk-611], [bdk-tx PR #65][bdk-tx-65]                                          |
| **LND** sweeper        | ON            | `current_height` para sweep/close                                      | No                    | [LND PR #2063][lnd-2063] (2018)                                                             |
| **Core Lightning**     | ON (withdrawals) | `current_height` ("the tip")                                        | No                    | [CLN PR #3465][cln-3465] (~2020)                                                            |
| **LDK** (funding)      | ON            | `current_height` en LN funding tx                                      | No                    | [LDK PR #1531][ldk-1531] (2022); Bitcoin Optech                                             |
| **Nunchuk** (libnunchuk)| Probable ON  | Hereda lógica de Bitcoin Core internals                                | Desconocido           | Anuncio libnunchuk: "reusing much of [Core's] logic"                                        |
| **Bitcoin Keeper**     | Probable ON   | Usa BDK con default                                                    | Desconocido           | BDK PR #611; sin confirmación explícita                                                     |
| **Zeus** (embedded LND)| ON (sweeps)   | Hereda LND                                                             | No                    | LND PR #2063                                                                                |
| **Phoenix** (ACINQ)    | ON (vía Eclair)| Hereda lógica Lightning para on-chain                                 | No                    | ACINQ Phoenix splicing arch                                                                 |
| **Wasabi v2** (sends regulares) | INCIERTO | Propuesta de 27 % prob; sin release note confirmando.            | N/D                   | [Issue #2500 (WalletWasabi)][wasabi-2500]                                                   |
| **Green** (GDK)        | INCIERTO      | npm `@ledgerhq/hw-app-btc` mostraba lockTime default=0                 | N/D                   | help.blockstream.com; GDK npm                                                               |
| **Muun**               | Probable OFF  | Sin evidencia de AFS en libwallet (Go)                                 | N/D                   | github.com/muun/libwallet                                                                   |
| **BlueWallet**         | Probable OFF  | Sin evidencia; Issue #1313 es feature-request, no implementación       | N/D                   | bluewallet Issue #1313                                                                      |
| **Aqua** (JAN3)        | INCIERTO      | Sin documentación pública                                              | N/D                   | —                                                                                           |
| **Trezor Suite**       | OFF (default) | "Add Locktime" manual; default=0                                       | Sí (UI manual)        | trezor.io/learn/a/locktime-in-trezor-suite                                                  |
| **Ledger Live**        | OFF           | `lockTime` opcional, default=0                                         | Sí (manual)           | npm `@ledgerhq/hw-app-btc` docs                                                             |
| **Passport / Envoy**   | N/A (firma)   | El coordinator (Envoy/Sparrow) decide                                  | N/D                   | Arquitectura PSBT                                                                           |
| **Coldcard Mk4**       | N/A (firma)   | Coordinator decide; Velocity Limiting EXIGE `locktime == tip`          | N/D                   | coldcard.com/docs/sssp/                                                                     |
| **Krux**               | N/A (firma)   | Coordinator decide                                                     | N/D                   | selfcustody.github.io/krux                                                                  |
| **Bitkey** (Block)     | INCIERTO      | Sin código fuente público                                              | N/D                   | —                                                                                           |
| **Wasabi v1**          | OFF           | `locktime = 0` siempre                                                 | No                    | Wasabi Issue #2500                                                                          |
| **Wasabi v2** (coinjoin)| OFF          | `locktime = 0` (WabiSabi)                                              | No                    | Arquitectura WabiSabi                                                                       |
| **Samourai Whirlpool** | OFF           | `locktime = 0` (Chaumian coinjoin)                                     | No                    | Arquitectura Whirlpool                                                                      |
| **JoinMarket**         | OFF           | Nunca implementado; repo archivado 2026-04-27                          | No                    | [JoinMarket Issue #755][joinmarket-755]                                                     |

---

## 3. Detalle por wallet

### 3.1 Bitcoin Core

Algoritmo en `GetLocktimeForNewTransaction()` (`src/wallet/wallet.cpp`):

- Baseline: `nLockTime = GetLastBlockHeight()` (tip de la cadena).
- 10 % prob: `nLockTime = max(0, nLockTime - GetRandInt(100))`.
- Deshabilitado: si nodo lleva >8 h sin ver bloque nuevo (PR [#15039]),
  vuelve a `locktime = 0`.

Hitos:

- **PR [#2340]** (Peter Todd, 2014): introduce AFS. Merged en Core 0.11 (~2015).
- **PR [#6216]** (2015-12): hace AFS efectivo para el bloque siguiente (off-by-one).
- **PR [#15039]** (maflcko, 2019-01, en Core 0.18): desactiva AFS si nodo offline.
- **Issue [#26527][core-26527]** (abierto): el 10 % de backdating puede producir
  locktimes "imposibles" al gastar UTXOs no confirmados (locktime hijo < locktime
  padre) — fingerprint identificable.
- **PR [#24128][core-24128]** (BIP-326 nSequence taproot): cerrado/up-for-grabs
  2025-02-25 por merge conflicts. No está en ninguna release de Core a 2026-05.

Configurable: no en `sendtoaddress`/GUI. RPC `createrawtransaction` **no** aplica
AFS (el usuario pasa el locktime).

### 3.2 Electrum

Código fuente (`electrum/wallet.py`):

```python
def get_locktime_for_new_transaction(network, *, include_random_component=True):
    if not network:
        return 0
    chain = network.blockchain()
    if chain.is_tip_stale():
        return 0
    chain_height = chain.height()
    server_height = network.get_server_height()
    if server_height < chain_height - 10:
        return 0
    locktime = min(chain_height, server_height)
    if include_random_component:
        if random.randint(0, 9) == 0:
            locktime = max(0, locktime - random.randint(0, 99))
    locktime = max(0, locktime)
    return locktime
```

Idéntico a Core en lógica del 10 %. Adicionalmente usa `min(chain_height, server_height)`
para evitar carreras con el servidor Electrum.

**Issue [#8073][electrum-8073]** (abierto): mismo problema que Core #26527 — no
hacer backdating al gastar UTXOs no confirmados ni al hacer RBF.

### 3.3 Sparrow

**Implementa AFS + BIP-326**: para inputs taproot, alterna 50/50 entre poner el
randomizado en `nLockTime` o en `nSequence` por input. Es el único wallet
conocido que sigue BIP-326 completo.

- [Issue #161][sparrow-161] (cerrado/implementado): "Add anti-fee-sniping code
  using nSequence to help improve privacy of off-chain protocols".
- BIP-326 acredita a Craig Raw (autor de Sparrow) por sugerir el uso de nSequence
  en taproot.

Impacto: las txs taproot de Sparrow son indistinguibles de ciertas settlement
txs de Lightning, ampliando el anonymity set.

### 3.4 Specter Desktop

Antes de mediados de 2021, Specter ponía `locktime = 0` en multisig
([Issue #1101][specter-1101]). PR #1411 lo corrigió a "nearest block height".
Confirmado por fingerprinting analysis externo (consentonchain):

> "nLocktime for Bitcoin Core, Knots, Electrum, Sparrow and Specter is set to
> the nearest block height."

Specter delega firma a HW vía PSBT; el companion construye la tx.

### 3.5 Liana

AFS añadido en **v7.0** (2024-09-18). Release notes:

> "when creating a spend transaction, Liana now uses anti fee sniping algorithm
> based on nLockTime, the most common practice in the industry for such use case."

Coexistencia importante con sus **recovery transactions**, que usan `nSequence`
(CSV) para el timelock relativo; son campos independientes.

Detalle del randomizado interno no documentado públicamente.

### 3.6 BDK / BDK-tx

- [PR #611][bdk-611] (2022): AFS por defecto en BDK.
- [PR #1789][bdk-1789]: txversion default actualizada a 2 (prep BIP-326).
- [bdk-tx PR #65][bdk-tx-65] (2024): arregla bug donde AFS podía invalidar txs
  con inputs CLTV (e.g. Liana recovery paths). Cambia API a
  `anti_fee_sniping: Option<absolute::Height>`.

Cualquier wallet con BDK underneath hereda AFS si no lo sobreescribe.

### 3.7 LND, CLN, LDK

| Proyecto | PR | Comportamiento |
| --- | --- | --- |
| **LND** sweeper | [#2063][lnd-2063] (2018, roasbeef) | "updates sweeper to use nLockTime anti fee sniping" — todas las txs de sweep/close llevan `locktime = current_height` |
| **Core Lightning** | [#3465][cln-3465] (~2020, darosior) | "withdrawal transactions now sets nlocktime to the current tip" |
| **LDK** | [#1531][ldk-1531] (2022) | AFS para LN funding tx |

Nota de protocolo: los 2nd-level HTLC txs (timeout/success) usan
`SIGHASH SINGLE|ANYONECANPAY` y deben compartir nLockTime; en esos casos el
locktime es coordinado, no independiente.

### 3.8 Trezor Suite y Ledger Live

Ambos son los outliers más significativos por volumen.

- **Trezor Suite**: locktime es manual ("Add Locktime" en UI). Default `0`.
  Documentación oficial: trezor.io/learn/a/locktime-in-trezor-suite.
- **Ledger Live**: `lockTime` parámetro opcional, default `0` (npm
  `@ledgerhq/hw-app-btc`). Sin evidencia de AFS automático.

El dispositivo HW firma lo que el host le pasa — la responsabilidad del AFS es
del companion, y ambos companions oficiales no lo aplican.

### 3.9 Coldcard Mk4 — caso especial

Coldcard no construye txs (solo firma PSBT). Pero para su **Velocity Limiting**
(Spending Policy), Coldcard exige `nLockTime == current_best_block_height`
y rechaza PSBTs con locktime pasado o con timestamp en lugar de altura.

Implicación: con Velocity Limiting activado, Coldcard es **incompatible** con
el 10 % de backdating de Core/Electrum. El coordinator debe omitir el
randomizado para esos PSBTs.

### 3.10 Coinjoin clients (Wasabi v1/v2, JoinMarket, Whirlpool)

Todos usan `locktime = 0` por necesidad de coordinación: en una ronda
multi-party, todos los participantes firman la misma tx; si cada uno quisiera
su propio randomizado, la tx no podría existir.

Fingerprint conocida: `nVersion=1, locktime=0` para Wasabi v1 (Issue #2500).
Para Wasabi v2 sends regulares (fuera de coinjoin), Issue #2500 propuso un
27 % prob con block height reciente, pero ninguna release note confirma
implementación.

### 3.11 BlueWallet, Muun, Aqua, Bitkey

Sin evidencia pública de AFS automático en ninguno. Ninguna documentación
oficial menciona `nLockTime` salvo BlueWallet [Issue #1313], que es una
solicitud de timelock manual del usuario (no AFS).

Muun por arquitectura submarine-swap tiene timelocks propios (HTLC refund
paths) que pueden colisionar con AFS estándar — su ausencia probablemente es
intencional.

---

## 4. Casos especiales

### 4.1 Coinjoin y AFS

Tres soluciones posibles:

1. **`locktime = 0`** — adoptado por todos los coinjoin existentes (Wasabi,
   JoinMarket, Whirlpool). El más simple.
2. **Locktime coordinado** — coordinador anuncia `current_height`, todos usan
   ese valor. No implementado por ningún protocolo.
3. **BIP-326 vía nSequence** — cada participante controla su propio nSequence
   por input; permitiría AFS sin coordinación de nLockTime. Sin implementación
   en coinjoin a día de hoy.

Consecuencia: los coinjoin son identificables por `locktime = 0` como
fingerprint.

### 4.2 Lightning Channel Open / Close

| Tipo de tx | AFS posible | Notas |
| --- | --- | --- |
| Funding tx | Sí | LDK lo aplica desde PR #1531 |
| Unilateral close (commit tx) | Restringido | Locktime puede estar fijado por params del canal (CLTV en HTLCs) |
| 2nd-level HTLC (timeout/success) | Restringido | `SIGHASH SINGLE\|ANYONECANPAY` exige mismo nLockTime entre inputs cooperantes |
| Cooperative close | Sí | Sin restricción protocolar |

### 4.3 Taproot script-path vs key-path

- **Key-path**: compatible con AFS por nLockTime o nSequence (BIP-326).
  Sparrow lo aplica.
- **Script-path**: sin restricción técnica salvo que el script contenga CLTV.
  Si `OP_CHECKLOCKTIMEVERIFY` está presente, la tx de gasto necesita
  `nLockTime >= CLTV_value` — esto puede entrar en conflicto con el 10 % de
  backdating (bdk-tx PR #65 arregló exactamente este caso).

### 4.4 Firmware HW antiguo

Firmware viejo de Trezor, Ledger Nano S, Coldcard pre-Mk4 rechazaba
`nLockTime != 0`. Ya no aplica con firmware reciente, pero fue razón histórica
por la que algunos companions evitaban AFS para mantener compatibilidad.

---

## 5. Wallet fingerprinting vía `nLockTime`

### Literatura publicada

- **[b10c — "The stair-pattern in time-locked Bitcoin transactions"][b10c]**:
  identificó el patrón escalera en locktimes (clusters por block heights
  consecutivos). Detectó una entidad anónima con bug off-by-one que la
  identificó hasta que lo corrigieron en early 2020.
- **[achow101/wallet-fingerprinting][achow]**: documenta wallets por
  fingerprint. Confirma textualmente: Core "locktime is either current block
  height or 10% randomly up to 100 blocks back"; Electrum "same behavior as Core".
- **[ishaanam/wallet-fingerprinting][ishaanam]**: estudia 8 wallets (Core,
  Electrum, BlueWallet, Exodus, Trust, Coinbase, Trezor Suite, Ledger Live).
  Imagen `fingerprints_final.png` con tabla de comportamientos.
- **[consentonchain — nLocktime + nVersion fingerprinting][consent]**:
  confirma "Core, Knots, Electrum, Sparrow, Specter → nearest block height".
- **[DISCRYPT (UAB)][discrypt]**: estudio en curso; identificó >30 traits
  fingerprinting. Recomienda AFS como feature a activar por defecto.
- **[BitMEX — Bitcoin Time Locks][bitmex-tl]**: análisis de adopción AFS;
  documenta pico de ~20 % de txs con locktime ≠ 0 en 2015 y declive posterior.
- **[arxiv:2512.16683][arxiv]**: paper sobre reutilizar el campo `nLockTime`
  para meta-protocolos de descubrimiento.
- **Core [Issue #10020][core-10020]**: "Setting nLockTime on all transactions
  allows offline clients to be fingerprinted" — documenta el problema base.

### Tensión AFS vs privacidad

| Comportamiento                          | Consecuencia para privacidad                                                            |
| --------------------------------------- | --------------------------------------------------------------------------------------- |
| `locktime = 0` siempre                  | Fingerprint clara: "wallet sin AFS" (Wasabi v1, JoinMarket, Trezor, Ledger).            |
| `locktime = current_height` siempre     | Fingerprint: "AFS sin randomización"; revela bloque exacto de firma.                    |
| `locktime = current_height` + 10 % back | Fingerprint reducida pero identificable como "Core/Electrum style"; bug #26527 lo agrava.|
| BIP-326 50/50 nLockTime/nSequence       | Indistinguible de Lightning settlement txs en taproot; anonymity set máximo.            |
| Nodo offline >8 h → `locktime = 0`      | Evita repetir mismo locktime durante todo el periodo offline (Core PR #15039).          |

---

## 6. Timeline 2014-2026

| Fecha       | Evento                                                                                                              |
| ----------- | ------------------------------------------------------------------------------------------------------------------- |
| 2014 Q4     | Bitcoin Core PR [#2340] (Peter Todd): introduce AFS. Merged en Core 0.11 (~2015).                                   |
| 2015-12-02  | Core PR [#6216]: hace AFS efectivo para el bloque siguiente (off-by-one fix).                                       |
| 2017-08-31  | JoinMarket [Issue #755][joinmarket-755]: propuesta AFS. Nunca implementada.                                         |
| 2018        | LND PR [#2063][lnd-2063]: sweeper adopta AFS.                                                                       |
| 2019-01-10  | Core PR [#15039]: deshabilita AFS si nodo offline >8 h (Core 0.18).                                                 |
| 2019-11-05  | Wasabi [Issue #2500][wasabi-2500]: "Random nlocktime to prevent fee sniping". Propone 27 % prob.                    |
| 2020 Q1     | CLN PR [#3465][cln-3465]: withdrawal txs adoptan AFS.                                                               |
| 2021-04     | Specter [Issue #1101][specter-1101] detectado; PR #1411 arregla locktime=0 en multisig.                             |
| 2021-06     | Chris Belcher publica propuesta BIP-326 en bitcoin-dev.                                                             |
| 2021-07     | Sparrow [Issue #161][sparrow-161]: solicita BIP-326. Cerrado/implementado.                                          |
| 2022        | BDK PR [#611][bdk-611]: AFS por defecto.                                                                            |
| 2022        | LDK PR [#1531][ldk-1531]: AFS para LN funding txs.                                                                  |
| 2022-03-16  | Bitcoin Optech #191: documenta BIP-326.                                                                             |
| 2023        | BDK PR [#1789][bdk-1789]: default txversion a 2 (prep BIP-326).                                                     |
| 2024-09-18  | **Liana v7.0**: AFS vía nLockTime.                                                                                  |
| 2024        | bdk-tx PR [#65][bdk-tx-65]: fix AFS con inputs CLTV.                                                                |
| 2025-02-25  | Core PR [#24128][core-24128] (BIP-326): cerrado/up-for-grabs. No mergeado.                                          |
| 2026-04-27  | JoinMarket-clientserver archivado. AFS nunca implementado.                                                          |

---

## 7. Implicaciones para Broadcast Pool

BP es un proxy Electrum que ve las txs antes del broadcast. El `nLockTime` de
cada tx entrante es una señal útil:

1. **Identificación heurística del wallet origen** (complemento al
   `wallet_label` que el usuario asigna en import):

    - `locktime = 0` → Trezor Suite, Ledger Live, Wasabi v1, coinjoin clients
       (Wasabi v2/JoinMarket/Whirlpool).
    - `locktime ≈ tip` (sin backdating) → Sparrow (key-path o aleatoriamente),
       Specter, Liana, BDK-based.
    - `locktime ≈ tip - N` con `N ≤ 99` → Core o Electrum (con su 10 % de
       backdating).
    - `locktime ≈ tip` en input taproot con `nSequence` randomizado
       → Sparrow taproot path.

2. **Fact-check de la sección "Cómo funciona"**: la nota actual sobre
   "Bitcoin Core randomiza hasta 100 bloques el 10 % de las txs" es **correcta**;
   se puede ampliar añadiendo:
   *"Core deshabilita la randomización si el nodo lleva más de 8 h sin ver bloque
   nuevo (PR #15039) para no fingerprintear nodos offline."*

3. **Decisión sobre construcción de txs propias**: si en el futuro BP genera
   alguna tx propia (e.g. consolidation, sweep), el comportamiento por defecto
   debería ser `locktime = current_height` sin backdating — más simple, más
   visible, sin riesgo del bug Core #26527.

4. **No alterar locktime en proxy**: BP debe pasar las txs tal cual; modificar
   `nLockTime` cambiaría el txid e invalidaría la firma. Esta es una observación
   trivial pero importante: el campo es signed.

5. **Educación al usuario**: la "Cómo funciona" puede incluir una tabla resumida
   con qué wallets aplican AFS, ayudando al usuario a entender por qué hay txs
   pendientes con locktime futuro vs `0`.

---

## 8. Bibliografía

### PRs y issues clave

- Bitcoin Core PR [#2340] — AFS original
- Bitcoin Core PR [#6216] — AFS efectivo
- Bitcoin Core PR [#15039] — desactivar si offline >8 h
- Bitcoin Core [Issue #26527][core-26527] — backdating con UTXOs no confirmados
- Bitcoin Core PR [#24128][core-24128] — BIP-326 nSequence (no mergeado)
- Bitcoin Core [Issue #10020][core-10020] — fingerprinting offline
- Electrum [Issue #8073][electrum-8073]
- Wasabi [Issue #2500][wasabi-2500]
- JoinMarket [Issue #755][joinmarket-755]
- LND PR [#2063][lnd-2063]
- Core Lightning PR [#3465][cln-3465]
- LDK PR [#1531][ldk-1531]
- BDK PR [#611][bdk-611], PR [#1789][bdk-1789]
- bdk-tx PR [#65][bdk-tx-65]
- Sparrow [Issue #161][sparrow-161]
- Specter [Issue #1101][specter-1101]

### BIPs y documentación

- [BIP-326 — Anti-fee-sniping in taproot transactions (Chris Belcher)](https://bips.dev/326/)
- [Bitcoin Optech — Fee Sniping](https://bitcoinops.org/en/topics/fee-sniping/)

### Análisis de fingerprinting

- [b10c — Stair-pattern in time-locked Bitcoin transactions][b10c]
- [achow101/wallet-fingerprinting][achow]
- [ishaanam/wallet-fingerprinting][ishaanam]
- [consentonchain — Wallet Fingerprinting using nLocktime and nVersion][consent]
- [DISCRYPT (UAB) — Wallet fingerprinting in Bitcoin][discrypt]
- [BitMEX — Bitcoin Time Locks: Security Feature Adoption Analysis][bitmex-tl]
- [arxiv:2512.16683 — Efficient Bitcoin Meta-Protocol Transaction and Data Discovery Through nLockTime Field Repurposing][arxiv]
- [Ishaana blog — Wallet Fingerprints: Detection & Analysis](https://ishaana.com/blog/wallet_fingerprinting/)

### Releases / notas

- [Liana v7.0 — nobsbitcoin.com](https://www.nobsbitcoin.com/liana-v7-0/)
- [Wizardsardine — Liana 7.0 blog](https://wizardsardine.com/blog/liana-7.0-release/)
- [Coldcard SSSP docs — Velocity Limiting locktime requirement](https://coldcard.com/docs/sssp/)
- [BIP-326: Anti-Fee-Sniping as a Privacy Primitive — btrust.tech](https://blog.btrust.tech/bip326-anti-fee-sniping-as-a-privacy-primitive-for-taproot-wallets/)

---

## 9. Confidence assessment

| Afirmación                                                                       | Confianza   | Justificación                                                                  |
| -------------------------------------------------------------------------------- | ----------- | ------------------------------------------------------------------------------ |
| Bitcoin Core: 10 % prob, `rand(0, 99)`, off si stale >8 h                        | Alta        | Código en `wallet.cpp`; PRs #2340, #6216, #15039 verificados                   |
| Electrum: lógica idéntica a Core                                                 | Alta        | Código `wallet.py` extraído                                                    |
| Sparrow implementa BIP-326                                                       | Alta        | Issue #161 cerrado; BIP-326 acredita a Craig Raw                               |
| Specter: nearest block height (fix Issue #1101)                                  | Media-alta  | Issue cerrado con PR; fingerprinting analysis externo confirma                 |
| Liana v7.0: AFS via nLockTime                                                    | Alta        | Release notes oficiales                                                        |
| Wasabi v2 sends regulares                                                        | Baja        | Issue propuso fix; sin release note confirmatorio                              |
| Trezor Suite: locktime manual, default 0                                         | Alta        | Documentación Trezor oficial                                                   |
| Ledger Live: locktime default 0                                                  | Media       | npm package muestra default; sin documentación de AFS                          |
| BlueWallet: sin AFS                                                              | Media       | Issue #1313 es feature-request; sin evidencia de implementación                |
| Muun: sin AFS                                                                    | Media       | Sin evidencia en libwallet; arquitectura submarine-swap                        |
| Bitcoin Core PR #24128: no mergeado a 2026-05                                    | Alta        | GitHub muestra PR cerrado 2025-02-25                                           |
| Adopción global: ~10-20 % de txs con locktime ≠ 0                                | Media       | BitMEX blog; tendencia decreciente desde pico 2015                             |

---

[#2340]: https://github.com/bitcoin/bitcoin/pull/2340
[#6216]: https://github.com/bitcoin/bitcoin/pull/6216
[#15039]: https://github.com/bitcoin/bitcoin/pull/15039
[core-24128]: https://github.com/bitcoin/bitcoin/pull/24128
[core-26527]: https://github.com/bitcoin/bitcoin/issues/26527
[core-10020]: https://github.com/bitcoin/bitcoin/issues/10020
[electrum-8073]: https://github.com/spesmilo/electrum/issues/8073
[wasabi-2500]: https://github.com/WalletWasabi/WalletWasabi/issues/2500
[joinmarket-755]: https://github.com/JoinMarket-Org/joinmarket/issues/755
[lnd-2063]: https://github.com/lightningnetwork/lnd/pull/2063
[cln-3465]: https://github.com/ElementsProject/lightning/pull/3465
[ldk-1531]: https://github.com/lightningdevkit/rust-lightning/pull/1531
[bdk-611]: https://github.com/bitcoindevkit/bdk/pull/611
[bdk-1789]: https://github.com/bitcoindevkit/bdk/pull/1789
[bdk-tx-65]: https://github.com/bitcoindevkit/bdk-tx/pull/65
[sparrow-161]: https://github.com/sparrowwallet/sparrow/issues/161
[specter-1101]: https://github.com/cryptoadvance/specter-desktop/issues/1101
[b10c]: https://b10c.me/observations/01-locktime-stairs/
[achow]: https://github.com/achow101/wallet-fingerprinting
[ishaanam]: https://github.com/ishaanam/wallet-fingerprinting
[consent]: https://consentonchain.github.io/blog/posts/fingerprinting/
[discrypt]: https://www.discrypt.cat/wallet-fingerprinting-in-bitcoin-and-its-privacy-implications/
[bitmex-tl]: https://www.bitmex.com/blog/bitcoin-time-locks
[arxiv]: https://arxiv.org/html/2512.16683
