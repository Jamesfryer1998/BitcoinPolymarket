"""
Centralized Configuration for BTC Trading System
"""
import os

# ─────────────────────────────────────────────
# API ENDPOINTS
# ─────────────────────────────────────────────
POLYMARKET_GAMMA_API = "https://gamma-api.polymarket.com"
POLYMARKET_CLOB_API  = "https://clob.polymarket.com"
BINANCE_API          = "https://api.binance.com/api/v3"

# ─────────────────────────────────────────────
# MARKET CONFIGURATION
# ─────────────────────────────────────────────
MARKET_SLUG = "btc-up-or-down-5m"  # Polymarket BTC 5-min market series
SYMBOL = "BTCUSDT"  # Binance trading pair

# ─────────────────────────────────────────────
# STRATEGY PARAMETERS
# ─────────────────────────────────────────────
MIN_PERIODS = 20        # Minimum periods needed for pattern analysis
LOOKBACK_PERIODS = 200  # Number of periods to analyze for patterns (max ~200 due to Binance API 1000 candle limit)

# ─────────────────────────────────────────────
# DATA FILES
# ─────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STORAGE_DIR = os.path.join(BASE_DIR, "data", "storage")

# Create storage directory if it doesn't exist
os.makedirs(STORAGE_DIR, exist_ok=True)

HISTORY_FILE = os.path.join(STORAGE_DIR, "btc_5min_history.json")
PERFORMANCE_FILE_PATTERN = os.path.join(STORAGE_DIR, "btc_strategy_performance_pattern.json")
PERFORMANCE_FILE_SELECTIVE_PATTERN = os.path.join(STORAGE_DIR, "btc_strategy_performance_selective_pattern.json")
ACTIVITY_FEED_FILE = os.path.join(STORAGE_DIR, "activity_feed.json")

# Legacy file for backward compatibility
PERFORMANCE_FILE = os.path.join(STORAGE_DIR, "btc_strategy_performance.json")

# Activity feed settings
MAX_ACTIVITY_ITEMS = 200  # Maximum items to keep in activity feed

# History settings
HISTORY_MAX_DAYS = 7  # Maximum days of history to keep

# ─────────────────────────────────────────────
# FLASK CONFIGURATION
# ─────────────────────────────────────────────
FLASK_HOST = "0.0.0.0"
FLASK_PORT = 8000
FLASK_DEBUG = True

# ─────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────
LOGS_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

LOG_LEVEL = "INFO"
LOG_MAX_DAYS = 7  # Maximum days to keep logs

# ─────────────────────────────────────────────
# TIMING
# ─────────────────────────────────────────────
PERIOD_MINUTES = 5       # 5-minute periods
MID_PERIOD_SECONDS = 150  # 2.5 minutes (2:30 mark)

# ─────────────────────────────────────────────
# BACKTEST CONFIGURATION
# ─────────────────────────────────────────────
DEFAULT_BACKTEST_PERIODS = 1000
MIN_BACKTEST_PERIODS = 100
MAX_BACKTEST_PERIODS = 2000

# ─────────────────────────────────────────────
# TRADING SIMULATION CONFIGURATION
# ─────────────────────────────────────────────
DEFAULT_BET_AMOUNT = 10.0        # Default bet amount in USD
DEFAULT_STARTING_CAPITAL = 1000.0  # Default starting capital in USD
