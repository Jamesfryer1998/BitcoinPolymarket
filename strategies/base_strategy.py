"""
Base Strategy - Abstract base class for all trading strategies
"""
from abc import ABC, abstractmethod
from config import MIN_PERIODS


class BaseStrategy(ABC):
    """Abstract base class for trading strategies"""

    def __init__(self, name):
        """
        Initialize strategy.

        Args:
            name (str): Strategy name (e.g., "pattern", "random")
        """
        self.name = name

    @abstractmethod
    def analyze(self, history):
        """
        Analyze historical data and make a prediction.

        Args:
            history (list): List of historical period dicts

        Returns:
            tuple: (prediction, score, reasons, expected_mid_direction)
                - prediction (str): "UP" or "DOWN"
                - score (int): Confidence score
                - reasons (list): List of reason strings
                - expected_mid_direction (str or None): Expected mid-period direction
        """
        pass

    def check_mid_period(self, start_price, mid_price, expected_mid_direction, current_position):
        """
        Check if mid-period behavior matches expectations.
        Can be overridden by subclasses for custom logic.

        Args:
            start_price (float): Price at period start
            mid_price (float): Price at mid-period (2:30)
            expected_mid_direction (str or None): Expected direction
            current_position (str): Current UP/DOWN position

        Returns:
            tuple: (new_position, reversed, message)
                - new_position (str): New UP/DOWN position
                - reversed (bool): Whether position was reversed
                - message (str): Explanation message
        """
        actual_mid_direction = "UP" if mid_price > start_price else "DOWN"

        if expected_mid_direction is None:
            # No strong expectation, hold position
            return current_position, False, "No strong mid-period expectation - holding position"

        if actual_mid_direction == expected_mid_direction:
            # Pattern holding, keep position
            return current_position, False, f"Mid-period matches expectation ({actual_mid_direction}) - holding {current_position}"

        # Pattern not holding, reverse position
        new_position = "DOWN" if current_position == "UP" else "UP"
        return new_position, True, f"Mid-period mismatch! Expected {expected_mid_direction}, got {actual_mid_direction} - REVERSING to {new_position}"

    def can_trade(self, history_size):
        """
        Check if strategy has enough data to make predictions.

        Args:
            history_size (int): Number of periods in history

        Returns:
            bool: True if can trade, False otherwise
        """
        return history_size >= MIN_PERIODS

    def get_name(self):
        """Get strategy name"""
        return self.name

    def __str__(self):
        """String representation"""
        return f"{self.name.title()} Strategy"
