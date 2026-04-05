"""Configuration from environment variables."""

import os

# Default upstream (overrideable from UI via proxy_state)
ELECTRUM_HOST = os.environ.get("ELECTRUM_HOST", "127.0.0.1")
ELECTRUM_PORT = int(os.environ.get("ELECTRUM_PORT", "50001"))
ELECTRUM_SSL = os.environ.get("ELECTRUM_SSL", "false").lower() in ("true", "1", "yes")
ELECTRUM_SSL_NOVERIFY = os.environ.get("ELECTRUM_SSL_NOVERIFY", "false").lower() in ("true", "1", "yes")

PROXY_PORT = int(os.environ.get("PROXY_PORT", "50005"))
WEB_PORT = int(os.environ.get("WEB_PORT", "4040"))

DB_PATH = os.environ.get("DB_PATH", "data/pool.db")

# Rebroadcast txs that fell out of mempool after this many minutes
REBROADCAST_AFTER_MINUTES = int(os.environ.get("REBROADCAST_AFTER_MINUTES", "10"))

CLIENT_NAME = "broadcast-pool"
PROTOCOL_VERSION = "1.4"

# Encryption key for scheduled txs (Umbrel injects APP_SEED automatically)
APP_SEED = os.environ.get("APP_SEED", "")

# Purge confirmed txs after this many blocks (0 = never purge)
PURGE_AFTER_BLOCKS = int(os.environ.get("PURGE_AFTER_BLOCKS", "1"))

# Genesis hashes for network detection (from server.features)
GENESIS_HASHES = {
    "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f": "mainnet",
    "000000000933ea01ad0ee984209779baaec3ced90fa3f408719526f8d77f4943": "testnet",
    "00000008819873e925422c1ff0f99f7cc9bbb232af63a077a480a3633bee1ef6": "signet",
    "0f9188f13cb7b2c71f2a335e3a4fc328bf5beb436012afca590b1a11466e2206": "regtest",
}
