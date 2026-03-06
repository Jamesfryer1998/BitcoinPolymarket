"""
Strategy Runner - Thread-safe execution of trading strategies
"""
import threading
import time
from datetime import datetime, timedelta
from data.price_fetcher import get_price_fetcher
from data.history_manager import get_history_manager
from trading.performance_tracker import PerformanceTracker
from services.polymarket import get_polymarket_api
from services.trading_engine import TradingEngine
from services.storage import TradeStorage
from config import (PERFORMANCE_FILE_PATTERN, PERFORMANCE_FILE_SELECTIVE_PATTERN,
                   DEFAULT_BET_AMOUNT, DEFAULT_STARTING_CAPITAL)


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
        self.stop_event = threading.Event()
        self.stop_event.set()  # Initially stopped
        self.thread = None
        self.price_fetcher = get_price_fetcher()
        self.history_manager = get_history_manager()
        self.polymarket_api = get_polymarket_api()

        # Use strategy-specific performance file
        if strategy.get_name() == "pattern":
            perf_file = PERFORMANCE_FILE_PATTERN
        elif strategy.get_name() == "selective_pattern":
            perf_file = PERFORMANCE_FILE_SELECTIVE_PATTERN
        else:
            perf_file = f"btc_strategy_performance_{strategy.get_name()}.json"

        self.performance_tracker = PerformanceTracker(perf_file)

        # Trading simulation
        self.trading_engine = TradingEngine(
            strategy.get_name(),
            DEFAULT_STARTING_CAPITAL,
            DEFAULT_BET_AMOUNT
        )
        self.trade_storage = TradeStorage(strategy.get_name())

        # Current period state
        self.current_position = None
        self.current_expected_mid = None
        self.period_start_price = None
        self.period_mid_price = None
        self.initial_prediction = None
        self.position_reversed = False

        # Polymarket prices
        self.current_up_price = None
        self.current_down_price = None
        self.current_market_slug = None

        # Open trades (for linking to storage)
        self.current_trade_ids = []

    def start(self):
        """Start the strategy runner in a background thread"""
        if not self.stop_event.is_set():
            return False

        # Check if we need to backfill historical data
        self._ensure_historical_data()

        self.stop_event.clear()
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
        if self.stop_event.is_set():
            return False

        # Emit event immediately BEFORE stopping
        self._emit_event("strategy_status", {
            "strategy": self.strategy.get_name(),
            "status": "stopped"
        })

        # Signal thread to stop
        self.stop_event.set()

        # Wait for thread to finish (with timeout to prevent hanging)
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)

        return True

    def is_running(self):
        """Check if strategy is currently running"""
        return not self.stop_event.is_set()

    def get_status(self):
        """Get current status of the strategy"""
        trading_status = self.trading_engine.get_status()

        # Calculate unrealized P&L if we have prices
        unrealized_pnl = 0.0
        if self.current_up_price is not None and self.current_down_price is not None:
            unrealized_pnl = self.trading_engine.get_unrealized_pnl(
                self.current_up_price,
                self.current_down_price
            )

        return {
            "name": self.strategy.get_name(),
            "running": not self.stop_event.is_set(),
            "current_position": self.current_position,
            "performance": self.performance_tracker.get_stats(),
            "predictions_count": len(self.performance_tracker),
            "total_trades": len(self.trade_storage.get_history()),
            "up_price": self.current_up_price,
            "down_price": self.current_down_price,
            "market_slug": self.current_market_slug,
            "balance": trading_status["balance"],
            "total_profit_loss": trading_status["total_profit_loss"],
            "unrealized_pnl": unrealized_pnl,
            "open_positions": trading_status["num_open_positions"]
        }

    def _run_loop(self):
        """Main strategy execution loop (runs in background thread)"""
        while not self.stop_event.is_set():
            try:
                current_boundary = self._get_current_5min_boundary()

                # Calculate time until next events
                next_boundary_seconds = self._seconds_until_next_boundary()
                mid_period_seconds = self._seconds_until_mid_period()

                # Determine next action
                if 0 < mid_period_seconds < next_boundary_seconds and self.current_position is not None:
                    # Mid-period check is next
                    print(f"[{self.strategy.get_name().upper()}] Waiting {mid_period_seconds:.0f}s for mid-period check...")

                    # Sleep in small intervals to check stop_event frequently
                    for _ in range(int(mid_period_seconds)):
                        if self.stop_event.is_set():
                            return
                        time.sleep(1)

                    if self.stop_event.is_set():
                        return

                    # Mid-period check
                    self._handle_mid_period_check()

                else:
                    # Boundary decision is next
                    next_time = self._get_next_5min_boundary()
                    print(f"[{self.strategy.get_name().upper()}] Waiting {next_boundary_seconds:.0f}s until next boundary ({next_time.strftime('%H:%M:%S')})...")

                    # Sleep in small intervals to check stop_event frequently
                    for _ in range(int(next_boundary_seconds + 1)):
                        if self.stop_event.is_set():
                            return
                        time.sleep(1)

                    if self.stop_event.is_set():
                        return

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

            # Refresh Polymarket prices at midpoint
            try:
                current_boundary = self._get_current_5min_boundary()
                up_price, down_price, market_slug = self.polymarket_api.get_current_market_prices(current_boundary)
                self.current_up_price = up_price
                self.current_down_price = down_price
                print(f"[{self.strategy.get_name().upper()}] Mid-period prices: UP={up_price:.3f}, DOWN={down_price:.3f}")
            except Exception as e:
                print(f"Warning: Failed to fetch midpoint Polymarket prices: {e}")

            new_position, reversed, message = self.strategy.check_mid_period(
                self.period_start_price, mid_price, self.current_expected_mid, self.current_position
            )

            # Log to console
            if reversed:
                print(f"[{self.strategy.get_name().upper()}] ⚠️  Mid-period check: Position REVERSED to {new_position}")

                # Place reversal bet
                entry_price = self.current_up_price if new_position == "UP" else self.current_down_price

                try:
                    position = self.trading_engine.place_bet(
                        new_position,
                        entry_price,
                        datetime.now(),
                        is_midpoint=True
                    )

                    # Save midpoint trade to storage
                    trade = self.trade_storage.save_trade({
                        "timestamp": datetime.now().isoformat(),
                        "direction": new_position,
                        "entry_price": entry_price,
                        "bet_amount": self.trading_engine.bet_amount,
                        "is_midpoint_bet": True,
                        "potential_profit": position.potential_profit(),
                        "up_price": self.current_up_price,
                        "down_price": self.current_down_price,
                        "market_slug": self.current_market_slug
                    })

                    self.current_trade_ids.append(trade["trade_id"])

                    print(f"  Midpoint Bet: ${self.trading_engine.bet_amount:.2f} at {entry_price:.3f} - Potential: ${position.potential_profit():+.2f}")

                    # Emit midpoint bet placed event
                    self._emit_event("bet_placed", {
                        "strategy": self.strategy.get_name(),
                        "timestamp": datetime.now().isoformat(),
                        "direction": new_position,
                        "bet_amount": self.trading_engine.bet_amount,
                        "entry_price": entry_price,
                        "potential_profit": position.potential_profit(),
                        "balance": self.trading_engine.balance,
                        "up_price": self.current_up_price,
                        "down_price": self.current_down_price,
                        "is_midpoint": True
                    })

                except ValueError as e:
                    print(f"Error placing midpoint bet: {e}")

                self.current_position = new_position
                self.position_reversed = True

                # Emit full status update to sync all UI fields
                self._emit_event("strategies_update", {
                    self.strategy.get_name(): self.get_status()
                })

            else:
                print(f"[{self.strategy.get_name().upper()}] ✓ Mid-period check: Position {self.current_position} confirmed")

            self._emit_event("mid_period_check", {
                "strategy": self.strategy.get_name(),
                "start_price": self.period_start_price,
                "mid_price": mid_price,
                "old_position": self.current_position if not reversed else self.initial_prediction,
                "new_position": new_position,
                "reversed": reversed,
                "message": message,
                "up_price": self.current_up_price,
                "down_price": self.current_down_price
            })

            # Store mid price for end-of-period recording
            self.period_mid_price = mid_price

        except Exception as e:
            print(f"Error during mid-period check: {e}")
            import traceback
            traceback.print_exc()

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

                    # Close trading positions and calculate P&L
                    net_pnl, closed_positions = self.trading_engine.close_positions(
                        actual_outcome,
                        current_boundary
                    )

                    # Update trade records in storage
                    for position in closed_positions:
                        if self.current_trade_ids:
                            trade_id = self.current_trade_ids.pop(0) if len(self.current_trade_ids) > 0 else None
                            if trade_id:
                                self.trade_storage.update_trade(trade_id, {
                                    "exit_price": 1.0 if position["won"] else 0.0,
                                    "profit_loss": position["pnl"],
                                    "result": "win" if position["won"] else "loss",
                                    "close_timestamp": current_boundary.isoformat()
                                })

                    # Clear trade IDs
                    self.current_trade_ids = []

                    # Emit result event with P&L
                    self._emit_event("strategy_result", {
                        "strategy": self.strategy.get_name(),
                        "timestamp": current_boundary.isoformat(),
                        "prediction": prediction_record,
                        "stats": self.performance_tracker.get_stats(),
                        "predictions_count": len(self.performance_tracker)
                    })

                    # Emit position closed event
                    self._emit_event("position_closed", {
                        "strategy": self.strategy.get_name(),
                        "timestamp": current_boundary.isoformat(),
                        "outcome": actual_outcome,
                        "net_pnl": net_pnl,
                        "balance": self.trading_engine.balance,
                        "closed_positions": closed_positions
                    })

                    # Emit full status update to sync all UI fields
                    self._emit_event("strategies_update", {
                        self.strategy.get_name(): self.get_status()
                    })

            except Exception as e:
                print(f"Error recording period: {e}")
                import traceback
                traceback.print_exc()

        # Reset for new period
        self.period_mid_price = None
        self.position_reversed = False

        # Get current price for new period start
        try:
            self.period_start_price = self.price_fetcher.get_current_price()
        except Exception as e:
            print(f"Error fetching start price: {e}")
            return

        # Fetch Polymarket prices for this boundary
        try:
            up_price, down_price, market_slug = self.polymarket_api.get_current_market_prices(current_boundary)
            self.current_up_price = up_price
            self.current_down_price = down_price
            self.current_market_slug = market_slug
            print(f"[{self.strategy.get_name().upper()}] Polymarket prices: UP={up_price:.3f}, DOWN={down_price:.3f}")
        except Exception as e:
            print(f"Warning: Failed to fetch Polymarket prices: {e}")
            # Use fallback prices
            self.current_up_price = 0.5
            self.current_down_price = 0.5
            self.current_market_slug = None

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

                # Place bet with trading engine
                entry_price = self.current_up_price if prediction == "UP" else self.current_down_price

                try:
                    position = self.trading_engine.place_bet(
                        prediction,
                        entry_price,
                        current_boundary,
                        is_midpoint=False
                    )

                    # Save trade to storage
                    trade = self.trade_storage.save_trade({
                        "timestamp": current_boundary.isoformat(),
                        "direction": prediction,
                        "entry_price": entry_price,
                        "bet_amount": self.trading_engine.bet_amount,
                        "is_midpoint_bet": False,
                        "potential_profit": position.potential_profit(),
                        "up_price": self.current_up_price,
                        "down_price": self.current_down_price,
                        "market_slug": self.current_market_slug
                    })

                    self.current_trade_ids.append(trade["trade_id"])

                    print(f"\n[{self.strategy.get_name().upper()}] {current_boundary.strftime('%H:%M')} - Predicted {prediction} (Score: {score:+d})")
                    print(f"  Bet: ${self.trading_engine.bet_amount:.2f} at {entry_price:.3f} - Potential: ${position.potential_profit():+.2f}")

                    # Emit bet placed event
                    self._emit_event("bet_placed", {
                        "strategy": self.strategy.get_name(),
                        "timestamp": current_boundary.isoformat(),
                        "direction": prediction,
                        "bet_amount": self.trading_engine.bet_amount,
                        "entry_price": entry_price,
                        "potential_profit": position.potential_profit(),
                        "balance": self.trading_engine.balance,
                        "up_price": self.current_up_price,
                        "down_price": self.current_down_price,
                        "is_midpoint": False
                    })

                    # Emit prediction event
                    self._emit_event("strategy_prediction", {
                        "strategy": self.strategy.get_name(),
                        "timestamp": current_boundary.isoformat(),
                        "prediction": prediction,
                        "score": score,
                        "reasons": reasons,
                        "start_price": self.period_start_price,
                        "history_size": len(history),
                        "up_price": self.current_up_price,
                        "down_price": self.current_down_price
                    })

                    # Emit full status update to sync all UI fields
                    self._emit_event("strategies_update", {
                        self.strategy.get_name(): self.get_status()
                    })

                except ValueError as e:
                    print(f"Error placing bet: {e}")

            else:
                # Strategy decided not to trade - log the reasons
                print(f"\n[{self.strategy.get_name().upper()}] {current_boundary.strftime('%H:%M')} - SKIPPED TRADE (Score: {score if score is not None else 'N/A'})")

                # Log reasons for skipping
                if reasons:
                    for reason in reasons:
                        print(f"  • {reason}")

                # Create summary message for activity feed
                if reasons:
                    # Find the main reason (usually the last one or one mentioning "skipping")
                    skip_reason = next((r for r in reversed(reasons) if "skip" in r.lower()), reasons[-1] if reasons else "No confidence")
                    summary = skip_reason
                else:
                    summary = "Insufficient confidence to trade"

                # Emit skip event to activity feed
                self._emit_event("trade_skipped", {
                    "strategy": self.strategy.get_name(),
                    "timestamp": current_boundary.isoformat(),
                    "score": score if score is not None else 0,
                    "reason": summary,
                    "all_reasons": reasons
                })

                # Clear position state
                self.current_position = None
                self.current_expected_mid = None
                self.initial_prediction = None

        else:
            print(f"\n[{self.strategy.get_name().upper()}] Waiting for data: {len(history)}/{self.strategy.can_trade.__self__.__class__.__dict__.get('MIN_PERIODS', 20)} periods")

            # Emit waiting event to activity feed
            self._emit_event("strategy_waiting", {
                "strategy": self.strategy.get_name(),
                "timestamp": current_boundary.isoformat(),
                "current_periods": len(history),
                "required_periods": 20  # MIN_PERIODS
            })

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
