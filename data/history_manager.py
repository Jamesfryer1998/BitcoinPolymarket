"""
Historical Data Manager - Thread-safe storage and retrieval of historical periods
"""
import json
import os
import threading
from datetime import datetime, timedelta
from config import HISTORY_FILE, LOOKBACK_PERIODS, HISTORY_MAX_DAYS


class HistoryManager:
    """Thread-safe manager for historical price data"""

    def __init__(self, history_file=HISTORY_FILE):
        self.history_file = history_file
        self.history = []
        self.lock = threading.Lock()
        self.load()

    def load(self):
        """Load historical data from file"""
        with self.lock:
            if not os.path.exists(self.history_file):
                self.history = []
                return

            try:
                with open(self.history_file, 'r') as f:
                    self.history = json.load(f)
            except Exception as e:
                print(f"Error loading history: {e}")
                self.history = []

    def save(self):
        """Save historical data to file"""
        with self.lock:
            try:
                with open(self.history_file, 'w') as f:
                    json.dump(self.history, f, indent=2)
            except Exception as e:
                print(f"Error saving history: {e}")

    def add_period(self, period_start, start_price, mid_price, end_price):
        """
        Add a completed period to history.

        Args:
            period_start (datetime): Start time of period
            start_price (float): Price at start
            mid_price (float): Price at midpoint (2:30)
            end_price (float): Price at end (5:00)

        Returns:
            dict: The period record that was added
        """
        direction = "UP" if end_price > start_price else "DOWN"
        mid_direction = "UP" if mid_price > start_price else "DOWN"

        record = {
            "timestamp": period_start.isoformat() if hasattr(period_start, 'isoformat') else period_start,
            "start_price": start_price,
            "mid_price": mid_price,
            "end_price": end_price,
            "direction": direction,
            "mid_direction": mid_direction,
            "change_pct": ((end_price - start_price) / start_price) * 100,
            "mid_change_pct": ((mid_price - start_price) / start_price) * 100
        }

        gaps_filled = 0
        with self.lock:
            # Check if this period already exists
            timestamp_str = record["timestamp"]
            if not any(p.get("timestamp") == timestamp_str for p in self.history):
                # Check for gaps before adding
                gaps_filled = self._check_and_fill_gaps(period_start)

                self.history.append(record)
                # Sort by timestamp to maintain chronological order
                self.history.sort(key=lambda p: p["timestamp"])

            # Clean old data
            self._clean_old_data()

        self.save()

        if gaps_filled > 0:
            print(f"[HISTORY] Filled {gaps_filled} missing periods")

        return record, gaps_filled

    def get_history(self, limit=None):
        """
        Get historical data.

        Args:
            limit (int, optional): Maximum number of records to return

        Returns:
            list: List of period records
        """
        with self.lock:
            if limit is None:
                return self.history.copy()
            else:
                return self.history[-limit:].copy()

    def get_recent(self, count=LOOKBACK_PERIODS):
        """Get most recent N periods"""
        return self.get_history(limit=count)

    def clear(self):
        """Clear all historical data"""
        with self.lock:
            self.history = []
        self.save()

    def __len__(self):
        """Get number of periods in history"""
        with self.lock:
            return len(self.history)

    def bulk_add(self, periods):
        """
        Add multiple periods at once (used for backfilling).

        Args:
            periods (list): List of period dicts
        """
        with self.lock:
            self.history.extend(periods)
            # Remove duplicates and clean old data
            self._remove_duplicates()
            self._clean_old_data()

        self.save()

    def period_exists(self, timestamp):
        """
        Check if a period with the given timestamp already exists.

        Args:
            timestamp (str or datetime): Timestamp to check

        Returns:
            bool: True if period exists
        """
        if isinstance(timestamp, datetime):
            timestamp = timestamp.isoformat()

        with self.lock:
            return any(p.get("timestamp") == timestamp for p in self.history)

    def get_latest_timestamp(self):
        """
        Get the timestamp of the most recent period.

        Returns:
            datetime or None: Most recent period timestamp
        """
        with self.lock:
            if not self.history:
                return None
            # History is stored chronologically
            latest = self.history[-1]
            return datetime.fromisoformat(latest["timestamp"])

    def _remove_duplicates(self):
        """Remove duplicate periods (same timestamp). Must be called with lock held."""
        seen = set()
        unique_history = []

        for period in self.history:
            timestamp = period.get("timestamp")
            if timestamp not in seen:
                seen.add(timestamp)
                unique_history.append(period)

        self.history = unique_history

    def _clean_old_data(self):
        """Remove periods older than HISTORY_MAX_DAYS. Must be called with lock held."""
        if not self.history:
            return

        cutoff_date = datetime.now() - timedelta(days=HISTORY_MAX_DAYS)

        # Filter out old periods
        self.history = [
            p for p in self.history
            if datetime.fromisoformat(p["timestamp"]) > cutoff_date
        ]

    def _check_and_fill_gaps(self, new_period_timestamp):
        """
        Check for gaps between latest period and new period, fill if needed.
        Must be called with lock held.

        Args:
            new_period_timestamp (datetime): Timestamp of the new period being added

        Returns:
            int: Number of periods filled
        """
        if not self.history:
            return 0

        # Get latest period
        latest = self.history[-1]
        latest_timestamp = datetime.fromisoformat(latest["timestamp"])

        # Convert new_period_timestamp to datetime if it's a string
        if isinstance(new_period_timestamp, str):
            new_period_timestamp = datetime.fromisoformat(new_period_timestamp)

        # Calculate expected time difference (5 minutes)
        expected_diff = timedelta(minutes=5)
        actual_diff = new_period_timestamp - latest_timestamp

        # If gap is more than 5 minutes, we have missing periods
        if actual_diff > expected_diff:
            # Calculate how many periods are missing
            missing_periods = int(actual_diff.total_seconds() / 300) - 1  # 300 seconds = 5 minutes

            if missing_periods > 0:
                print(f"[HISTORY] Detected gap: {missing_periods} missing periods between {latest_timestamp.strftime('%H:%M')} and {new_period_timestamp.strftime('%H:%M')}")

                try:
                    # Fetch missing periods from Binance
                    from data.price_fetcher import get_price_fetcher
                    price_fetcher = get_price_fetcher()

                    # Fetch enough periods to cover the gap plus some buffer
                    num_to_fetch = min(missing_periods + 2, 100)  # Cap at 100
                    periods = price_fetcher.get_5min_periods(num_periods=num_to_fetch)

                    if periods:
                        filled_count = 0
                        for period in periods:
                            period_timestamp = datetime.fromisoformat(period["timestamp"])

                            # Only add periods that fall within the gap
                            if latest_timestamp < period_timestamp < new_period_timestamp:
                                # Check if not already in history
                                if not any(p.get("timestamp") == period["timestamp"] for p in self.history):
                                    # Add the period record
                                    gap_record = {
                                        "timestamp": period["timestamp"],
                                        "start_price": period["start_price"],
                                        "mid_price": period["mid_price"],
                                        "end_price": period["end_price"],
                                        "direction": period["direction"],
                                        "mid_direction": period["mid_direction"],
                                        "change_pct": period["change_pct"],
                                        "mid_change_pct": period["mid_change_pct"]
                                    }
                                    self.history.append(gap_record)
                                    filled_count += 1

                        return filled_count

                except Exception as e:
                    print(f"[HISTORY] Error filling gaps: {e}")
                    import traceback
                    traceback.print_exc()

        return 0

    def clean_old_data(self):
        """Public method to clean old data (can be called externally)."""
        with self.lock:
            self._clean_old_data()
        self.save()


# Singleton instance
_history_manager = None

def get_history_manager():
    """Get singleton HistoryManager instance"""
    global _history_manager
    if _history_manager is None:
        _history_manager = HistoryManager()
    return _history_manager
