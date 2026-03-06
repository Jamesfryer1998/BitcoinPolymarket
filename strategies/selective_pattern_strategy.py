"""
Selective Pattern Strategy - Trades only high-confidence setups
"""
from strategies.base_strategy import BaseStrategy
from config import MIN_PERIODS, LOOKBACK_PERIODS


class SelectivePatternStrategy(BaseStrategy):
    """
    Improved pattern strategy designed for higher win rate.

    Enhancements:
    - Skips low confidence setups
    - Detects volatility regimes
    - Uses momentum acceleration
    - Stronger streak reversion logic
    - Mid-period confirmation expectations
    """

    CONFIDENCE_THRESHOLD = 3  # Lowered to allow more trades
    VOLATILITY_THRESHOLD = 20  # Adjusted for BTC price scale (~$70k)

    def __init__(self):
        super().__init__("selective_pattern")

    def analyze(self, history):
        """
        Analyze historical patterns and make a prediction.

        Args:
            history (list): List of historical period dicts

        Returns:
            tuple: (prediction, score, reasons, expected_mid_direction)
                   prediction can be None if confidence is too low
        """
        if len(history) < MIN_PERIODS:
            return None, None, [], None

        recent = history[-LOOKBACK_PERIODS:]
        reasons = []

        total_periods = len(recent)

        up_count = sum(1 for p in recent if p["direction"] == "UP")
        down_count = total_periods - up_count
        up_rate = up_count / total_periods

        reasons.append(
            f"Analyzed {total_periods} periods: {up_count} UP ({up_rate:.1%}) / {down_count} DOWN ({1-up_rate:.1%})"
        )

        # ------------------------------------
        # VOLATILITY FILTER
        # ------------------------------------

        if all("start_price" in p and "end_price" in p for p in recent[-3:]):
            moves = [abs(p["end_price"] - p["start_price"]) for p in recent[-3:]]
            avg_move = sum(moves) / len(moves)

            reasons.append(f"Avg move last 3 periods: {avg_move:.2f}")

            if avg_move < self.VOLATILITY_THRESHOLD:
                reasons.append("Low volatility regime - skipping trade")
                return None, None, reasons, None

        # ------------------------------------
        # STREAK ANALYSIS
        # ------------------------------------

        current_streak = 1
        for i in range(len(recent) - 1, 0, -1):
            if recent[i]["direction"] == recent[i - 1]["direction"]:
                current_streak += 1
            else:
                break

        reasons.append(
            f"Current streak: {current_streak} {recent[-1]['direction']} periods"
        )

        # ------------------------------------
        # MIDPOINT PATTERNS
        # ------------------------------------

        up_periods = [p for p in recent if p["direction"] == "UP"]
        down_periods = [p for p in recent if p["direction"] == "DOWN"]

        up_mid_up_rate = None
        down_mid_down_rate = None

        if up_periods:
            up_mid_up_rate = sum(
                1 for p in up_periods if p["mid_direction"] == "UP"
            ) / len(up_periods)

            reasons.append(
                f"UP mid confirmation rate: {up_mid_up_rate:.1%}"
            )

        if down_periods:
            down_mid_down_rate = sum(
                1 for p in down_periods if p["mid_direction"] == "DOWN"
            ) / len(down_periods)

            reasons.append(
                f"DOWN mid confirmation rate: {down_mid_down_rate:.1%}"
            )

        # ------------------------------------
        # MOMENTUM ACCELERATION
        # ------------------------------------

        score = 0

        if len(recent) >= 6:
            last_3 = recent[-3:]
            prev_3 = recent[-6:-3]

            last_up = sum(1 for p in last_3 if p["direction"] == "UP")
            prev_up = sum(1 for p in prev_3 if p["direction"] == "UP")

            if last_up > prev_up:
                score += 2
                reasons.append("Momentum accelerating UP (+2)")

            elif last_up < prev_up:
                score -= 2
                reasons.append("Momentum accelerating DOWN (-2)")

        # ------------------------------------
        # DIRECTIONAL BIAS
        # ------------------------------------

        if up_rate > 0.62:
            score += 4
            reasons.append("Strong UP bias (+4)")

        elif up_rate < 0.38:
            score -= 4
            reasons.append("Strong DOWN bias (-4)")

        elif up_rate > 0.55:
            score += 2
            reasons.append("Moderate UP bias (+2)")

        elif up_rate < 0.45:
            score -= 2
            reasons.append("Moderate DOWN bias (-2)")

        else:
            reasons.append("No clear directional bias")

        # ------------------------------------
        # STREAK LOGIC
        # ------------------------------------

        last_direction = recent[-1]["direction"]

        if current_streak >= 6:

            if last_direction == "UP":
                score -= 4
                reasons.append("Extreme UP streak → reversion (-4)")

            else:
                score += 4
                reasons.append("Extreme DOWN streak → reversion (+4)")

        elif current_streak >= 3:

            if last_direction == "UP":
                score += 1
                reasons.append("UP momentum streak (+1)")

            else:
                score -= 1
                reasons.append("DOWN momentum streak (-1)")

        # ------------------------------------
        # CONFIDENCE FILTER
        # ------------------------------------

        if score >= self.CONFIDENCE_THRESHOLD:
            prediction = "UP"

        elif score <= -self.CONFIDENCE_THRESHOLD:
            prediction = "DOWN"

        else:
            return None, score, reasons, None

        # ------------------------------------
        # MIDPOINT EXPECTATION
        # ------------------------------------

        expected_mid_direction = None

        if prediction == "UP" and up_mid_up_rate and up_mid_up_rate > 0.6:
            expected_mid_direction = "UP"

        elif prediction == "DOWN" and down_mid_down_rate and down_mid_down_rate > 0.6:
            expected_mid_direction = "DOWN"

        reasons.append(f"Final score: {score} → Prediction: {prediction}")

        return prediction, score, reasons, expected_mid_direction
