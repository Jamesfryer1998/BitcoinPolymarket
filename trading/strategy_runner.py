"""
Strategy Runner - Thread-safe execution of trading strategies
"""
import threading
import time
from datetime import datetime, timedelta
from data.price_fetcher import get_price_fetcher
from data.history_manager import get_history_manager
from trading.performance_tracker import PerformanceTracker
from config import PERFORMANCE_FILE_PATTERN, PERFORMANCE_FILE_RANDOM


class StrategyRunner:
    """
    Manages the execution of a single trading strategy in a background thread.
    """

    def __init__(self, strategy, event_callback=None):
        """
        Initialize strategy runner.

        Args:
            strategy: Strategy instance (must implement BaseStrategy interface)
            event_callback: Optional callback function for events
                           callback(event_type, data)
        """
        self.strategy = strategy
        self.event_callback = event_callback
        self.running = False
        self.thread = None
        self.price_fetcher = get_price_fetcher()
        self.history_manager = get_history_manager()

        # Use strategy-specific performance file
        if strategy.get_name() == "pattern":
            perf_file = PERFORMANCE_FILE_PATTERN
        elif strategy.get_name() == "random":
            perf_file = PERFORMANCE_FILE_RANDOM
        else:
            perf_file = f"btc_strategy_performance_{strategy.get_name()}.json"

        self.performance_tracker = PerformanceTracker(perf_file)

        # Current period state
        self.current_position = None
        self.current_expected_mid = None
        self.period_start_price = None
        self.period_mid_price = None
        self.initial_prediction = None
        self.position_reversed = False

    def start(self):
        """Start the strategy runner in a background thread"""
        if self.running:
            return False

        # Check if we need to backfill historical data
        self._ensure_historical_data()

        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        self._emit_event("strategy_status", {
            "strategy": self.strategy.get_name(),
            "status": "started"
        })
        return True

    def _ensure_historical_data(self):
        """Ensure we have enough historical data, backfill if needed"""
        from config import MIN_PERIODS, LOOKBACK_PERIODS

        history_size = len(self.history_manager)

        if history_size < MIN_PERIODS:
            print(f"\n{self.strategy.get_name().upper()} Strategy: Insufficient history ({history_size}/{MIN_PERIODS} periods)")
            print("Auto-backfilling from Binance...")

            try:
                periods = self.price_fetcher.get_5min_periods(num_periods=LOOKBACK_PERIODS)
                if periods:
                    self.history_manager.bulk_add(periods)
                    print(f"✓ Backfilled {len(periods)} periods")

                    # Emit event
                    self._emit_event("backfill_complete", {
                        "strategy": self.strategy.get_name(),
                        "periods_added": len(periods)
                    })
                else:
                    print("✗ Failed to backfill data")
            except Exception as e:
                print(f"✗ Error during backfill: {e}")
                import traceback
                traceback.print_exc()

    def stop(self):
        """Stop the strategy runner"""
        if not self.running:
            return False

        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        self._emit_event("strategy_status", {
            "strategy": self.strategy.get_name(),
            "status": "stopped"
        })
        return True

    def is_running(self):
        """Check if strategy is currently running"""
        return self.running

    def get_status(self):
        """Get current status of the strategy"""
        return {
            "name": self.strategy.get_name(),
            "running": self.running,
            "current_position": self.current_position,
            "performance": self.performance_tracker.get_stats(),
            "predictions_count": len(self.performance_tracker)
        }

    def _run_loop(self):
        """Main strategy execution loop (runs in background thread)"""
        while self.running:
            try:
                current_boundary = self._get_current_5min_boundary()

                # Calculate time until next events
                next_boundary_seconds = self._seconds_until_next_boundary()
                mid_period_seconds = self._seconds_until_mid_period()

                # Determine next action
                if 0 < mid_period_seconds < next_boundary_seconds and self.current_position is not None:
                    # Mid-period check is next
                    print(f"[{self.strategy.get_name().upper()}] Waiting {mid_period_seconds:.0f}s for mid-period check...")
                    time.sleep(max(0, mid_period_seconds))

                    if not self.running:
                        break

                    # Mid-period check
                    self._handle_mid_period_check()

                else:
                    # Boundary decision is next
                    next_time = self._get_next_5min_boundary()
                    print(f"[{self.strategy.get_name().upper()}] Waiting {next_boundary_seconds:.0f}s until next boundary ({next_time.strftime('%H:%M:%S')})...")
                    time.sleep(max(0, next_boundary_seconds + 1))  # +1 to ensure we're past boundary

                    if not self.running:
                        break

                    # Record previous period and make new prediction
                    self._handle_boundary()

            except Exception as e:
                print(f"Error in {self.strategy.get_name()} strategy loop: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(10)

    def _handle_mid_period_check(self):
        """Handle mid-period validation and potential position reversal"""
        try:
            mid_price = self.price_fetcher.get_current_price()
            new_position, reversed, message = self.strategy.check_mid_period(
                self.period_start_price, mid_price, self.current_expected_mid, self.current_position
            )

            # Log to console
            if reversed:
                print(f"[{self.strategy.get_name().upper()}] ⚠️  Mid-period check: Position REVERSED to {new_position}")
            else:
                print(f"[{self.strategy.get_name().upper()}] ✓ Mid-period check: Position {self.current_position} confirmed")

            self._emit_event("mid_period_check", {
                "strategy": self.strategy.get_name(),
                "start_price": self.period_start_price,
                "mid_price": mid_price,
                "old_position": self.current_position,
                "new_position": new_position,
                "reversed": reversed,
                "message": message
            })

            if reversed:
                self.current_position = new_position
                self.position_reversed = True

            # Store mid price for end-of-period recording
            self.period_mid_price = mid_price

        except Exception as e:
            print(f"Error during mid-period check: {e}")

    def _handle_boundary(self):
        """Handle 5-minute boundary - record previous period and make new prediction"""
        current_boundary = self._get_current_5min_boundary()

        # Record previous period if we have the data
        if self.period_start_price is not None:
            try:
                end_price = self.price_fetcher.get_current_price()
                actual_outcome = "UP" if end_price > self.period_start_price else "DOWN"

                # If we don't have mid-price (mid-check didn't happen), use average of start and end
                mid_price = self.period_mid_price if self.period_mid_price is not None else (self.period_start_price + end_price) / 2

                print(f"[{self.strategy.get_name().upper()}] Recording period: {current_boundary.strftime('%H:%M')} - {actual_outcome} ({((end_price - self.period_start_price) / self.period_start_price * 100):+.2f}%)")

                # Add to history (and fill any gaps)
                record, gaps_filled = self.history_manager.add_period(
                    current_boundary,
                    self.period_start_price,
                    mid_price,
                    end_price
                )

                # Emit gap filled event if we filled any gaps
                if gaps_filled > 0:
                    self._emit_event("gap_filled", {
                        "strategy": self.strategy.get_name(),
                        "gaps_filled": gaps_filled
                    })

                # Emit chart refresh event
                self._emit_event("refresh_chart", {})

                # Record performance
                if self.initial_prediction is not None:
                    prediction_record = self.performance_tracker.record_prediction(
                        current_boundary,
                        self.initial_prediction,
                        self.current_position,
                        actual_outcome,
                        self.position_reversed,
                        self.period_start_price,
                        mid_price,
                        end_price
                    )

                    # Emit result event
                    self._emit_event("strategy_result", {
                        "strategy": self.strategy.get_name(),
                        "timestamp": current_boundary.isoformat(),
                        "prediction": prediction_record,
                        "stats": self.performance_tracker.get_stats(),
                        "predictions_count": len(self.performance_tracker)
                    })

            except Exception as e:
                print(f"Error recording period: {e}")

        # Reset for new period
        self.period_mid_price = None
        self.position_reversed = False

        # Get current price for new period start
        try:
            self.period_start_price = self.price_fetcher.get_current_price()
        except Exception as e:
            print(f"Error fetching start price: {e}")
            return

        # Analyze and make decision if we have enough history
        history = self.history_manager.get_history()
        if self.strategy.can_trade(len(history)):
            prediction, score, reasons, expected_mid = self.strategy.analyze(history)

            if prediction:
                # Save initial prediction for win rate tracking
                self.initial_prediction = prediction
                self.current_position = prediction
                self.current_expected_mid = expected_mid
                self.position_reversed = False

                print(f"\n[{self.strategy.get_name().upper()}] {current_boundary.strftime('%H:%M')} - Predicted {prediction} (Score: {score:+d})")

                self._emit_event("strategy_prediction", {
                    "strategy": self.strategy.get_name(),
                    "timestamp": current_boundary.isoformat(),
                    "prediction": prediction,
                    "score": score,
                    "reasons": reasons,
                    "start_price": self.period_start_price,
                    "history_size": len(history)
                })

        else:
            print(f"\n[{self.strategy.get_name().upper()}] Waiting for data: {len(history)}/{self.strategy.can_trade.__self__.__class__.__dict__.get('MIN_PERIODS', 20)} periods")
            self.current_position = None
            self.current_expected_mid = None
            self.initial_prediction = None

    def _emit_event(self, event_type, data):
        """Emit an event through the callback if provided"""
        if self.event_callback:
            try:
                self.event_callback(event_type, data)
            except Exception as e:
                print(f"Error in event callback: {e}")

    @staticmethod
    def _get_current_5min_boundary():
        """Get the start of the current 5-minute period"""
        now = datetime.now()
        minutes = (now.minute // 5) * 5
        return now.replace(minute=minutes, second=0, microsecond=0)

    @staticmethod
    def _get_next_5min_boundary():
        """Get the start of the next 5-minute period"""
        current_boundary = StrategyRunner._get_current_5min_boundary()
        return current_boundary + timedelta(minutes=5)

    @staticmethod
    def _seconds_until_next_boundary():
        """Calculate seconds until next 5-minute boundary"""
        next_boundary = StrategyRunner._get_next_5min_boundary()
        now = datetime.now()
        return (next_boundary - now).total_seconds()

    @staticmethod
    def _seconds_until_mid_period():
        """Calculate seconds until 2:30 mark of current period"""
        current_boundary = StrategyRunner._get_current_5min_boundary()
        mid_point = current_boundary + timedelta(seconds=150)  # 2.5 minutes
        now = datetime.now()
        return (mid_point - now).total_seconds()
