# BTC 5-Min Trading Strategy

A Bitcoin trading strategy system for Polymarket's 5-minute BTC markets with live trading, backtesting capabilities, and a real-time web dashboard.

## Overview

This project implements two trading strategies for Polymarket's BTC 5-minute markets:
- **Pattern-Based Strategy**: Analyzes historical price patterns to make predictions
- **Selective Pattern Strategy**: Enhanced pattern strategy that trades only high-confidence setups with volatility filtering and momentum acceleration

## Features

### 🌐 Web Dashboard (NEW!)
- **Real-time Trading Dashboard**:
  - Live BTC price display with change indicators
  - Historical price chart (last 100 periods)
  - Run both strategies simultaneously with toggle controls
  - Strategy performance cards with win rates and stats
  - Live activity feed showing predictions and results
  - Side-by-side strategy comparison

- **Interactive Backtesting Lab**:
  - Web-based backtest configuration
  - Adjustable parameters (strategy, periods)
  - Real-time progress updates
  - Beautiful results visualization with charts
  - Strategy comparison mode
  - Export results (JSON)

### 📊 CLI Tools

- **Live Trading** (`polymarket_btc_strategy.py`):
  - Real-time BTC price tracking from Binance
  - Synchronized to 5-minute market boundaries
  - Mid-period validation and position reversals
  - Performance tracking and win rate statistics
  - Automatic historical data backfilling

- **Backtesting** (`backtest.py`):
  - Test strategies on historical data
  - Chronological walk-through (no look-ahead bias)
  - Comprehensive performance metrics
  - Configurable test periods
  - JSON output for analysis

## Installation

```bash
# Install all dependencies
pip install -r requirements.txt

# Or minimal CLI-only installation
pip install requests colorama
```

## Usage Examples

### Web Dashboard (Recommended)

```bash
# Start the web dashboard
python run_web.py

# Then open your browser to:
# http://localhost:8000
```

**Features:**
- **Live Trading Tab**:
  - Toggle both strategies on/off independently
  - See real-time price updates and predictions
  - Monitor win rates and performance metrics
  - View live activity feed of all trading decisions

- **Backtesting Lab Tab**:
  - Select strategy (Pattern, Random, or Both)
  - Adjust number of periods (100-2000)
  - Run backtest with progress bar
  - See beautiful results with charts and statistics

### CLI - Live Trading

```bash
# Live trading with pattern strategy (default)
python polymarket_btc_strategy.py

# Live trading with selective pattern strategy
python polymarket_btc_strategy.py --strategy selective_pattern
```

### CLI - Backtesting

```bash
# Backtest pattern strategy (default, 1000 periods)
python backtest.py

# Backtest pattern strategy with custom period count
python backtest.py --periods 500

# Backtest selective pattern strategy
python backtest.py --strategy selective_pattern --periods 1000

# Backtest with custom output file
python backtest.py --strategy pattern --output pattern_results.json

# Compare both strategies
python backtest.py --strategy pattern --output pattern_results.json
python backtest.py --strategy selective_pattern --output selective_pattern_results.json
```

## Strategy Details

### Pattern-Based Strategy

Analyzes the last 20-30 periods for statistical patterns including:
- Overall directional bias (UP/DOWN win rates)
- Recent momentum (last 5 periods)
- Streak analysis with mean reversion signals
- Mid-period behavior patterns

**Decision Making**:
- Scores patterns on multiple factors (40% win rate, 30% momentum, 30% streaks)
- Makes BUY/SELL decision at 5-minute boundaries
- Validates at 2:30 mark and may reverse position if pattern doesn't hold

### Selective Pattern Strategy

Enhanced pattern-based strategy designed for higher win rates:
- **Volatility Filtering**: Skips trades in low-volatility regimes (< $20 moves)
- **Confidence Threshold**: Only trades when signal strength meets minimum threshold (±3)
- **Momentum Acceleration**: Detects accelerating trends in recent 6 periods
- **Streak Reversion**: Applies mean reversion logic for extreme streaks (6+ periods)
- **Mid-period Confirmation**: Uses historical mid-period patterns to set expectations

The strategy analyzes last 30 periods for:
- Directional bias (UP/DOWN win rates)
- Momentum acceleration patterns
- Streak analysis with mean reversion signals
- Mid-period behavior patterns

**Decision Making**:
- Skips low-confidence setups where score < ±3
- Validates at 2:30 mark and may reverse position
- More selective than basic pattern strategy, aiming for higher win rate

## Data Sources

- **BTC Prices**: Binance API (1-minute candles)
  - Closely tracks Chainlink BTC/USD oracle used by Polymarket (~0.1% difference)
  - Used for both live trading and historical backtesting

- **Polymarket API**: Available for live market tracking (optional)

## Project Structure

```
BitcoinPolymarket/
├── strategies/                    # Strategy implementations
│   ├── base_strategy.py          # Abstract base class
│   ├── pattern_strategy.py       # Pattern-based strategy
│   └── selective_pattern_strategy.py  # Selective pattern strategy
│
├── data/                          # Data management
│   ├── price_fetcher.py          # Binance API integration
│   └── history_manager.py        # Historical data storage
│
├── trading/                       # Trading engine
│   ├── strategy_runner.py        # Multi-strategy execution
│   ├── performance_tracker.py    # Performance tracking
│   └── backtester.py             # Backtest engine
│
├── web/                           # Web dashboard
│   ├── app.py                    # Flask application
│   ├── templates/index.html      # Dashboard UI
│   └── static/                   # CSS & JavaScript
│
├── run_web.py                     # Start web dashboard
├── polymarket_btc_strategy.py     # CLI live trading
├── backtest.py                    # CLI backtesting
├── config.py                      # Configuration
└── requirements.txt               # Dependencies
```

**Generated Files (stored in `data/storage/`):**
- `btc_5min_history.json` - Historical period data (shared by all strategies)
- `btc_strategy_performance_pattern.json` - Pattern strategy performance
- `btc_strategy_performance_selective_pattern.json` - Selective pattern strategy performance
- `trade_history_pattern.json` - Pattern strategy trade history
- `trade_history_selective_pattern.json` - Selective pattern strategy trade history
- `activity_feed.json` - Persistent activity feed (last 200 items)
- `backtest_results.json` - CLI backtest results

**Note:** All data files are now stored in `data/storage/` directory for better organization. The activity feed persists across browser refreshes and can be manually cleared by deleting the JSON file.

## Command-Line Options

### polymarket_btc_strategy.py

```
--strategy {pattern,selective_pattern}   Strategy to use (default: pattern)
```

### backtest.py

```
--periods N                              Number of 5-min periods to backtest (default: 1000)
--output FILE                            Output JSON file path (default: backtest_results.json)
--strategy {pattern,selective_pattern}   Strategy to use (default: pattern)
```

## Performance Metrics

Both scripts track:
- Initial prediction accuracy (at boundary)
- Final position accuracy (after mid-period check)
- Win/loss streaks
- Position reversal impact
- Recent performance trends

## Example Output

```
═══════════════════════════════════════════════════════════════════
  🔷 BTC 5-MIN PATTERN STRATEGY - BOUNDARY DECISION  |  2024-01-15 10:30:00
═══════════════════════════════════════════════════════════════════

  Period Start  :  10:30
  BTC Price     :  $43,527.45
  History Size  :  30 periods

  Pattern Score :  +5

  Analysis:
    • Analyzed last 30 periods: 18 UP (60.0%), 12 DOWN (40.0%)
    • Strong UP bias in recent history (+4)
    • Recent momentum: 3/5 UP (+1)
    • UP periods: 66.7% had UP at 2:30 mark

──────────────────────────────────────────────────────────────────
  ✅  DECISION: BUY  (Score: +5)
──────────────────────────────────────────────────────────────────
```

## Technology Stack

### Backend
- **Python 3.x** - Core language
- **Flask** - Web framework
- **Flask-SocketIO** - Real-time WebSocket communication
- **Requests** - HTTP API calls

### Frontend
- **Bootstrap 5** - UI framework
- **Chart.js** - Data visualization
- **Socket.IO** - Real-time client updates
- **Vanilla JavaScript** - No framework overhead

### Architecture
- **Thread-safe** - Multiple strategies run concurrently
- **Event-driven** - Real-time updates via WebSockets
- **Modular** - Clean separation of concerns

## Notes

- Requires continuous internet connection for Binance API
- System time should be reasonably accurate for proper boundary synchronization
- First run will auto-backfill 30 periods of historical data
- Selective Pattern strategy may skip trades when confidence is low (score < ±3) or volatility is too low
- Web dashboard runs on `localhost:8000` by default (configurable in `config.py`)
- Both strategies can run simultaneously in the web dashboard
- CLI tools remain fully functional for headless/automated trading



Add this profit and loss logic to the backtesting too.


The current btc price that we frequenctly update is supplied by binance i think? It slighly differs from that of polymarksts. It gets its btc price from chainlink I believe. Try and get the current price as frequenclty as we do from chainlink btc price so we closely match polymarkets price. When loading the historical prices when we have no data, that is fine to load from binance like we do already. 

Also do we actually use the current btc price in our decision?
