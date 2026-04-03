"""TxStore — CRUD operations over SQLite for retained transactions."""

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime

from src.pool.tx_parser import ParsedTx


@dataclass
class RetainedTx:
    txid: str
    raw_hex: str
    fee_sats: int
    fee_rate: float
    vsize: int
    amount_sats: int
    input_count: int
    output_count: int
    locktime: int
    depends_on: str | None
    network: str
    wallet_label: str
    status: str
    target_block: int | None
    sort_order: int
    error_message: str | None
    confirmed_block: int | None
    created_at: str
    updated_at: str
    broadcast_at: str | None


@dataclass
class RetainedInput:
    txid: str
    prev_txid: str
    prev_vout: int
    scripthash: str
    value_sats: int | None
    confirmed_height: int | None


@dataclass
class RetainedOutput:
    txid: str
    vout: int
    scripthash: str
    value_sats: int


class TxStore:
    """Thread-safe SQLite store for retained transactions."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._lock = threading.Lock()
        self._network = "mainnet"  # Active network, set by proxy on connect

    @property
    def network(self) -> str:
        return self._network

    @network.setter
    def network(self, value: str) -> None:
        self._network = value

    def save_retained_tx(self, parsed: ParsedTx, raw_hex: str, wallet_label: str = "") -> None:
        """Save a new retained transaction with its inputs and outputs."""
        amount_sats = sum(out.value_sats for out in parsed.outputs)

        with self._lock:
            # Next sort_order
            row = self._conn.execute(
                "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM retained_txs WHERE network = ?",
                (self._network,),
            ).fetchone()
            next_order = row[0]

            self._conn.execute(
                """INSERT OR REPLACE INTO retained_txs
                   (txid, raw_hex, fee_sats, fee_rate, vsize, amount_sats, input_count, output_count, locktime, network, wallet_label, status, sort_order)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
                (parsed.txid, raw_hex, parsed.fee_sats, parsed.fee_rate,
                 parsed.vsize, amount_sats, len(parsed.inputs), len(parsed.outputs),
                 parsed.locktime, self._network, wallet_label, next_order),
            )

            for inp in parsed.inputs:
                self._conn.execute(
                    """INSERT OR REPLACE INTO retained_tx_inputs
                       (txid, prev_txid, prev_vout, scripthash, value_sats, confirmed_height)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (parsed.txid, inp.prev_txid, inp.prev_vout,
                     inp.scripthash, inp.value_sats, inp.confirmed_height),
                )

            for i, out in enumerate(parsed.outputs):
                self._conn.execute(
                    """INSERT OR REPLACE INTO retained_tx_outputs
                       (txid, vout, scripthash, value_sats)
                       VALUES (?, ?, ?, ?)""",
                    (parsed.txid, i, out.scripthash, out.value_sats),
                )

            self._conn.commit()

    def get_all_txs(self, status: str | None = None, network: str | None = None) -> list[RetainedTx]:
        """Get retained transactions, filtered by active network and optionally by status."""
        net = network or self._network
        if status:
            rows = self._conn.execute(
                "SELECT * FROM retained_txs WHERE network = ? AND status = ? ORDER BY sort_order",
                (net, status),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM retained_txs WHERE network = ? ORDER BY sort_order",
                (net,),
            ).fetchall()
        return [RetainedTx(**dict(r)) for r in rows]

    def get_tx(self, txid: str) -> RetainedTx | None:
        """Get a single retained transaction by txid."""
        row = self._conn.execute(
            "SELECT * FROM retained_txs WHERE txid = ?", (txid,)
        ).fetchone()
        return RetainedTx(**dict(row)) if row else None

    def get_active_txs(self) -> list[RetainedTx]:
        """Get txs that are pending or scheduled (not yet broadcast) for active network."""
        rows = self._conn.execute(
            "SELECT * FROM retained_txs WHERE network = ? AND status IN ('pending', 'scheduled') ORDER BY sort_order",
            (self._network,),
        ).fetchall()
        return [RetainedTx(**dict(r)) for r in rows]

    def get_due_txs(self, current_height: int) -> list[RetainedTx]:
        """Get scheduled txs whose target_block <= current_height for active network."""
        rows = self._conn.execute(
            """SELECT * FROM retained_txs
               WHERE network = ? AND status = 'scheduled' AND target_block <= ?
               ORDER BY target_block, sort_order""",
            (self._network, current_height),
        ).fetchall()
        return [RetainedTx(**dict(r)) for r in rows]

    def get_inputs(self, txid: str) -> list[RetainedInput]:
        rows = self._conn.execute(
            "SELECT * FROM retained_tx_inputs WHERE txid = ?", (txid,)
        ).fetchall()
        return [RetainedInput(**dict(r)) for r in rows]

    def get_outputs(self, txid: str) -> list[RetainedOutput]:
        rows = self._conn.execute(
            "SELECT * FROM retained_tx_outputs WHERE txid = ?", (txid,)
        ).fetchall()
        return [RetainedOutput(**dict(r)) for r in rows]

    def get_retained_for_scripthash(self, scripthash: str) -> list[RetainedTx]:
        """Get active retained txs that touch a given scripthash (as input or output) for active network."""
        rows = self._conn.execute(
            """SELECT DISTINCT t.* FROM retained_txs t
               LEFT JOIN retained_tx_inputs i ON t.txid = i.txid
               LEFT JOIN retained_tx_outputs o ON t.txid = o.txid
               WHERE (i.scripthash = ? OR o.scripthash = ?)
                 AND t.network = ?
                 AND t.status IN ('pending', 'scheduled')
               ORDER BY t.sort_order""",
            (scripthash, scripthash, self._network),
        ).fetchall()
        return [RetainedTx(**dict(r)) for r in rows]

    def get_spent_outpoints_for_scripthash(self, scripthash: str) -> set[tuple[str, int]]:
        """Get outpoints spent by active retained txs for a scripthash on active network."""
        rows = self._conn.execute(
            """SELECT i.prev_txid, i.prev_vout
               FROM retained_tx_inputs i
               JOIN retained_txs t ON t.txid = i.txid
               WHERE i.scripthash = ?
                 AND t.network = ?
                 AND t.status IN ('pending', 'scheduled')""",
            (scripthash, self._network),
        ).fetchall()
        return {(r["prev_txid"], r["prev_vout"]) for r in rows}

    def get_retained_outputs_for_scripthash(self, scripthash: str) -> list[RetainedOutput]:
        """Get outputs of active retained txs destined to a scripthash on active network."""
        rows = self._conn.execute(
            """SELECT o.* FROM retained_tx_outputs o
               JOIN retained_txs t ON t.txid = o.txid
               WHERE o.scripthash = ?
                 AND t.network = ?
                 AND t.status IN ('pending', 'scheduled')""",
            (scripthash, self._network),
        ).fetchall()
        return [RetainedOutput(**dict(r)) for r in rows]

    def get_oldest_coin_age(self, txid: str, current_height: int) -> int | None:
        """Get the age in blocks of the oldest input UTXO.
        Returns 0 for unconfirmed inputs (mempool/CPFP). None only if no inputs resolved."""
        rows = self._conn.execute(
            "SELECT confirmed_height FROM retained_tx_inputs WHERE txid = ?",
            (txid,),
        ).fetchall()

        if not rows:
            return None

        heights = [r["confirmed_height"] for r in rows if r["confirmed_height"] is not None]

        if not heights:
            return None

        min_h = min(heights)

        # confirmed_height == 0 means unconfirmed (mempool) — age is 0
        if min_h == 0:
            return 0

        if current_height > 0:
            return current_height - min_h

        return None

    def get_raw_hex(self, txid: str) -> str:
        """Get decrypted raw_hex for a transaction."""
        row = self._conn.execute(
            "SELECT raw_hex FROM retained_txs WHERE txid = ?", (txid,)
        ).fetchone()
        if not row or not row["raw_hex"]:
            return ""
        from src.pool.crypto import decrypt, is_encrypted
        from src import config
        raw = row["raw_hex"]
        if is_encrypted(raw):
            return decrypt(raw, config.APP_SEED)
        return raw

    def get_scripthashes_for_tx(self, txid: str) -> set[str]:
        """Get all scripthashes touched by a tx (inputs + outputs)."""
        rows = self._conn.execute(
            """SELECT scripthash FROM retained_tx_inputs WHERE txid = ?
               UNION
               SELECT scripthash FROM retained_tx_outputs WHERE txid = ?""",
            (txid, txid),
        ).fetchall()
        return {r["scripthash"] for r in rows}

    def update_status(self, txid: str, status: str, error: str | None = None) -> None:
        with self._lock:
            # Encrypt raw_hex when moving to scheduled
            if status == "scheduled":
                from src.pool.crypto import encrypt, is_encrypted
                from src import config
                if config.APP_SEED:
                    row = self._conn.execute(
                        "SELECT raw_hex FROM retained_txs WHERE txid = ?", (txid,)
                    ).fetchone()
                    if row and row["raw_hex"] and not is_encrypted(row["raw_hex"]):
                        enc = encrypt(row["raw_hex"], config.APP_SEED)
                        self._conn.execute(
                            "UPDATE retained_txs SET raw_hex = ? WHERE txid = ?",
                            (enc, txid),
                        )

            self._conn.execute(
                """UPDATE retained_txs
                   SET status = ?, error_message = ?, updated_at = datetime('now')
                   WHERE txid = ?""",
                (status, error, txid),
            )
            self._conn.commit()

    def set_depends_on(self, txid: str, parent_txid: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE retained_txs SET depends_on=?, updated_at=datetime('now') WHERE txid=?",
                (parent_txid, txid),
            )
            self._conn.commit()

    def update_target_block(self, txid: str, target_block: int, keep_status: bool = False) -> None:
        with self._lock:
            if keep_status:
                self._conn.execute(
                    """UPDATE retained_txs
                       SET target_block = ?, updated_at = datetime('now')
                       WHERE txid = ?""",
                    (target_block, txid),
                )
            else:
                self._conn.execute(
                    """UPDATE retained_txs
                       SET target_block = ?, status = 'scheduled', updated_at = datetime('now')
                       WHERE txid = ?""",
                    (target_block, txid),
                )
            self._conn.commit()

    def update_broadcast_time(self, txid: str) -> None:
        with self._lock:
            self._conn.execute(
                """UPDATE retained_txs
                   SET broadcast_at = datetime('now'), updated_at = datetime('now')
                   WHERE txid = ?""",
                (txid,),
            )
            self._conn.commit()

    def set_confirmed(self, txid: str, block_height: int) -> None:
        with self._lock:
            self._conn.execute(
                """UPDATE retained_txs
                   SET status = 'confirmed', confirmed_block = ?, updated_at = datetime('now')
                   WHERE txid = ?""",
                (block_height, txid),
            )
            self._conn.commit()

        # Immediately encrypt to vault if npub configured
        self._encrypt_to_vault(txid)

    def _encrypt_to_vault(self, txid: str) -> None:
        """Encrypt a confirmed/abandoned tx to the vault if npub is set."""
        npub = self.get_state("npub")
        if not npub:
            return

        tx = self.get_tx(txid)
        if not tx:
            return

        # Check if already in vault (avoid duplicates)
        existing = self._conn.execute(
            "SELECT id FROM vault_entries WHERE payload LIKE ? LIMIT 1",
            (f"%{txid[:16]}%",),
        ).fetchone()
        if existing:
            return

        # Classify
        n_in, n_out = tx.input_count, tx.output_count
        if n_in == 1 and n_out == 1:
            tx_type = "barrido"
        elif n_out > 2:
            tx_type = "lotes"
        elif n_out > 1:
            tx_type = "pago"
        elif n_in > 1:
            tx_type = "consolidacion"
        else:
            tx_type = "otro"

        wallet = tx.wallet_label.split()[0] if tx.wallet_label else ""

        try:
            from src.pool.nip44 import encrypt_for_npub
            vault_data = {
                "txid": tx.txid,
                "tx_type": tx_type,
                "wallet": wallet,
                "amount_sats": tx.amount_sats,
                "fee_sats": tx.fee_sats,
                "fee_rate": tx.fee_rate,
                "vsize": tx.vsize,
                "status": tx.status,
                "confirmed_block": tx.confirmed_block,
                "target_block": tx.target_block,
                "broadcast_at": tx.broadcast_at,
                "created_at": tx.created_at,
                "input_count": tx.input_count,
                "output_count": tx.output_count,
            }
            encrypted = encrypt_for_npub(vault_data, npub)
            with self._lock:
                self._conn.execute(
                    "INSERT INTO vault_entries (ephem_pubkey, payload, network) VALUES (?, ?, ?)",
                    (encrypted["ephem_pubkey"], encrypted["payload"], tx.network),
                )
                self._conn.commit()
            import logging
            logging.getLogger(__name__).info("Encrypted tx %s to vault", txid[:16])
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Vault encrypt failed for %s: %s", txid[:16], e)

    def delete_tx(self, txid: str) -> bool:
        """Delete a retained tx. Returns True if deleted."""
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM retained_txs WHERE txid = ? AND status IN ('pending', 'scheduled')",
                (txid,),
            )
            self._conn.commit()
            return cursor.rowcount > 0

    def reorder(self, txid: str, direction: str) -> None:
        """Move a tx up or down in sort order."""
        with self._lock:
            current = self._conn.execute(
                "SELECT sort_order FROM retained_txs WHERE txid = ?", (txid,)
            ).fetchone()
            if not current:
                return

            current_order = current["sort_order"]

            if direction == "up":
                neighbor = self._conn.execute(
                    """SELECT txid, sort_order FROM retained_txs
                       WHERE sort_order < ? ORDER BY sort_order DESC LIMIT 1""",
                    (current_order,),
                ).fetchone()
            else:
                neighbor = self._conn.execute(
                    """SELECT txid, sort_order FROM retained_txs
                       WHERE sort_order > ? ORDER BY sort_order ASC LIMIT 1""",
                    (current_order,),
                ).fetchone()

            if neighbor:
                # Swap sort_order values
                self._conn.execute(
                    "UPDATE retained_txs SET sort_order = ? WHERE txid = ?",
                    (neighbor["sort_order"], txid),
                )
                self._conn.execute(
                    "UPDATE retained_txs SET sort_order = ? WHERE txid = ?",
                    (current_order, neighbor["txid"]),
                )
                self._conn.commit()

    def auto_assign(self, base_block: int, offset: int, txids: list[str] | None = None) -> int:
        """Auto-assign target blocks to pending txs on active network. Returns count assigned."""
        with self._lock:
            if txids:
                placeholders = ",".join("?" * len(txids))
                rows = self._conn.execute(
                    f"""SELECT txid FROM retained_txs
                        WHERE txid IN ({placeholders}) AND network = ? AND status = 'pending'
                        ORDER BY sort_order""",
                    [*txids, self._network],
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT txid FROM retained_txs WHERE network = ? AND status = 'pending' ORDER BY sort_order",
                    (self._network,),
                ).fetchall()

            count = 0
            for i, row in enumerate(rows):
                target = base_block + (offset * i)
                self._conn.execute(
                    """UPDATE retained_txs
                       SET target_block = ?, status = 'scheduled', updated_at = datetime('now')
                       WHERE txid = ?""",
                    (target, row["txid"]),
                )
                count += 1

            self._conn.commit()
            return count

    # -- Proxy state --

    def get_state(self, key: str) -> str | None:
        row = self._conn.execute(
            "SELECT value FROM proxy_state WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None

    def set_state(self, key: str, value: str) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT OR REPLACE INTO proxy_state (key, value, updated_at)
                   VALUES (?, ?, datetime('now'))""",
                (key, value),
            )
            self._conn.commit()

    def get_current_height(self) -> int:
        val = self.get_state("current_height")
        return int(val) if val else 0

    # -- Upstream settings --

    def get_upstream(self) -> tuple[str, int, bool]:
        """Get the configured upstream host:port:ssl (from DB or env defaults)."""
        from src import config
        host = self.get_state("upstream_host") or config.ELECTRUM_HOST
        port = self.get_state("upstream_port") or str(config.ELECTRUM_PORT)
        ssl_str = self.get_state("upstream_ssl")
        use_ssl = ssl_str == "true" if ssl_str is not None else config.ELECTRUM_SSL
        return host, int(port), use_ssl

    def set_upstream(self, host: str, port: int, use_ssl: bool = False) -> None:
        self.set_state("upstream_host", host)
        self.set_state("upstream_port", str(port))
        self.set_state("upstream_ssl", "true" if use_ssl else "false")

    def get_detected_network(self) -> str:
        return self.get_state("network") or "mainnet"

    def update_input(self, txid: str, prev_txid: str, prev_vout: int,
                     scripthash: str, value_sats: int, confirmed_height: int) -> None:
        """Update a retained tx input with resolved data."""
        with self._lock:
            self._conn.execute(
                """UPDATE retained_tx_inputs
                   SET scripthash=?, value_sats=?, confirmed_height=?
                   WHERE txid=? AND prev_txid=? AND prev_vout=?""",
                (scripthash, value_sats, confirmed_height, txid, prev_txid, prev_vout),
            )
            self._conn.commit()

    def update_fee(self, txid: str, fee_sats: int, fee_rate: float) -> None:
        """Update fee for a retained tx."""
        with self._lock:
            self._conn.execute(
                "UPDATE retained_txs SET fee_sats=?, fee_rate=? WHERE txid=?",
                (fee_sats, round(fee_rate, 1), txid),
            )
            self._conn.commit()

    def set_detected_network(self, network: str) -> None:
        self.set_state("network", network)
        self._network = network

    # -- Purge confirmed txs --

    def purge_confirmed(self, current_height: int, after_blocks: int = 6) -> int:
        """Purge sensitive data from confirmed txs that are deep enough.
        Saves anonymous stats before purging. Returns count purged."""
        if after_blocks <= 0:
            return 0

        with self._lock:
            rows = self._conn.execute(
                """SELECT txid, fee_sats, fee_rate, vsize, amount_sats,
                          input_count, output_count, network, wallet_label,
                          status, target_block, confirmed_block, broadcast_at, created_at
                   FROM retained_txs
                   WHERE status IN ('confirmed', 'abandoned', 'replaced')
                     AND (
                       (confirmed_block IS NOT NULL AND confirmed_block > 0 AND confirmed_block <= ?)
                       OR (status IN ('abandoned', 'replaced'))
                     )""",
                (current_height - after_blocks,),
            ).fetchall()

            if not rows:
                return 0

            for r in rows:
                # Determine tx type for stats
                n_in = r["input_count"]
                n_out = r["output_count"]
                if n_in == 1 and n_out == 1:
                    tx_type = "barrido"
                elif n_out > 2:
                    tx_type = "lotes"
                elif n_out > 1:
                    tx_type = "pago"
                elif n_in > 1:
                    tx_type = "consolidacion"
                else:
                    tx_type = "otro"

                wallet = r["wallet_label"] or ""
                # Extract just the wallet name (e.g. "Sparrow" from "Sparrow 2.1.0")
                wallet_short = wallet.split()[0] if wallet else ""

                date = None
                # Estimate date from block height (~10 min per block)
                # Just use today's date for simplicity
                from datetime import date as d
                date = d.today().isoformat()

                # Save anonymous stat
                self._conn.execute(
                    """INSERT INTO history_stats (date, network, tx_type, wallet, count)
                       VALUES (?, ?, ?, ?, 1)""",
                    (date, r["network"], tx_type, wallet_short),
                )

                # Encrypt to vault if npub configured
                npub = self.get_state("npub")
                if npub:
                    try:
                        from src.pool.nip44 import encrypt_for_npub
                        vault_data = {
                            "txid": r["txid"],
                            "tx_type": tx_type,
                            "wallet": wallet_short,
                            "amount_sats": r["amount_sats"],
                            "fee_sats": r["fee_sats"],
                            "fee_rate": r["fee_rate"],
                            "vsize": r["vsize"],
                            "status": r["status"],
                            "confirmed_block": r["confirmed_block"],
                            "target_block": r["target_block"],
                            "broadcast_at": r["broadcast_at"],
                            "created_at": r["created_at"],
                            "input_count": r["input_count"],
                            "output_count": r["output_count"],
                        }
                        encrypted = encrypt_for_npub(vault_data, npub)
                        self._conn.execute(
                            "INSERT INTO vault_entries (ephem_pubkey, payload, network) VALUES (?, ?, ?)",
                            (encrypted["ephem_pubkey"], encrypted["payload"], r["network"]),
                        )
                    except Exception as e:
                        import logging
                        logging.getLogger(__name__).warning(
                            "Vault encryption failed for %s: %s", r["txid"][:16], e
                        )

                # Delete the tx and all its inputs/outputs entirely
                self._conn.execute(
                    "DELETE FROM retained_tx_inputs WHERE txid = ?", (r["txid"],)
                )
                self._conn.execute(
                    "DELETE FROM retained_tx_outputs WHERE txid = ?", (r["txid"],)
                )
                self._conn.execute(
                    "DELETE FROM retained_txs WHERE txid = ?", (r["txid"],)
                )

            self._conn.commit()
            return len(rows)
