"""
Flask Web Application for BTC Trading Dashboard
"""
import os
import threading
import uuid
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
from flask_cors import CORS

from strategies.pattern_strategy import PatternStrategy
from strategies.random_strategy import RandomStrategy
from trading.strategy_runner import StrategyRunner
from trading.backtester import Backtester
from data.price_fetcher import get_price_fetcher
from data.history_manager import get_history_manager
from data.activity_manager import get_activity_manager
from config import FLASK_HOST, FLASK_PORT, FLASK_DEBUG, LOGS_DIR, LOG_MAX_DAYS
from utils.logger import get_logger

# Initialize logger
logger = get_logger('web')

# Initialize Flask app
app = Flask(__name__,
            template_folder='templates',
            static_folder='static')
app.config['SECRET_KEY'] = 'btc-trading-secret-key'
CORS(app)

# Initialize SocketIO
socketio = SocketIO(app, cors_allowed_origins="*")

# Global state
strategy_runners = {}
backtest_jobs = {}
backtest_lock = threading.Lock()
history_updater_running = False
history_updater_thread = None
log_cleaner_running = False
log_cleaner_thread = None


def strategy_event_callback(event_type, data):
    """Callback for strategy events - forwards to SocketIO clients and saves to activity feed"""
    socketio.emit(event_type, data)

    # Save to persistent activity feed
    activity_manager = get_activity_manager()
    strategy = data.get('strategy', 'system')

    if event_type == 'strategy_prediction':
        message = f"Predicted {data['prediction']} (Score: {data.get('score', 0):+d})"
        activity_manager.add_item('info', message, strategy)
    elif event_type == 'bet_placed':
        direction = data['direction']
        amount = data['bet_amount']
        price = data['entry_price']
        potential = data['potential_profit']
        midpoint = " (Midpoint)" if data.get('is_midpoint') else ""
        message = f"Bet placed{midpoint} - {direction} - ${amount:.2f} at {price:.3f} - Potential: ${potential:+.2f}"
        activity_manager.add_item('info', message, strategy)
    elif event_type == 'position_closed':
        outcome = data['outcome']
        pnl = data['net_pnl']
        balance = data['balance']
        message = f"Trade closed - {outcome} - P&L: ${pnl:+.2f} - Balance: ${balance:.2f}"
        activity_manager.add_item('success' if pnl > 0 else 'danger', message, strategy)
    elif event_type == 'strategy_result':
        pred = data['prediction']
        correct = pred['final_correct']
        change = pred['price_change_pct']
        message = f"{'✓' if correct else '✗'} {pred['actual_outcome']} - Predicted {pred['final_position']} ({change:+.2f}%)"
        activity_manager.add_item('success' if correct else 'danger', message, strategy)
    elif event_type == 'strategy_status':
        status = data['status']
        message = f"{'Started' if status == 'started' else 'Stopped'}"
        activity_manager.add_item('info', message, strategy)
    elif event_type == 'mid_period_check':
        if data.get('reversed'):
            message = f"Mid-check: Position REVERSED to {data['new_position']}"
            activity_manager.add_item('warning', message, strategy)
        else:
            message = f"Mid-check: Position {data['old_position']} confirmed"
            activity_manager.add_item('info', message, strategy)
    elif event_type == 'backfill_complete':
        periods = data.get('periods_added', 0)
        message = f"Backfilled {periods} historical periods from Binance"
        activity_manager.add_item('info', message, strategy)

        # Emit event to refresh chart
        socketio.emit('refresh_chart', {})
    elif event_type == 'gap_filled':
        # Just refresh chart, don't add to activity feed
        socketio.emit('refresh_chart', {})


def history_updater():
    """Background thread that continuously updates historical data"""
    global history_updater_running
    import time
    from datetime import datetime, timedelta

    print("History updater thread started")
    last_checked_boundary = None

    while history_updater_running:
        try:
            # Calculate current 5-minute boundary
            now = datetime.now()
            current_minute = (now.minute // 5) * 5
            current_boundary = now.replace(minute=current_minute, second=0, microsecond=0)

            # Check if we're past the boundary (period is complete)
            if now.second >= 30:  # Wait 30 seconds after boundary to ensure data is available
                # Get the boundary that just completed
                completed_boundary = current_boundary

                # Check if we've already processed this boundary
                if last_checked_boundary != completed_boundary:
                    last_checked_boundary = completed_boundary

                    history_manager = get_history_manager()
                    price_fetcher = get_price_fetcher()
                    activity_manager = get_activity_manager()

                    # Check if this period already exists
                    if not history_manager.period_exists(completed_boundary):
                        # Fetch the most recent completed period
                        periods = price_fetcher.get_5min_periods(num_periods=1)

                        if periods and len(periods) > 0:
                            latest_period = periods[-1]
                            period_timestamp = datetime.fromisoformat(latest_period["timestamp"])

                            # Make sure this is the period we want
                            if period_timestamp == completed_boundary:
                                # Add to history (and fill any gaps)
                                record, gaps_filled = history_manager.add_period(
                                    period_timestamp,
                                    latest_period["start_price"],
                                    latest_period["mid_price"],
                                    latest_period["end_price"]
                                )

                                print(f"[HISTORY] Added period: {period_timestamp.strftime('%Y-%m-%d %H:%M')} - {latest_period['direction']}")

                                # Add activity item
                                activity_manager.add_item(
                                    'info',
                                    f"Period {period_timestamp.strftime('%H:%M')} recorded: {latest_period['direction']} ({latest_period['change_pct']:+.2f}%)",
                                    'system'
                                )

                                # If gaps were filled, add activity item
                                if gaps_filled > 0:
                                    activity_manager.add_item(
                                        'info',
                                        f"Filled {gaps_filled} missing periods",
                                        'system'
                                    )
                                    socketio.emit('gap_filled', {'gaps_filled': gaps_filled})

                                # Emit event to refresh chart
                                socketio.emit('refresh_chart', {})

                    # Clean old data periodically
                    history_manager.clean_old_data()

            # Sleep for 30 seconds before checking again
            time.sleep(30)

        except Exception as e:
            print(f"Error in history updater: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(60)  # Wait longer on error

    print("History updater thread stopped")


def start_history_updater():
    """Start the history updater background thread"""
    global history_updater_running, history_updater_thread

    if not history_updater_running:
        history_updater_running = True
        history_updater_thread = threading.Thread(target=history_updater, daemon=True)
        history_updater_thread.start()
        print("History updater started")


def stop_history_updater():
    """Stop the history updater background thread"""
    global history_updater_running

    if history_updater_running:
        history_updater_running = False
        logger.info("History updater stopping...")


def log_cleaner():
    """Background thread that cleans up old log files"""
    global log_cleaner_running
    import time
    from datetime import datetime, timedelta

    logger.info("Log cleaner thread started")

    while log_cleaner_running:
        try:
            # Run cleanup once per day
            cutoff_date = datetime.now() - timedelta(days=LOG_MAX_DAYS)

            # Get all log files
            if os.path.exists(LOGS_DIR):
                deleted_count = 0
                for filename in os.listdir(LOGS_DIR):
                    if filename.startswith("all-") and filename.endswith(".log"):
                        filepath = os.path.join(LOGS_DIR, filename)

                        # Get file modification time
                        file_mtime = datetime.fromtimestamp(os.path.getmtime(filepath))

                        # Delete if older than cutoff
                        if file_mtime < cutoff_date:
                            try:
                                os.remove(filepath)
                                deleted_count += 1
                                logger.info(f"Deleted old log file: {filename}")
                            except Exception as e:
                                logger.error(f"Error deleting log file {filename}: {e}")

                if deleted_count > 0:
                    logger.info(f"Cleaned up {deleted_count} old log files")

            # Sleep for 24 hours (86400 seconds)
            time.sleep(86400)

        except Exception as e:
            logger.error(f"Error in log cleaner: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(3600)  # Wait 1 hour on error

    logger.info("Log cleaner thread stopped")


def start_log_cleaner():
    """Start the log cleaner background thread"""
    global log_cleaner_running, log_cleaner_thread

    if not log_cleaner_running:
        log_cleaner_running = True
        log_cleaner_thread = threading.Thread(target=log_cleaner, daemon=True)
        log_cleaner_thread.start()
        logger.info("Log cleaner started")


def stop_log_cleaner():
    """Stop the log cleaner background thread"""
    global log_cleaner_running

    if log_cleaner_running:
        log_cleaner_running = False
        logger.info("Log cleaner stopping...")


def initialize_strategies():
    """Initialize strategy runners"""
    global strategy_runners

    pattern_strategy = PatternStrategy()
    random_strategy = RandomStrategy()

    strategy_runners['pattern'] = StrategyRunner(pattern_strategy, strategy_event_callback)
    strategy_runners['random'] = StrategyRunner(random_strategy, strategy_event_callback)

    # Start background threads
    start_history_updater()
    start_log_cleaner()


# ─────────────────────────────────────────────
# WEB ROUTES
# ─────────────────────────────────────────────

@app.route('/')
def index():
    """Serve the main dashboard page"""
    return render_template('index.html')


@app.route('/api/current_price')
def get_current_price():
    """Get current BTC price"""
    try:
        price_fetcher = get_price_fetcher()
        price = price_fetcher.get_current_price()
        return jsonify({
            "price": price,
            "timestamp": "now"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/history')
def get_history():
    """Get historical price data"""
    try:
        limit = request.args.get('limit', type=int, default=100)
        history_manager = get_history_manager()
        history = history_manager.get_history(limit=limit)
        return jsonify({
            "history": history,
            "count": len(history)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/strategies')
def get_strategies():
    """Get status of all strategies"""
    try:
        strategies_status = {}
        for name, runner in strategy_runners.items():
            strategies_status[name] = runner.get_status()
        return jsonify(strategies_status)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/activity')
def get_activity():
    """Get activity feed items"""
    try:
        limit = request.args.get('limit', type=int, default=50)
        activity_manager = get_activity_manager()
        items = activity_manager.get_items(limit=limit)
        return jsonify({
            "items": items,
            "count": len(items)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/trades/<strategy_name>')
def get_trades(strategy_name):
    """Get trade history for a strategy"""
    try:
        if strategy_name not in strategy_runners:
            return jsonify({"error": "Strategy not found"}), 404

        runner = strategy_runners[strategy_name]
        trades = runner.trade_storage.get_history()

        return jsonify({
            "strategy": strategy_name,
            "trades": trades,
            "count": len(trades)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/strategy/<strategy_name>/start', methods=['POST'])
def start_strategy(strategy_name):
    """Start a strategy"""
    try:
        if strategy_name not in strategy_runners:
            return jsonify({"error": "Strategy not found"}), 404

        runner = strategy_runners[strategy_name]
        if runner.start():
            return jsonify({
                "status": "started",
                "strategy": strategy_name
            })
        else:
            return jsonify({
                "status": "already_running",
                "strategy": strategy_name
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/strategy/<strategy_name>/stop', methods=['POST'])
def stop_strategy(strategy_name):
    """Stop a strategy"""
    try:
        if strategy_name not in strategy_runners:
            return jsonify({"error": "Strategy not found"}), 404

        runner = strategy_runners[strategy_name]
        if runner.stop():
            return jsonify({
                "status": "stopped",
                "strategy": strategy_name
            })
        else:
            return jsonify({
                "status": "not_running",
                "strategy": strategy_name
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/trading/config', methods=['POST'])
def update_trading_config():
    """Update trading configuration (bet amount, starting capital)"""
    try:
        data = request.get_json()
        bet_amount = data.get('bet_amount')
        starting_capital = data.get('starting_capital')

        if bet_amount is not None:
            bet_amount = float(bet_amount)
            if bet_amount < 1:
                return jsonify({"error": "Bet amount must be at least $1"}), 400

        if starting_capital is not None:
            starting_capital = float(starting_capital)
            if starting_capital < 100:
                return jsonify({"error": "Starting capital must be at least $100"}), 400

        # Update all strategy runners
        for name, runner in strategy_runners.items():
            if bet_amount is not None:
                runner.trading_engine.bet_amount = bet_amount
            if starting_capital is not None:
                runner.trading_engine.starting_capital = starting_capital

        return jsonify({
            "status": "success",
            "bet_amount": bet_amount,
            "starting_capital": starting_capital,
            "message": "Configuration updated for all strategies"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/trading/reset', methods=['POST'])
def reset_trading():
    """Reset all trading engines (balances, P/L, trade history)"""
    try:
        # Reset all strategy runners
        for name, runner in strategy_runners.items():
            # Reset trading engine
            runner.trading_engine.reset()

            # Clear trade storage
            runner.trade_storage.clear_history()

            # Clear current trade IDs
            runner.current_trade_ids = []

        # Emit update to refresh UI
        strategies_status = {}
        for name, runner in strategy_runners.items():
            strategies_status[name] = runner.get_status()

        socketio.emit('strategies_update', strategies_status)

        return jsonify({
            "status": "success",
            "message": "All balances and P/L reset to starting values"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/backtest/run', methods=['POST'])
def run_backtest():
    """Run a backtest"""
    try:
        data = request.get_json()
        strategy_name = data.get('strategy', 'pattern')
        periods = data.get('periods', 1000)

        # Validate inputs
        if strategy_name not in ['pattern', 'random', 'both']:
            return jsonify({"error": "Invalid strategy"}), 400

        if not isinstance(periods, int) or periods < 100 or periods > 2000:
            return jsonify({"error": "Periods must be between 100 and 2000"}), 400

        # Generate job ID
        job_id = str(uuid.uuid4())

        # Store job info
        with backtest_lock:
            backtest_jobs[job_id] = {
                "status": "running",
                "strategy": strategy_name,
                "periods": periods,
                "progress": 0,
                "results": None
            }

        # Run backtest in background thread
        thread = threading.Thread(
            target=_run_backtest_job,
            args=(job_id, strategy_name, periods),
            daemon=True
        )
        thread.start()

        return jsonify({
            "job_id": job_id,
            "status": "started"
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _run_backtest_job(job_id, strategy_name, periods):
    """Run backtest in background thread"""
    try:
        if strategy_name == 'both':
            # Run both strategies
            pattern_results = _run_single_backtest('pattern', periods, job_id)
            random_results = _run_single_backtest('random', periods, job_id)

            results = {
                "pattern": pattern_results,
                "random": random_results,
                "comparison": _compare_backtest_results(pattern_results, random_results)
            }
        else:
            results = _run_single_backtest(strategy_name, periods, job_id)

        # Update job status
        with backtest_lock:
            if job_id in backtest_jobs:
                backtest_jobs[job_id]["status"] = "completed"
                backtest_jobs[job_id]["results"] = results
                backtest_jobs[job_id]["progress"] = 100

        # Emit completion event
        socketio.emit('backtest_complete', {
            "job_id": job_id,
            "results": results
        })

    except Exception as e:
        print(f"Error in backtest job {job_id}: {e}")
        with backtest_lock:
            if job_id in backtest_jobs:
                backtest_jobs[job_id]["status"] = "error"
                backtest_jobs[job_id]["error"] = str(e)


def _run_single_backtest(strategy_name, periods, job_id):
    """Run backtest for a single strategy"""
    # Create strategy
    if strategy_name == 'pattern':
        strategy = PatternStrategy()
    elif strategy_name == 'random':
        strategy = RandomStrategy()
    else:
        raise ValueError(f"Unknown strategy: {strategy_name}")

    # Create backtester
    backtester = Backtester(strategy)

    # Prepare data
    historical_periods = backtester.prepare_historical_data(periods)

    # Progress callback
    def progress_callback(current, total):
        progress = int((current / total) * 100)
        with backtest_lock:
            if job_id in backtest_jobs:
                backtest_jobs[job_id]["progress"] = progress
        socketio.emit('backtest_progress', {
            "job_id": job_id,
            "progress": progress
        })

    # Run backtest
    results = backtester.run(historical_periods, progress_callback=progress_callback)

    return results


def _compare_backtest_results(pattern_results, random_results):
    """Compare results from two strategies"""
    pattern_stats = pattern_results.get('stats', {})
    random_stats = random_results.get('stats', {})

    pattern_wr = pattern_stats.get('final_win_rate', 0)
    random_wr = random_stats.get('final_win_rate', 0)

    return {
        "pattern_win_rate": pattern_wr,
        "random_win_rate": random_wr,
        "difference": pattern_wr - random_wr,
        "pattern_better": pattern_wr > random_wr,
        "improvement_pct": ((pattern_wr - random_wr) / random_wr * 100) if random_wr > 0 else 0
    }


@app.route('/api/backtest/status/<job_id>')
def get_backtest_status(job_id):
    """Get backtest job status"""
    try:
        with backtest_lock:
            if job_id not in backtest_jobs:
                return jsonify({"error": "Job not found"}), 404

            job = backtest_jobs[job_id].copy()

        # Don't include full results in status check (too large)
        if job.get("results"):
            job["has_results"] = True
            job.pop("results", None)

        return jsonify(job)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/backtest/results/<job_id>')
def get_backtest_results(job_id):
    """Get backtest results"""
    try:
        with backtest_lock:
            if job_id not in backtest_jobs:
                return jsonify({"error": "Job not found"}), 404

            job = backtest_jobs[job_id]

            if job["status"] != "completed":
                return jsonify({"error": "Backtest not completed"}), 400

            return jsonify(job["results"])

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────
# SOCKETIO EVENTS
# ─────────────────────────────────────────────

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    print("Client connected")
    emit('connected', {"status": "connected"})


@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    print("Client disconnected")


@socketio.on('request_update')
def handle_request_update():
    """Handle client request for full update"""
    try:
        # Send current price
        price_fetcher = get_price_fetcher()
        price = price_fetcher.get_current_price()
        emit('price_update', {"price": price})

        # Send strategies status
        strategies_status = {}
        for name, runner in strategy_runners.items():
            strategies_status[name] = runner.get_status()
        emit('strategies_update', strategies_status)

    except Exception as e:
        print(f"Error in request_update: {e}")


def create_app():
    """Factory function to create and configure the app"""
    initialize_strategies()
    return app, socketio


if __name__ == '__main__':
    app, socketio = create_app()
    socketio.run(app, host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG)
