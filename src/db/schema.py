"""SQLite schema and database initialization."""

import sqlite3
from pathlib import Path

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS retained_txs (
    txid            TEXT PRIMARY KEY,
    raw_hex         TEXT NOT NULL,
    fee_sats        INTEGER NOT NULL,
    fee_rate        REAL NOT NULL,
    vsize           INTEGER NOT NULL,
    amount_sats     INTEGER NOT NULL DEFAULT 0,
    input_count     INTEGER NOT NULL DEFAULT 0,
    output_count    INTEGER NOT NULL DEFAULT 0,
    locktime        INTEGER NOT NULL DEFAULT 0,
    depends_on      TEXT,
    network         TEXT NOT NULL DEFAULT 'mainnet',
    wallet_label    TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'pending',
    target_block    INTEGER,
    sort_order      INTEGER NOT NULL DEFAULT 0,
    error_message   TEXT,
    confirmed_block INTEGER,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    broadcast_at    TEXT
);

CREATE TABLE IF NOT EXISTS retained_tx_inputs (
    txid            TEXT NOT NULL REFERENCES retained_txs(txid) ON DELETE CASCADE,
    prev_txid       TEXT NOT NULL,
    prev_vout       INTEGER NOT NULL,
    scripthash      TEXT NOT NULL,
    value_sats      INTEGER,
    confirmed_height INTEGER,
    PRIMARY KEY (txid, prev_txid, prev_vout)
);

CREATE TABLE IF NOT EXISTS retained_tx_outputs (
    txid            TEXT NOT NULL REFERENCES retained_txs(txid) ON DELETE CASCADE,
    vout            INTEGER NOT NULL,
    scripthash      TEXT NOT NULL,
    value_sats      INTEGER NOT NULL,
    PRIMARY KEY (txid, vout)
);

CREATE INDEX IF NOT EXISTS idx_inputs_scripthash
    ON retained_tx_inputs(scripthash);

CREATE INDEX IF NOT EXISTS idx_outputs_scripthash
    ON retained_tx_outputs(scripthash);

CREATE INDEX IF NOT EXISTS idx_txs_status
    ON retained_txs(status);

CREATE INDEX IF NOT EXISTS idx_txs_target_block
    ON retained_txs(target_block);

CREATE INDEX IF NOT EXISTS idx_txs_network
    ON retained_txs(network);

CREATE TABLE IF NOT EXISTS history_stats (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT NOT NULL,
    network         TEXT NOT NULL,
    tx_type         TEXT NOT NULL,
    wallet          TEXT NOT NULL DEFAULT '',
    count           INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS proxy_state (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL,
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


MIGRATIONS = [
    "ALTER TABLE retained_txs ADD COLUMN amount_sats INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE retained_txs ADD COLUMN input_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE retained_txs ADD COLUMN output_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE retained_txs ADD COLUMN locktime INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE retained_txs ADD COLUMN depends_on TEXT",
    "ALTER TABLE retained_txs ADD COLUMN network TEXT NOT NULL DEFAULT 'mainnet'",
    "ALTER TABLE retained_txs ADD COLUMN wallet_label TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE retained_tx_inputs ADD COLUMN confirmed_height INTEGER",
    """CREATE TABLE IF NOT EXISTS vault_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ephem_pubkey TEXT NOT NULL,
        payload TEXT NOT NULL,
        network TEXT NOT NULL DEFAULT 'mainnet',
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
]


def init_db(db_path: str) -> sqlite3.Connection:
    """Initialize the database, creating tables if needed."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.executescript(SCHEMA_SQL)

    # Run migrations (idempotent — ignores "duplicate column" errors)
    for sql in MIGRATIONS:
        try:
            conn.execute(sql)
        except sqlite3.OperationalError:
            pass  # Column already exists

    conn.commit()
    return conn
