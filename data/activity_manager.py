"""
Activity Feed Manager - Persistent storage for activity feed items
"""
import json
import os
import threading
from datetime import datetime
from config import ACTIVITY_FEED_FILE, MAX_ACTIVITY_ITEMS


class ActivityManager:
    """Thread-safe manager for activity feed items"""

    def __init__(self, activity_file=ACTIVITY_FEED_FILE):
        self.activity_file = activity_file
        self.items = []
        self.lock = threading.Lock()
        self.load()

    def load(self):
        """Load activity feed from file"""
        with self.lock:
            if not os.path.exists(self.activity_file):
                self.items = []
                return

            try:
                with open(self.activity_file, 'r') as f:
                    self.items = json.load(f)
            except Exception as e:
                print(f"Error loading activity feed: {e}")
                self.items = []

    def save(self):
        """Save activity feed to file"""
        with self.lock:
            try:
                with open(self.activity_file, 'w') as f:
                    json.dump(self.items, f, indent=2)
            except Exception as e:
                print(f"Error saving activity feed: {e}")

    def add_item(self, item_type, message, strategy=None):
        """
        Add an activity item.

        Args:
            item_type (str): Type of activity (info, success, warning, danger)
            message (str): Activity message
            strategy (str, optional): Strategy name if applicable

        Returns:
            dict: The activity item that was added
        """
        item = {
            "timestamp": datetime.now().isoformat(),
            "type": item_type,
            "message": message,
            "strategy": strategy
        }

        with self.lock:
            self.items.insert(0, item)  # Add to beginning

            # Keep only the last MAX_ACTIVITY_ITEMS
            if len(self.items) > MAX_ACTIVITY_ITEMS:
                self.items = self.items[:MAX_ACTIVITY_ITEMS]

        self.save()
        return item

    def get_items(self, limit=None):
        """
        Get activity items.

        Args:
            limit (int, optional): Maximum number of items to return

        Returns:
            list: List of activity items
        """
        with self.lock:
            if limit is None:
                return self.items.copy()
            else:
                return self.items[:limit].copy()

    def clear(self):
        """Clear all activity items"""
        with self.lock:
            self.items = []
        self.save()

    def __len__(self):
        """Get number of items"""
        with self.lock:
            return len(self.items)


# Singleton instance
_activity_manager = None

def get_activity_manager():
    """Get singleton ActivityManager instance"""
    global _activity_manager
    if _activity_manager is None:
        _activity_manager = ActivityManager()
    return _activity_manager
