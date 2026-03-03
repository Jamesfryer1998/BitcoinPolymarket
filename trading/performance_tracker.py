"""
Performance Tracker - Tracks and analyzes strategy performance
"""
import json
import os
import threading
from datetime import datetime


class PerformanceTracker:
    """Tracks performance metrics for a trading strategy"""

    def __init__(self, performance_file):
        self.performance_file = performance_file
        self.predictions = []
        self.stats = {}
        self.lock = threading.Lock()
        self.load()

    def load(self):
        """Load performance data from file"""
        with self.lock:
            if not os.path.exists(self.performance_file):
                self.predictions = []
                self.stats = {}
                return

            try:
                with open(self.performance_file, 'r') as f:
                    data = json.load(f)
                    self.predictions = data.get("predictions", [])
                    self.stats = data.get("stats", {})
            except Exception as e:
                print(f"Error loading performance data: {e}")
                self.predictions = []
                self.stats = {}

    def save(self):
        """Save performance data to file"""
        with self.lock:
            try:
                data = {
                    "predictions": self.predictions,
                    "stats": self.stats
                }
                with open(self.performance_file, 'w') as f:
                    json.dump(data, f, indent=2)
            except Exception as e:
                print(f"Error saving performance data: {e}")

    def record_prediction(self, timestamp, initial_prediction, final_position,
                         actual_outcome, reversed, start_price, mid_price, end_price):
        """
        Record a prediction and its outcome.

        Args:
            timestamp: Timestamp of prediction
            initial_prediction: Initial BUY/SELL prediction
            final_position: Final BUY/SELL position (after mid-period check)
            actual_outcome: Actual UP/DOWN outcome
            reversed: Whether position was reversed at midpoint
            start_price: Price at period start
            mid_price: Price at midpoint
            end_price: Price at period end

        Returns:
            dict: The prediction record
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

        with self.lock:
            self.predictions.append(prediction_record)
            self.stats = self._calculate_stats()

        self.save()
        return prediction_record

    def _calculate_stats(self):
        """Calculate performance statistics (must be called with lock held)"""
        if not self.predictions:
            return {}

        total = len(self.predictions)
        initial_wins = sum(1 for p in self.predictions if p.get("initial_correct", False))
        final_wins = sum(1 for p in self.predictions if p.get("final_correct", False))

        stats = {
            "total_predictions": total,
            "initial_wins": initial_wins,
            "final_wins": final_wins,
            "initial_win_rate": initial_wins / total if total > 0 else 0,
            "final_win_rate": final_wins / total if total > 0 else 0
        }

        # Recent performance (last 10, 20, 50)
        for n in [10, 20, 50]:
            if total >= n:
                recent = self.predictions[-n:]
                initial_recent = sum(1 for p in recent if p.get("initial_correct", False))
                final_recent = sum(1 for p in recent if p.get("final_correct", False))
                stats[f"last_{n}_initial_wr"] = initial_recent / n
                stats[f"last_{n}_final_wr"] = final_recent / n

        return stats

    def get_stats(self):
        """Get current performance statistics"""
        with self.lock:
            return self.stats.copy()

    def get_predictions(self, limit=None):
        """
        Get prediction history.

        Args:
            limit (int, optional): Maximum number of predictions to return

        Returns:
            list: List of prediction records
        """
        with self.lock:
            if limit is None:
                return self.predictions.copy()
            else:
                return self.predictions[-limit:].copy()

    def get_recent_predictions(self, count=10):
        """Get most recent N predictions"""
        return self.get_predictions(limit=count)

    def clear(self):
        """Clear all performance data"""
        with self.lock:
            self.predictions = []
            self.stats = {}
        self.save()

    def __len__(self):
        """Get number of predictions"""
        with self.lock:
            return len(self.predictions)
