"""
Polymarket BTC 5-Min Pattern-Based Strategy
============================================
Strategy:
  - Tracks historical BTC price at 0:00, 2:30, and 5:00 of each 5-min period
  - Analyzes last 20+ periods for statistical patterns
  - Makes BUY/SELL decision at 5-min boundaries based on patterns
  - Validates at 2:30 mark and reverses position if pattern doesn't match

Required installs:
    pip install requests colorama

Data sources:
  - Binance API for BTC prices (closely matches Chainlink BTC/USD used by Polymarket)
  - Uses 1-minute candles for accurate start/mid/end pricing
  - Polymarket API available for live market tracking (optional)

Note: Binance prices track Chainlink oracle within ~0.1%, providing reliable
      historical data since Polymarket's 5-min markets aren't accessible via API
      after settlement.
"""

import requests
import json
import time
import os
import argparse
from datetime import datetime, timedelta
from colorama import Fore, Style, init

init(autoreset=True)

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
POLYMARKET_GAMMA_API = "https://gamma-api.polymarket.com"
POLYMARKET_CLOB_API  = "https://clob.polymarket.com"
MARKET_SLUG          = "btc-up-or-down-5m"  # Polymarket BTC 5-min market series
BINANCE_API          = "https://api.binance.com/api/v3"  # Fallback for mid-period prices
SYMBOL               = "BTCUSDT"
HISTORY_FILE         = "btc_5min_history.json"       # Stores historical period data
PERFORMANCE_FILE     = "btc_strategy_performance.json"  # Stores prediction accuracy
MIN_PERIODS          = 20        # Minimum periods needed for pattern analysis
LOOKBACK_PERIODS     = 30        # Number of periods to analyze for patterns

# ─────────────────────────────────────────────
# 1. FETCH CURRENT BTC PRICE
# ─────────────────────────────────────────────
def get_btc_price(symbol=SYMBOL):
    """
    Get current BTC price.
    Uses Binance as a proxy for Chainlink BTC/USD (close enough for live trading).
    """
    url = f"{BINANCE_API}/ticker/price"
    params = {"symbol": symbol}
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    return float(data["price"])

def get_btc_1min_candles(symbol=SYMBOL, limit=150):
    """
    Fetch 1-minute candles from Binance for mid-period approximation.
    limit=150 gives us 150 minutes = 30 5-minute periods
    """
    url = f"{BINANCE_API}/klines"
    params = {"symbol": symbol, "interval": "1m", "limit": limit}
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()

    # Parse candles: [open_time, open, high, low, close, ...]
    candles = []
    for c in data:
        candles.append({
            "open_time": int(c[0]),
            "open": float(c[1]),
            "high": float(c[2]),
            "low": float(c[3]),
            "close": float(c[4]),
        })
    return candles

def get_polymarket_events(slug=MARKET_SLUG, closed=True, limit=100):
    """
    Fetch Polymarket events by slug.
    Returns list of events, sorted by most recent first.
    """
    url = f"{POLYMARKET_GAMMA_API}/events"
    params = {
        "slug": slug,
        "closed": str(closed).lower(),
        "limit": limit,
        "_sort": "end_date_iso",  # Sort by end date
        "_order": "DESC"  # Most recent first
    }
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else []

# ─────────────────────────────────────────────
# 2. HISTORICAL DATA MANAGEMENT
# ─────────────────────────────────────────────
def load_history():
    """Load historical period data from JSON file."""
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading history: {e}")
        return []

def save_history(history):
    """Save historical period data to JSON file."""
    try:
        with open(HISTORY_FILE, 'w') as f:
            json.dump(history, f, indent=2)
    except Exception as e:
        print(f"Error saving history: {e}")

def add_period_record(history, period_start, start_price, mid_price, end_price):
    """Add a completed period to history."""
    direction = "UP" if end_price > start_price else "DOWN"
    mid_direction = "UP" if mid_price > start_price else "DOWN"

    record = {
        "timestamp": period_start.isoformat(),
        "start_price": start_price,
        "mid_price": mid_price,
        "end_price": end_price,
        "direction": direction,
        "mid_direction": mid_direction,
        "change_pct": ((end_price - start_price) / start_price) * 100,
        "mid_change_pct": ((mid_price - start_price) / start_price) * 100
    }

    history.append(record)

    # Keep only the last LOOKBACK_PERIODS * 2 records
    if len(history) > LOOKBACK_PERIODS * 2:
        history = history[-LOOKBACK_PERIODS * 2:]

    save_history(history)
    return history

def parse_polymarket_event(event):
    """
    Parse a Polymarket event to extract prices and outcome.
    Returns (timestamp, start_price, end_price, outcome) or None if can't parse.

    Note: Currently unused because Polymarket 5-min markets aren't accessible
    via API after settlement. Kept for potential future use or live tracking.
    """
    try:
        # Get timestamp from end_date_iso
        timestamp_str = event.get("end_date_iso")
        if not timestamp_str:
            return None

        # Parse timestamp - end_date_iso is when the period ENDED
        # We want the START of the period (5 minutes before end)
        from dateutil import parser as date_parser
        end_time = date_parser.parse(timestamp_str)
        start_time = end_time - timedelta(minutes=5)

        # Get markets (should be 2: Up and Down)
        markets = event.get("markets", [])
        if len(markets) < 2:
            return None

        # Find the winning outcome by looking for outcomePrices near 1.0 or 0.0
        # After settlement, winning outcome price → 1.0, losing → 0.0
        outcome = None
        for market in markets:
            outcome_name = market.get("outcome", "").upper()
            prices_raw = market.get("outcomePrices")

            if prices_raw:
                # Parse outcomePrices
                if isinstance(prices_raw, str):
                    import json as json_lib
                    prices = json_lib.loads(prices_raw)
                else:
                    prices = prices_raw

                # Check if this outcome won (price close to 1.0)
                if len(prices) > 0 and float(prices[0]) > 0.9:
                    outcome = "UP" if "UP" in outcome_name else "DOWN"
                    break

        if not outcome:
            # Can't determine outcome reliably, skip this event
            return None

        # Get start price from description (usually shows "Price to Beat: $X")
        description = event.get("description", "")
        import re
        price_match = re.search(r'\$?([\d,]+\.?\d*)', description)

        start_price = None
        if price_match:
            start_price = float(price_match.group(1).replace(',', ''))

        # If we can't get start price from description, skip this event
        if not start_price:
            return None

        # Calculate end price based on outcome
        # This is approximate since we don't have exact end price from Polymarket
        # We'll use Binance historical data to get accurate mid/end prices
        end_price = None  # We'll fill this in later

        return (start_time, start_price, end_price, outcome)

    except Exception as e:
        print(f"Error parsing event: {e}")
        return None

def backfill_from_binance(num_periods=30):
    """
    Backfill historical data from Binance 1-minute candles.

    Note: Binance prices closely track Chainlink BTC/USD (which Polymarket uses).
    Since Polymarket's 5-min markets aren't accessible via API after settlement,
    we use Binance as a reliable proxy for historical data.

    Returns populated history list.
    """
    print(f"\n{Fore.CYAN}Backfilling historical data from Binance...{Style.RESET_ALL}")
    print(f"Fetching last {num_periods * 5} minutes of 1-min candles...")
    print(f"(Note: Binance closely tracks Chainlink BTC/USD used by Polymarket)")

    try:
        # Fetch 1-min candles (5 candles per 5-min period)
        candles = get_btc_1min_candles(limit=num_periods * 5)

        if len(candles) < num_periods * 5:
            print(f"{Fore.YELLOW}Warning: Only got {len(candles)} candles, expected {num_periods * 5}{Style.RESET_ALL}")
            num_periods = len(candles) // 5

        history = []

        # Group into 5-minute periods
        for i in range(0, len(candles) - 4, 5):  # -4 to ensure we have 5 candles per group
            period_candles = candles[i:i+5]

            # Extract prices:
            # - Start: close of 1st candle (minute 0)
            # - Mid: close of 3rd candle (minute 2, closest to 2:30)
            # - End: close of 5th candle (minute 5)
            start_price = period_candles[0]["close"]
            mid_price = period_candles[2]["close"]  # Minute 2 is at 2:00-3:00, closest to 2:30
            end_price = period_candles[4]["close"]

            # Get timestamp from first candle
            period_start_ms = period_candles[0]["open_time"]
            period_start = datetime.fromtimestamp(period_start_ms / 1000)

            # Calculate directions
            direction = "UP" if end_price > start_price else "DOWN"
            mid_direction = "UP" if mid_price > start_price else "DOWN"

            record = {
                "timestamp": period_start.isoformat(),
                "start_price": start_price,
                "mid_price": mid_price,
                "end_price": end_price,
                "direction": direction,
                "mid_direction": mid_direction,
                "change_pct": ((end_price - start_price) / start_price) * 100,
                "mid_change_pct": ((mid_price - start_price) / start_price) * 100,
                "source": "binance"
            }

            history.append(record)

        # Save to file
        save_history(history)

        # Display summary
        print(f"\n{Fore.GREEN}✓ Backfill complete!{Style.RESET_ALL}")
        print(f"  Loaded {len(history)} historical 5-minute periods")

        up_count = sum(1 for r in history if r["direction"] == "UP")
        down_count = len(history) - up_count
        print(f"  Results: {up_count} UP ({up_count/len(history):.1%}), {down_count} DOWN ({down_count/len(history):.1%})")

        if history:
            print(f"  Time range: {history[0]['timestamp']} to {history[-1]['timestamp']}")

        return history

    except Exception as e:
        print(f"{Fore.RED}Error during backfill: {e}{Style.RESET_ALL}")
        import traceback
        traceback.print_exc()
        return []

# ─────────────────────────────────────────────
# 3. PERFORMANCE TRACKING
# ─────────────────────────────────────────────
def load_performance():
    """Load performance tracking data from JSON file."""
    if not os.path.exists(PERFORMANCE_FILE):
        return {"predictions": [], "stats": {}}
    try:
        with open(PERFORMANCE_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading performance data: {e}")
        return {"predictions": [], "stats": {}}

def save_performance(performance):
    """Save performance tracking data to JSON file."""
    try:
        with open(PERFORMANCE_FILE, 'w') as f:
            json.dump(performance, f, indent=2)
    except Exception as e:
        print(f"Error saving performance data: {e}")

def calculate_win_rates(predictions):
    """
    Calculate win rates from prediction history.
    Returns dict with overall and recent win rates.
    """
    if not predictions:
        return None

    total = len(predictions)
    initial_correct = sum(1 for p in predictions if p.get("initial_correct", False))
    final_correct = sum(1 for p in predictions if p.get("final_correct", False))

    stats = {
        "total_predictions": total,
        "initial_wins": initial_correct,
        "final_wins": final_correct,
        "initial_win_rate": initial_correct / total if total > 0 else 0,
        "final_win_rate": final_correct / total if total > 0 else 0
    }

    # Recent performance (last 10, 20, 50)
    for n in [10, 20, 50]:
        if total >= n:
            recent = predictions[-n:]
            initial_recent = sum(1 for p in recent if p.get("initial_correct", False))
            final_recent = sum(1 for p in recent if p.get("final_correct", False))
            stats[f"last_{n}_initial_wr"] = initial_recent / n
            stats[f"last_{n}_final_wr"] = final_recent / n

    return stats

def record_prediction(performance, timestamp, initial_prediction, final_position, actual_outcome, reversed,
                      start_price, mid_price, end_price):
    """
    Record a prediction and its outcome.
    Updates performance data with win/loss and price data.
    """
    # Convert BUY/SELL to UP/DOWN for comparison
    initial_direction = "UP" if initial_prediction == "BUY" else "DOWN"
    final_direction = "UP" if final_position == "BUY" else "DOWN"

    # Check if predictions were correct
    initial_correct = (initial_direction == actual_outcome)
    final_correct = (final_direction == actual_outcome)

    # Calculate price change
    price_change_pct = ((end_price - start_price) / start_price) * 100

    prediction_record = {
        "timestamp": timestamp.isoformat() if hasattr(timestamp, 'isoformat') else timestamp,
        "initial_prediction": initial_prediction,
        "final_position": final_position,
        "actual_outcome": actual_outcome,
        "initial_correct": initial_correct,
        "final_correct": final_correct,
        "reversed_at_midpoint": reversed,
        "start_price": start_price,
        "mid_price": mid_price,
        "end_price": end_price,
        "price_change_pct": price_change_pct
    }

    performance["predictions"].append(prediction_record)

    # Update stats
    performance["stats"] = calculate_win_rates(performance["predictions"])

    # Save to file
    save_performance(performance)

    return performance

def print_performance_summary(performance):
    """Print a summary of strategy performance."""
    stats = performance.get("stats", {})
    if not stats or stats.get("total_predictions", 0) == 0:
        print(f"\n{Fore.CYAN}No predictions recorded yet.{Style.RESET_ALL}")
        return

    total = stats["total_predictions"]
    initial_wr = stats["initial_win_rate"]
    final_wr = stats["final_win_rate"]

    print("\n" + "═"*70)
    print(f"  📊 STRATEGY PERFORMANCE SUMMARY")
    print("═"*70)
    print(f"\n  Total Predictions: {total}")
    print(f"\n  Initial Prediction (at boundary):")
    print(f"    Wins: {stats['initial_wins']}/{total}  •  Win Rate: {initial_wr:.1%}")

    print(f"\n  Final Position (after mid-period check):")
    print(f"    Wins: {stats['final_wins']}/{total}  •  Win Rate: {final_wr:.1%}")

    # Recent performance
    if total >= 10:
        print(f"\n  Recent Performance:")
        for n in [10, 20, 50]:
            if total >= n:
                initial_recent = stats.get(f"last_{n}_initial_wr", 0)
                final_recent = stats.get(f"last_{n}_final_wr", 0)
                print(f"    Last {n}: Initial {initial_recent:.1%}  •  Final {final_recent:.1%}")

    # Calculate improvement from reversals
    if total > 0:
        improvement = (stats['final_wins'] - stats['initial_wins']) / total * 100
        if improvement > 0:
            print(f"\n  🎯 Mid-period reversals improved accuracy by {improvement:.1f}%")
        elif improvement < 0:
            print(f"\n  ⚠️  Mid-period reversals reduced accuracy by {abs(improvement):.1f}%")

    print("═"*70 + "\n")

# ─────────────────────────────────────────────
# 4. TIME SYNCHRONIZATION
# ─────────────────────────────────────────────
def get_current_5min_boundary():
    """Get the start of the current 5-minute period."""
    now = datetime.now()
    minutes = (now.minute // 5) * 5
    return now.replace(minute=minutes, second=0, microsecond=0)

def get_next_5min_boundary():
    """Get the start of the next 5-minute period."""
    current_boundary = get_current_5min_boundary()
    return current_boundary + timedelta(minutes=5)

def seconds_until_next_boundary():
    """Calculate seconds until next 5-minute boundary."""
    next_boundary = get_next_5min_boundary()
    now = datetime.now()
    return (next_boundary - now).total_seconds()

def seconds_until_mid_period():
    """Calculate seconds until 2:30 mark of current period."""
    current_boundary = get_current_5min_boundary()
    mid_point = current_boundary + timedelta(seconds=150)  # 2.5 minutes
    now = datetime.now()
    return (mid_point - now).total_seconds()

# ─────────────────────────────────────────────
# 4. PATTERN ANALYSIS ENGINE
# ─────────────────────────────────────────────
def analyze_patterns(history):
    """
    Analyze last 20+ periods for patterns.
    Returns prediction and analysis details.
    """
    if len(history) < MIN_PERIODS:
        return None, None, []

    # Analyze recent history
    recent = history[-LOOKBACK_PERIODS:]

    # Calculate basic statistics
    total_periods = len(recent)
    up_count = sum(1 for p in recent if p["direction"] == "UP")
    down_count = total_periods - up_count
    up_rate = up_count / total_periods

    reasons = []
    reasons.append(f"Analyzed last {total_periods} periods: {up_count} UP ({up_rate:.1%}), {down_count} DOWN ({1-up_rate:.1%})")

    # Analyze streaks
    current_streak = 1
    for i in range(len(recent) - 1, 0, -1):
        if recent[i]["direction"] == recent[i-1]["direction"]:
            current_streak += 1
        else:
            break

    if current_streak >= 3:
        reasons.append(f"Current streak: {current_streak} consecutive {recent[-1]['direction']} periods")

    # Analyze mid-period patterns
    # For UP periods, what % had mid_direction UP?
    up_periods = [p for p in recent if p["direction"] == "UP"]
    down_periods = [p for p in recent if p["direction"] == "DOWN"]

    if up_periods:
        up_mid_up_count = sum(1 for p in up_periods if p["mid_direction"] == "UP")
        up_mid_up_rate = up_mid_up_count / len(up_periods)
        reasons.append(f"UP periods: {up_mid_up_rate:.1%} had UP at 2:30 mark")

    if down_periods:
        down_mid_down_count = sum(1 for p in down_periods if p["mid_direction"] == "DOWN")
        down_mid_down_rate = down_mid_down_count / len(down_periods)
        reasons.append(f"DOWN periods: {down_mid_down_rate:.1%} had DOWN at 2:30 mark")

    # Decision logic based on multiple factors
    score = 0

    # Factor 1: Win rate (40% weight)
    if up_rate > 0.60:
        score += 4
        reasons.append("Strong UP bias in recent history (+4)")
    elif up_rate < 0.40:
        score -= 4
        reasons.append("Strong DOWN bias in recent history (-4)")
    elif up_rate > 0.55:
        score += 2
        reasons.append("Moderate UP bias (+2)")
    elif up_rate < 0.45:
        score -= 2
        reasons.append("Moderate DOWN bias (-2)")
    else:
        reasons.append("No clear directional bias (neutral)")

    # Factor 2: Recent momentum (30% weight) - last 5 periods
    last_5 = recent[-5:]
    last_5_up = sum(1 for p in last_5 if p["direction"] == "UP")
    if last_5_up >= 4:
        score += 3
        reasons.append(f"Recent momentum: {last_5_up}/5 UP (+3)")
    elif last_5_up <= 1:
        score -= 3
        reasons.append(f"Recent momentum: {last_5_up}/5 UP, strong DOWN (-3)")
    elif last_5_up >= 3:
        score += 1
        reasons.append(f"Recent momentum: {last_5_up}/5 UP (+1)")
    elif last_5_up <= 2:
        score -= 1
        reasons.append(f"Recent momentum: {last_5_up}/5 UP (-1)")

    # Factor 3: Streak analysis (30% weight)
    if current_streak >= 5:
        # Long streak - slight mean reversion bias
        if recent[-1]["direction"] == "UP":
            score -= 2
            reasons.append("Very long UP streak - mean reversion signal (-2)")
        else:
            score += 2
            reasons.append("Very long DOWN streak - mean reversion signal (+2)")
    elif current_streak >= 3:
        # Medium streak - momentum bias
        if recent[-1]["direction"] == "UP":
            score += 1
            reasons.append("Medium UP streak - momentum signal (+1)")
        else:
            score -= 1
            reasons.append("Medium DOWN streak - momentum signal (-1)")

    # Final decision
    if score > 0:
        prediction = "BUY"
    elif score < 0:
        prediction = "SELL"
    else:
        # Tie-breaker: use recent win rate
        prediction = "BUY" if up_rate >= 0.5 else "SELL"
        reasons.append("Score tied - using win rate as tie-breaker")

    # Prepare mid-period expectations
    expected_mid_direction = None
    if prediction == "BUY" and up_periods:
        expected_mid_direction = "UP" if up_mid_up_rate > 0.6 else None
    elif prediction == "SELL" and down_periods:
        expected_mid_direction = "DOWN" if down_mid_down_rate > 0.6 else None

    return prediction, score, reasons, expected_mid_direction

def analyze_patterns_random(history):
    """
    Random strategy: Picks BUY or SELL at random.
    Returns same signature as analyze_patterns() for compatibility.
    """
    import random

    if len(history) < MIN_PERIODS:
        return None, None, []

    # Randomly pick BUY or SELL
    prediction = random.choice(["BUY", "SELL"])
    score = 0
    reasons = ["Random strategy: coin flip decision"]
    expected_mid_direction = None  # No mid-period expectations for random strategy

    return prediction, score, reasons, expected_mid_direction

# ─────────────────────────────────────────────
# 5. MID-PERIOD CHECK & POSITION REVERSAL
# ─────────────────────────────────────────────
def check_mid_period(start_price, mid_price, expected_mid_direction, current_position):
    """
    Check if mid-period behavior matches expectations.
    Returns new position and reversal flag.
    """
    actual_mid_direction = "UP" if mid_price > start_price else "DOWN"

    if expected_mid_direction is None:
        # No strong expectation, hold position
        return current_position, False, "No strong mid-period expectation - holding position"

    if actual_mid_direction == expected_mid_direction:
        # Pattern holding, keep position
        return current_position, False, f"Mid-period matches expectation ({actual_mid_direction}) - holding {current_position}"

    # Pattern not holding, reverse position
    new_position = "SELL" if current_position == "BUY" else "BUY"
    return new_position, True, f"Mid-period mismatch! Expected {expected_mid_direction}, got {actual_mid_direction} - REVERSING to {new_position}"

# ─────────────────────────────────────────────
# 6. DISPLAY OUTPUT
# ─────────────────────────────────────────────
def print_boundary_report(price, decision, score, reasons, history_count):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    boundary = get_current_5min_boundary().strftime("%H:%M")

    print("\n" + "═"*70)
    print(f"  🔷 BTC 5-MIN PATTERN STRATEGY - BOUNDARY DECISION  |  {now}")
    print("═"*70)

    print(f"\n  Period Start  :  {boundary}")
    print(f"  BTC Price     :  ${price:,.2f}")
    print(f"  History Size  :  {history_count} periods")

    print(f"\n  Pattern Score :  {score:+d}")
    print("\n  Analysis:")
    for r in reasons:
        print(f"    • {r}")

    print("\n" + "─"*70)
    if decision == "BUY":
        print(f"  {Fore.GREEN}✅  DECISION: {decision}  (Score: {score:+d}){Style.RESET_ALL}")
    else:
        print(f"  {Fore.RED}❌  DECISION: {decision}  (Score: {score:+d}){Style.RESET_ALL}")
    print("─"*70 + "\n")

def print_midpoint_report(start_price, mid_price, position, reversal_message):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    boundary = get_current_5min_boundary().strftime("%H:%M")
    change_pct = ((mid_price - start_price) / start_price) * 100

    print("\n" + "═"*70)
    print(f"  🔷 BTC 5-MIN PATTERN STRATEGY - MID-PERIOD CHECK  |  {now}")
    print("═"*70)

    print(f"\n  Period Start  :  {boundary}")
    print(f"  Start Price   :  ${start_price:,.2f}")
    print(f"  Mid Price     :  ${mid_price:,.2f}  ({change_pct:+.2f}%)")

    print(f"\n  {reversal_message}")

    print("\n" + "─"*70)
    if position == "BUY":
        print(f"  {Fore.GREEN}✅  POSITION: {position}{Style.RESET_ALL}")
    else:
        print(f"  {Fore.RED}❌  POSITION: {position}{Style.RESET_ALL}")
    print("─"*70 + "\n")

# ─────────────────────────────────────────────
# 7. MAIN LOOP
# ─────────────────────────────────────────────
def run_continuous(strategy='pattern'):
    """
    Run continuously with timing synchronized to 5-min boundaries.
    At each boundary: analyze patterns and make decision
    At 2:30 mark: check and potentially reverse position

    Args:
        strategy: 'pattern' or 'random' - which strategy to use
    """
    history = load_history()
    performance = load_performance()
    current_position = None
    current_expected_mid = None
    period_start_price = None
    initial_prediction = None  # Track initial prediction for win rate
    position_reversed = False   # Track if position was reversed

    # Select strategy function
    if strategy == 'random':
        strategy_func = analyze_patterns_random
        strategy_name = "Random (Coin Flip)"
    else:
        strategy_func = analyze_patterns
        strategy_name = "Pattern-Based"

    print(f"BTC 5-Min {strategy_name} Strategy Starting...")
    print(f"History file: {HISTORY_FILE}")
    print(f"Performance file: {PERFORMANCE_FILE}")
    print(f"Loaded {len(history)} historical periods")

    # Show performance summary if we have predictions
    if performance.get("predictions"):
        print_performance_summary(performance)

    # Check if we have enough history - if not, backfill automatically
    if len(history) < MIN_PERIODS:
        print(f"\n{Fore.YELLOW}Insufficient history: {len(history)}/{MIN_PERIODS} periods{Style.RESET_ALL}")
        print("Auto-backfilling from Binance (matches Chainlink/Polymarket prices)...")

        history = backfill_from_binance(num_periods=LOOKBACK_PERIODS)

        if len(history) >= MIN_PERIODS:
            print(f"\n{Fore.GREEN}Ready to trade!{Style.RESET_ALL}")
        else:
            print(f"\n{Fore.YELLOW}Backfill incomplete. Still need more data.{Style.RESET_ALL}")
            print("Entering data collection mode...\n")

    while True:
        try:
            current_boundary = get_current_5min_boundary()

            # Calculate time until next events
            next_boundary_seconds = seconds_until_next_boundary()
            mid_period_seconds = seconds_until_mid_period()

            # Determine next action
            if 0 < mid_period_seconds < next_boundary_seconds and current_position is not None:
                # Mid-period check is next
                print(f"Waiting {mid_period_seconds:.0f}s until 2:30 mark for mid-period check...")
                time.sleep(max(0, mid_period_seconds))

                # Mid-period check
                try:
                    mid_price = get_btc_price()
                    new_position, reversed, message = check_mid_period(
                        period_start_price, mid_price, current_expected_mid, current_position
                    )
                    print_midpoint_report(period_start_price, mid_price, new_position, message)

                    if reversed:
                        current_position = new_position
                        position_reversed = True

                    # Store mid price for end-of-period recording
                    period_mid_price = mid_price

                except Exception as e:
                    print(f"{Fore.RED}Error during mid-period check: {e}{Style.RESET_ALL}")

            else:
                # Boundary decision is next
                print(f"Waiting {next_boundary_seconds:.0f}s until next 5-min boundary ({get_next_5min_boundary().strftime('%H:%M:%S')})...")
                time.sleep(max(0, next_boundary_seconds + 1))  # +1 to ensure we're past the boundary

                # Record previous period if we have the data
                if period_start_price is not None and 'period_mid_price' in locals():
                    try:
                        end_price = get_btc_price()
                        actual_outcome = "UP" if end_price > period_start_price else "DOWN"

                        # Add to history
                        history = add_period_record(
                            history,
                            current_boundary,
                            period_start_price,
                            period_mid_price,
                            end_price
                        )

                        # Validate prediction and record performance
                        if initial_prediction is not None:
                            performance = record_prediction(
                                performance,
                                current_boundary,
                                initial_prediction,
                                current_position,
                                actual_outcome,
                                position_reversed,
                                period_start_price,
                                period_mid_price,
                                end_price
                            )

                            # Display result
                            final_correct = (("UP" if current_position == "BUY" else "DOWN") == actual_outcome)
                            result_color = Fore.GREEN if final_correct else Fore.RED
                            result_symbol = "✓" if final_correct else "✗"

                            print(f"{result_color}[{result_symbol}] Period result: {actual_outcome} - "
                                  f"Predicted: {current_position} - "
                                  f"Win Rate: {performance['stats'].get('final_win_rate', 0):.1%}{Style.RESET_ALL}")

                        print(f"Recorded period: {current_boundary.strftime('%H:%M')} - "
                              f"{actual_outcome} "
                              f"({((end_price - period_start_price) / period_start_price * 100):+.2f}%)\n")

                    except Exception as e:
                        print(f"{Fore.RED}Error recording period: {e}{Style.RESET_ALL}")

                # Reset for new period
                period_mid_price = None
                position_reversed = False

                # Get current price for new period start
                period_start_price = get_btc_price()

                # Analyze and make decision if we have enough history
                if len(history) >= MIN_PERIODS:
                    prediction, score, reasons, expected_mid = strategy_func(history)

                    if prediction:
                        # Save initial prediction for win rate tracking
                        initial_prediction = prediction
                        current_position = prediction
                        current_expected_mid = expected_mid
                        position_reversed = False  # Reset reversal flag
                        print_boundary_report(period_start_price, prediction, score, reasons, len(history))
                    else:
                        print(f"{Fore.YELLOW}Pattern analysis returned no prediction{Style.RESET_ALL}")
                        initial_prediction = None
                else:
                    print(f"\nData collection mode: {len(history)}/{MIN_PERIODS} periods")
                    print(f"Period start price: ${period_start_price:,.2f}")
                    print("Waiting for more data before making predictions...\n")
                    current_position = None
                    current_expected_mid = None
                    initial_prediction = None

        except KeyboardInterrupt:
            print("\n\nStopping strategy...")
            break
        except Exception as e:
            print(f"{Fore.RED}Error in main loop: {e}{Style.RESET_ALL}")
            import traceback
            traceback.print_exc()
            time.sleep(10)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='BTC 5-Minute Trading Strategy',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Strategy Options:
  pattern  - Pattern-based strategy analyzing historical trends (default)
  random   - Random coin flip strategy for baseline comparison

Examples:
  python polymarket_btc_strategy.py                 # Use pattern strategy
  python polymarket_btc_strategy.py --strategy random   # Use random strategy
        """
    )

    parser.add_argument(
        '--strategy',
        type=str,
        choices=['pattern', 'random'],
        default='pattern',
        help='Strategy to use: pattern (default) or random'
    )

    args = parser.parse_args()
    run_continuous(strategy=args.strategy)