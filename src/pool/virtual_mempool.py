"""Virtual mempool — injects retained txs into Electrum responses."""

from src.pool.store import TxStore, RetainedTx, RetainedOutput
from src.pool.status_hash import compute_status_hash


class VirtualMempool:
    """Modifies Electrum responses to include retained transactions."""

    def __init__(self, store: TxStore):
        self.store = store

    def inject_in_history(self, history: list[dict], scripthash: str) -> list[dict]:
        """Inject retained txs into a get_history response."""
        retained = self.store.get_retained_for_scripthash(scripthash)
        existing_txids = {h["tx_hash"] for h in history}

        for tx in retained:
            if tx.txid not in existing_txids:
                entry = {"tx_hash": tx.txid, "height": 0}
                if tx.fee_sats:
                    entry["fee"] = tx.fee_sats
                history.append(entry)

        return history

    def filter_listunspent(self, utxos: list[dict], scripthash: str) -> list[dict]:
        """Remove spent UTXOs and add new outputs from retained txs."""
        spent = self.store.get_spent_outpoints_for_scripthash(scripthash)

        # Filter out spent UTXOs
        filtered = [
            u for u in utxos
            if (u["tx_hash"], u["tx_pos"]) not in spent
        ]

        # Add outputs from retained txs destined to this scripthash
        retained_outputs = self.store.get_retained_outputs_for_scripthash(scripthash)
        existing = {(u["tx_hash"], u["tx_pos"]) for u in filtered}

        for out in retained_outputs:
            if (out.txid, out.vout) not in existing:
                filtered.append({
                    "tx_hash": out.txid,
                    "tx_pos": out.vout,
                    "height": 0,
                    "value": out.value_sats,
                })

        return filtered

    def compute_modified_status_hash(
        self, real_history: list[dict], scripthash: str
    ) -> str | None:
        """Compute status_hash including retained txs."""
        combined = self.inject_in_history(list(real_history), scripthash)
        return compute_status_hash(combined)

    def has_retained_for_scripthash(self, scripthash: str) -> bool:
        """Check if there are any active retained txs for this scripthash."""
        return len(self.store.get_retained_for_scripthash(scripthash)) > 0
