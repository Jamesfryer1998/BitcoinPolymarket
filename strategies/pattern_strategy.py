"""
Pattern Strategy - Analyzes historical patterns to make predictions
"""
from strategies.base_strategy import BaseStrategy
from config import MIN_PERIODS, LOOKBACK_PERIODS


class PatternStrategy(BaseStrategy):
    """
    Pattern-based trading strategy.
    Analyzes last 20-30 periods for statistical patterns including:
    - Overall directional bias (UP/DOWN win rates)
    - Recent momentum (last 5 periods)
    - Streak analysis with mean reversion signals
    - Mid-period behavior patterns
    """

    def __init__(self):
        super().__init__("pattern")

    def analyze(self, history):
        """
        Analyze historical patterns and make a prediction.

        Args:
            history (list): List of historical period dicts

        Returns:
            tuple: (prediction, score, reasons, expected_mid_direction)
        """
        if len(history) < MIN_PERIODS:
            return None, None, [], None

        # Analyze recent history
        recent = history[-LOOKBACK_PERIODS:]

        # Calculate basic statistics
        total_periods = len(recent)
        up_count = sum(1 for p in recent if p["direction"] == "UP")
        down_count = total_periods - up_count
        up_rate = up_count / total_periods

        reasons = []
        reasons.append(f"Analyzed last {total_periods} periods: {up_count} UP ({up_rate:.1%}), {down_count} DOWN ({1-up_rate:.1%})")

        # Analyze streaks
        current_streak = 1
        for i in range(len(recent) - 1, 0, -1):
            if recent[i]["direction"] == recent[i-1]["direction"]:
                current_streak += 1
            else:
                break

        if current_streak >= 3:
            reasons.append(f"Current streak: {current_streak} consecutive {recent[-1]['direction']} periods")

        # Analyze mid-period patterns
        up_periods = [p for p in recent if p["direction"] == "UP"]
        down_periods = [p for p in recent if p["direction"] == "DOWN"]

        if up_periods:
            up_mid_up_count = sum(1 for p in up_periods if p["mid_direction"] == "UP")
            up_mid_up_rate = up_mid_up_count / len(up_periods)
            reasons.append(f"UP periods: {up_mid_up_rate:.1%} had UP at 2:30 mark")

        if down_periods:
            down_mid_down_count = sum(1 for p in down_periods if p["mid_direction"] == "DOWN")
            down_mid_down_rate = down_mid_down_count / len(down_periods)
            reasons.append(f"DOWN periods: {down_mid_down_rate:.1%} had DOWN at 2:30 mark")

        # Decision logic based on multiple factors
        score = 0

        # Factor 1: Win rate (40% weight)
        if up_rate > 0.60:
            score += 4
            reasons.append("Strong UP bias in recent history (+4)")
        elif up_rate < 0.40:
            score -= 4
            reasons.append("Strong DOWN bias in recent history (-4)")
        elif up_rate > 0.55:
            score += 2
            reasons.append("Moderate UP bias (+2)")
        elif up_rate < 0.45:
            score -= 2
            reasons.append("Moderate DOWN bias (-2)")
        else:
            reasons.append("No clear directional bias (neutral)")

        # Factor 2: Recent momentum (30% weight) - last 5 periods
        last_5 = recent[-5:]
        last_5_up = sum(1 for p in last_5 if p["direction"] == "UP")
        if last_5_up >= 4:
            score += 3
            reasons.append(f"Recent momentum: {last_5_up}/5 UP (+3)")
        elif last_5_up <= 1:
            score -= 3
            reasons.append(f"Recent momentum: {last_5_up}/5 UP, strong DOWN (-3)")
        elif last_5_up >= 3:
            score += 1
            reasons.append(f"Recent momentum: {last_5_up}/5 UP (+1)")
        elif last_5_up <= 2:
            score -= 1
            reasons.append(f"Recent momentum: {last_5_up}/5 UP (-1)")

        # Factor 3: Streak analysis (30% weight)
        if current_streak >= 5:
            # Long streak - slight mean reversion bias
            if recent[-1]["direction"] == "UP":
                score -= 2
                reasons.append("Very long UP streak - mean reversion signal (-2)")
            else:
                score += 2
                reasons.append("Very long DOWN streak - mean reversion signal (+2)")
        elif current_streak >= 3:
            # Medium streak - momentum bias
            if recent[-1]["direction"] == "UP":
                score += 1
                reasons.append("Medium UP streak - momentum signal (+1)")
            else:
                score -= 1
                reasons.append("Medium DOWN streak - momentum signal (-1)")

        # Final decision
        if score > 0:
            prediction = "UP"
        elif score < 0:
            prediction = "DOWN"
        else:
            # Tie-breaker: use recent win rate
            prediction = "UP" if up_rate >= 0.5 else "DOWN"
            reasons.append("Score tied - using win rate as tie-breaker")

        # Prepare mid-period expectations
        expected_mid_direction = None
        if prediction == "UP" and up_periods:
            expected_mid_direction = "UP" if up_mid_up_rate > 0.6 else None
        elif prediction == "DOWN" and down_periods:
            expected_mid_direction = "DOWN" if down_mid_down_rate > 0.6 else None

        return prediction, score, reasons, expected_mid_direction
