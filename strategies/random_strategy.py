"""
Random Strategy - Makes random UP/DOWN decisions
"""
import random
from strategies.base_strategy import BaseStrategy
from config import MIN_PERIODS


class RandomStrategy(BaseStrategy):
    """
    Random coin flip strategy.
    Randomly picks UP or DOWN at each boundary.
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

        # Randomly pick UP or DOWN
        prediction = random.choice(["UP", "DOWN"])
        score = 0
        reasons = ["Random strategy: coin flip decision"]
        expected_mid_direction = None  # No mid-period expectations for random strategy

        return prediction, score, reasons, expected_mid_direction
