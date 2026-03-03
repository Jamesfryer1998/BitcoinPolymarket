"""
Backtester - Backtest trading strategies on historical data
"""
from datetime import datetime
from data.price_fetcher import get_price_fetcher
from config import MIN_PERIODS


class Backtester:
    """Backtests trading strategies on historical data"""

    def __init__(self, strategy):
        """
        Initialize backtester.

        Args:
            strategy: Strategy instance to backtest
        """
        self.strategy = strategy
        self.price_fetcher = get_price_fetcher()

    def prepare_historical_data(self, num_periods):
        """
        Fetch historical 1-min candles and group into 5-min periods.

        Args:
            num_periods (int): Number of 5-minute periods to fetch

        Returns:
            list: List of period dicts with start/mid/end prices and directions
        """
        periods = self.price_fetcher.get_5min_periods(num_periods=num_periods)
        return periods

    def run(self, periods, progress_callback=None):
        """
        Walk through periods chronologically and simulate trading strategy.

        Args:
            periods (list): List of historical periods
            progress_callback (callable, optional): Callback for progress updates
                                                   callback(current, total)

        Returns:
            dict: Backtest results with predictions and statistics
        """
        predictions = []

        for i in range(MIN_PERIODS, len(periods)):
            # Use only data up to current point (no look-ahead bias)
            history = periods[:i]
            current_period = periods[i]

            try:
                # Make prediction using strategy
                prediction, score, reasons, expected_mid = self.strategy.analyze(history)

                if not prediction:
                    continue

                # Store initial prediction
                initial_prediction = prediction
                initial_position = prediction

                # Simulate mid-period check
                mid_price = current_period["mid_price"]
                start_price = current_period["start_price"]

                new_position, reversed, message = self.strategy.check_mid_period(
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

                # Progress callback
                if progress_callback and (i - MIN_PERIODS + 1) % 10 == 0:
                    progress = i - MIN_PERIODS + 1
                    total = len(periods) - MIN_PERIODS
                    progress_callback(progress, total)

            except Exception as e:
                print(f"Error at period {i}: {e}")
                continue

        # Calculate statistics
        stats = self._calculate_stats(predictions)

        return {
            "strategy": self.strategy.get_name(),
            "predictions": predictions,
            "stats": stats,
            "config": {
                "total_periods": len(periods),
                "warmup_periods": MIN_PERIODS,
                "trading_periods": len(predictions),
                "backtest_date": datetime.now().isoformat(),
                "data_start": periods[0]["timestamp"] if periods else None,
                "data_end": periods[-1]["timestamp"] if periods else None
            }
        }

    def _calculate_stats(self, predictions):
        """
        Calculate comprehensive performance statistics.

        Args:
            predictions (list): List of prediction records

        Returns:
            dict: Statistics dictionary
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

        # Recent performance (last 50, 100, 200)
        for n in [50, 100, 200]:
            if total >= n:
                recent = predictions[-n:]
                recent_final_wins = sum(1 for p in recent if p["final_correct"])
                stats[f"last_{n}_win_rate"] = recent_final_wins / n

        # Best and worst trades
        if predictions:
            best_trade = max(predictions, key=lambda p: abs(p["price_change_pct"]) if p["final_correct"] else 0)
            worst_trade = min(predictions, key=lambda p: abs(p["price_change_pct"]) if not p["final_correct"] else float('inf'))

            stats["best_trade_pct"] = best_trade["price_change_pct"] if best_trade["final_correct"] else 0
            stats["worst_trade_pct"] = worst_trade["price_change_pct"] if not worst_trade["final_correct"] else 0

        return stats
