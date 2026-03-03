"""
Random Strategy - Makes random BUY/SELL decisions
"""
import random
from strategies.base_strategy import BaseStrategy
from config import MIN_PERIODS


class RandomStrategy(BaseStrategy):
    """
    Random coin flip strategy.
    Randomly picks BUY or SELL at each boundary.
    Serves as a baseline to measure if pattern strategy adds value.
    Expected win rate: ~50%
    """

    def __init__(self):
        super().__init__("random")

    def analyze(self, history):
        """
        Make a random prediction.

        Args:
            history (list): List of historical period dicts (not used)

        Returns:
            tuple: (prediction, score, reasons, expected_mid_direction)
        """
        if len(history) < MIN_PERIODS:
            return None, None, [], None

        # Randomly pick BUY or SELL
        prediction = random.choice(["BUY", "SELL"])
        score = 0
        reasons = ["Random strategy: coin flip decision"]
        expected_mid_direction = None  # No mid-period expectations for random strategy

        return prediction, score, reasons, expected_mid_direction
