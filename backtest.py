"""
BTC 5-Min Pattern Strategy Backtester
======================================
Backtests the pattern-based trading strategy on historical data.

Features:
  - Chronological walk-through (no look-ahead bias)
  - Simulates mid-period checks and reversals
  - Comprehensive performance metrics
  - Configurable test period

Usage:
    python backtest.py                          # Default: 1000 periods
    python backtest.py --periods 500            # Custom period count
    python backtest.py --output results.json    # Custom output file
"""

import requests
import json
import argparse
from datetime import datetime, timedelta
from colorama import Fore, Style, init

# Import strategy functions
from polymarket_btc_strategy import (
    get_btc_1min_candles,
    analyze_patterns,
    analyze_patterns_random,
    check_mid_period,
    calculate_win_rates
)

init(autoreset=True)

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
DEFAULT_PERIODS = 1000       # Default number of periods to backtest
MIN_PERIODS = 20             # Warmup periods before making predictions
OUTPUT_FILE = "backtest_results.json"

# ─────────────────────────────────────────────
# 1. HISTORICAL DATA PREPARATION
# ─────────────────────────────────────────────
def prepare_historical_data(num_periods):
    """
    Fetch historical 1-min candles and group into 5-min periods.
    Returns list of periods with start/mid/end prices.
    """
    print(f"\n{Fore.CYAN}Fetching historical data for backtest...{Style.RESET_ALL}")
    print(f"Requesting {num_periods * 5} 1-minute candles from Binance...")

    try:
        candles = get_btc_1min_candles(limit=num_periods * 5)

        if len(candles) < num_periods * 5:
            print(f"{Fore.YELLOW}Warning: Only got {len(candles)} candles{Style.RESET_ALL}")
            num_periods = len(candles) // 5

        print(f"Grouping into {num_periods} 5-minute periods...")

        periods = []
        for i in range(0, len(candles) - 4, 5):
            period_candles = candles[i:i+5]

            # Extract prices
            start_price = period_candles[0]["close"]
            mid_price = period_candles[2]["close"]  # At ~2:30
            end_price = period_candles[4]["close"]

            # Calculate outcome
            direction = "UP" if end_price > start_price else "DOWN"
            mid_direction = "UP" if mid_price > start_price else "DOWN"

            # Get timestamp
            period_start_ms = period_candles[0]["open_time"]
            period_start = datetime.fromtimestamp(period_start_ms / 1000)

            period = {
                "timestamp": period_start.isoformat(),
                "start_price": start_price,
                "mid_price": mid_price,
                "end_price": end_price,
                "direction": direction,
                "mid_direction": mid_direction,
                "change_pct": ((end_price - start_price) / start_price) * 100,
                "mid_change_pct": ((mid_price - start_price) / start_price) * 100
            }

            periods.append(period)

        print(f"{Fore.GREEN}✓ Prepared {len(periods)} historical periods{Style.RESET_ALL}")

        # Display time range
        if periods:
            print(f"  Time range: {periods[0]['timestamp']} to {periods[-1]['timestamp']}")
            up_count = sum(1 for p in periods if p["direction"] == "UP")
            print(f"  Historical distribution: {up_count} UP ({up_count/len(periods):.1%}), "
                  f"{len(periods)-up_count} DOWN ({(len(periods)-up_count)/len(periods):.1%})")

        return periods

    except Exception as e:
        print(f"{Fore.RED}Error fetching data: {e}{Style.RESET_ALL}")
        import traceback
        traceback.print_exc()
        return []

# ─────────────────────────────────────────────
# 2. BACKTEST ENGINE
# ─────────────────────────────────────────────
def run_backtest(periods, strategy='pattern'):
    """
    Walk through periods chronologically and simulate trading strategy.
    Returns list of predictions with outcomes.

    Args:
        periods: List of historical periods
        strategy: 'pattern' or 'random' - which strategy to use
    """
    # Select strategy function
    if strategy == 'random':
        strategy_func = analyze_patterns_random
        strategy_name = "Random (Coin Flip)"
    else:
        strategy_func = analyze_patterns
        strategy_name = "Pattern-Based"

    print(f"\n{Fore.CYAN}Running backtest with {strategy_name} strategy...{Style.RESET_ALL}")
    print(f"Warmup phase: First {MIN_PERIODS} periods")
    print(f"Trading phase: {len(periods) - MIN_PERIODS} periods\n")

    predictions = []

    for i in range(MIN_PERIODS, len(periods)):
        # Use only data up to current point (no look-ahead bias)
        history = periods[:i]
        current_period = periods[i]

        try:
            # Make prediction using selected strategy
            prediction, score, reasons, expected_mid = strategy_func(history)

            if not prediction:
                continue

            # Store initial prediction
            initial_prediction = prediction
            initial_position = prediction

            # Simulate mid-period check
            mid_price = current_period["mid_price"]
            start_price = current_period["start_price"]

            new_position, reversed, message = check_mid_period(
                start_price, mid_price, expected_mid, initial_position
            )

            final_position = new_position if reversed else initial_position

            # Get actual outcome
            actual_outcome = current_period["direction"]

            # Check if predictions were correct
            initial_direction = "UP" if initial_prediction == "BUY" else "DOWN"
            final_direction = "UP" if final_position == "BUY" else "DOWN"

            initial_correct = (initial_direction == actual_outcome)
            final_correct = (final_direction == actual_outcome)

            # Record prediction
            prediction_record = {
                "timestamp": current_period["timestamp"],
                "initial_prediction": initial_prediction,
                "final_position": final_position,
                "actual_outcome": actual_outcome,
                "initial_correct": initial_correct,
                "final_correct": final_correct,
                "reversed_at_midpoint": reversed,
                "start_price": current_period["start_price"],
                "mid_price": current_period["mid_price"],
                "end_price": current_period["end_price"],
                "price_change_pct": current_period["change_pct"],
                "score": score
            }

            predictions.append(prediction_record)

            # Progress indicator
            if (i - MIN_PERIODS + 1) % 100 == 0:
                progress = (i - MIN_PERIODS + 1)
                total = len(periods) - MIN_PERIODS
                print(f"Progress: {progress}/{total} periods ({progress/total:.1%})")

        except Exception as e:
            print(f"Error at period {i}: {e}")
            continue

    print(f"\n{Fore.GREEN}✓ Backtest complete!{Style.RESET_ALL}")
    print(f"  Processed {len(predictions)} predictions")

    return predictions

# ─────────────────────────────────────────────
# 3. PERFORMANCE STATISTICS
# ─────────────────────────────────────────────
def calculate_backtest_stats(predictions):
    """
    Calculate comprehensive performance statistics.
    """
    if not predictions:
        return {}

    total = len(predictions)
    initial_wins = sum(1 for p in predictions if p["initial_correct"])
    final_wins = sum(1 for p in predictions if p["final_correct"])
    reversals = sum(1 for p in predictions if p["reversed_at_midpoint"])

    # Base stats
    stats = {
        "total_predictions": total,
        "initial_wins": initial_wins,
        "final_wins": final_wins,
        "initial_win_rate": initial_wins / total,
        "final_win_rate": final_wins / total,
        "reversals_count": reversals,
        "reversal_improvement_pct": ((final_wins - initial_wins) / total) * 100
    }

    # Win/loss streaks
    current_streak = 0
    max_win_streak = 0
    max_loss_streak = 0

    for p in predictions:
        if p["final_correct"]:
            if current_streak >= 0:
                current_streak += 1
            else:
                current_streak = 1
            max_win_streak = max(max_win_streak, current_streak)
        else:
            if current_streak <= 0:
                current_streak -= 1
            else:
                current_streak = -1
            max_loss_streak = max(max_loss_streak, abs(current_streak))

    stats["longest_win_streak"] = max_win_streak
    stats["longest_loss_streak"] = max_loss_streak

    # Average price changes
    wins = [p for p in predictions if p["final_correct"]]
    losses = [p for p in predictions if not p["final_correct"]]

    if wins:
        stats["avg_win_price_change"] = sum(abs(p["price_change_pct"]) for p in wins) / len(wins)
    if losses:
        stats["avg_loss_price_change"] = sum(abs(p["price_change_pct"]) for p in losses) / len(losses)

    # Recent performance (last 50, 100)
    for n in [50, 100, 200]:
        if total >= n:
            recent = predictions[-n:]
            recent_final_wins = sum(1 for p in recent if p["final_correct"])
            stats[f"last_{n}_win_rate"] = recent_final_wins / n

    return stats

def print_backtest_summary(stats):
    """
    Print comprehensive backtest summary.
    """
    print("\n" + "═"*70)
    print(f"  📊 BACKTEST RESULTS SUMMARY")
    print("═"*70)

    print(f"\n  Total Predictions: {stats['total_predictions']}")

    print(f"\n  Initial Predictions (at boundary):")
    print(f"    Wins: {stats['initial_wins']}/{stats['total_predictions']}")
    print(f"    Win Rate: {stats['initial_win_rate']:.2%}")

    print(f"\n  Final Positions (after mid-period check):")
    print(f"    Wins: {stats['final_wins']}/{stats['total_predictions']}")
    print(f"    Win Rate: {stats['final_win_rate']:.2%}")

    print(f"\n  Mid-Period Reversals:")
    print(f"    Count: {stats['reversals_count']}")
    improvement = stats['reversal_improvement_pct']
    if improvement > 0:
        print(f"    Impact: {Fore.GREEN}+{improvement:.2f}% improvement{Style.RESET_ALL}")
    elif improvement < 0:
        print(f"    Impact: {Fore.RED}{improvement:.2f}% worse{Style.RESET_ALL}")
    else:
        print(f"    Impact: No change")

    print(f"\n  Streaks:")
    print(f"    Longest Win Streak: {stats['longest_win_streak']}")
    print(f"    Longest Loss Streak: {stats['longest_loss_streak']}")

    if 'avg_win_price_change' in stats:
        print(f"\n  Average Price Movement:")
        print(f"    On Wins: {stats['avg_win_price_change']:.3f}%")
    if 'avg_loss_price_change' in stats:
        print(f"    On Losses: {stats['avg_loss_price_change']:.3f}%")

    if 'last_50_win_rate' in stats:
        print(f"\n  Recent Performance:")
        if 'last_50_win_rate' in stats:
            print(f"    Last 50: {stats['last_50_win_rate']:.2%}")
        if 'last_100_win_rate' in stats:
            print(f"    Last 100: {stats['last_100_win_rate']:.2%}")
        if 'last_200_win_rate' in stats:
            print(f"    Last 200: {stats['last_200_win_rate']:.2%}")

    print("═"*70 + "\n")

# ─────────────────────────────────────────────
# 4. SAVE RESULTS
# ─────────────────────────────────────────────
def save_backtest_results(periods, predictions, stats, output_file):
    """
    Save backtest results to JSON file.
    """
    results = {
        "config": {
            "total_periods": len(periods),
            "warmup_periods": MIN_PERIODS,
            "trading_periods": len(predictions),
            "backtest_date": datetime.now().isoformat(),
            "data_start": periods[0]["timestamp"] if periods else None,
            "data_end": periods[-1]["timestamp"] if periods else None
        },
        "predictions": predictions,
        "stats": stats
    }

    try:
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"{Fore.GREEN}✓ Results saved to {output_file}{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}Error saving results: {e}{Style.RESET_ALL}")

# ─────────────────────────────────────────────
# 5. MAIN EXECUTION
# ─────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description='Backtest BTC 5-Min Pattern Strategy',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python backtest.py                          # Default: 1000 periods
  python backtest.py --periods 500            # Test 500 periods
  python backtest.py --output custom.json     # Custom output file
        """
    )

    parser.add_argument(
        '--periods',
        type=int,
        default=DEFAULT_PERIODS,
        help=f'Number of 5-min periods to backtest (default: {DEFAULT_PERIODS})'
    )

    parser.add_argument(
        '--output',
        type=str,
        default=OUTPUT_FILE,
        help=f'Output JSON file path (default: {OUTPUT_FILE})'
    )

    parser.add_argument(
        '--strategy',
        type=str,
        choices=['pattern', 'random'],
        default='pattern',
        help='Strategy to use: pattern (default) or random'
    )

    args = parser.parse_args()

    print("═"*70)
    print(f"  🔷 BTC 5-MIN STRATEGY BACKTEST")
    print("═"*70)
    print(f"\n  Configuration:")
    print(f"    Strategy: {args.strategy}")
    print(f"    Periods to test: {args.periods}")
    print(f"    Warmup periods: {MIN_PERIODS}")
    print(f"    Output file: {args.output}")

    # Step 1: Prepare historical data
    periods = prepare_historical_data(args.periods)

    if not periods or len(periods) < MIN_PERIODS:
        print(f"\n{Fore.RED}Error: Need at least {MIN_PERIODS} periods for backtest{Style.RESET_ALL}")
        return

    # Step 2: Run backtest
    predictions = run_backtest(periods, strategy=args.strategy)

    if not predictions:
        print(f"\n{Fore.RED}Error: No predictions generated{Style.RESET_ALL}")
        return

    # Step 3: Calculate statistics
    stats = calculate_backtest_stats(predictions)

    # Step 4: Display results
    print_backtest_summary(stats)

    # Step 5: Save results
    save_backtest_results(periods, predictions, stats, args.output)

    print(f"\n{Fore.GREEN}Backtest complete!{Style.RESET_ALL}\n")


if __name__ == "__main__":
    main()
