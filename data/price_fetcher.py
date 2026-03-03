"""
BTC Price Fetcher - Handles all price data retrieval from Binance API
"""
import requests
from datetime import datetime
from config import BINANCE_API, SYMBOL


class PriceFetcher:
    """Fetches BTC price data from Binance API"""

    def __init__(self, symbol=SYMBOL):
        self.symbol = symbol
        self.api_url = BINANCE_API

    def get_current_price(self):
        """
        Get current BTC price from Binance.

        Returns:
            float: Current BTC price in USD

        Raises:
            requests.RequestException: If API call fails
        """
        url = f"{self.api_url}/ticker/price"
        params = {"symbol": self.symbol}

        try:
            r = requests.get(url, params=params, timeout=10)
            r.raise_for_status()
            data = r.json()
            return float(data["price"])
        except requests.RequestException as e:
            raise Exception(f"Failed to fetch current price: {e}")

    def get_1min_candles(self, limit=150):
        """
        Fetch 1-minute candles from Binance.

        Args:
            limit (int): Number of candles to fetch (default: 150 = 30 5-min periods)

        Returns:
            list: List of candle dicts with keys: open_time, open, high, low, close

        Raises:
            requests.RequestException: If API call fails
        """
        url = f"{self.api_url}/klines"
        params = {
            "symbol": self.symbol,
            "interval": "1m",
            "limit": limit
        }

        try:
            r = requests.get(url, params=params, timeout=10)
            r.raise_for_status()
            data = r.json()

            # Parse candles: [open_time, open, high, low, close, ...]
            candles = []
            for c in data:
                candles.append({
                    "open_time": int(c[0]),
                    "open": float(c[1]),
                    "high": float(c[2]),
                    "low": float(c[3]),
                    "close": float(c[4]),
                })

            return candles
        except requests.RequestException as e:
            raise Exception(f"Failed to fetch 1-min candles: {e}")

    def get_5min_periods(self, num_periods=30):
        """
        Fetch and group 1-minute candles into 5-minute periods aligned to boundaries.

        Args:
            num_periods (int): Number of 5-minute periods to fetch

        Returns:
            list: List of period dicts with start/mid/end prices and directions
        """
        from datetime import datetime, timedelta

        # Calculate the most recent completed 5-minute boundary
        now = datetime.now()
        current_minute = (now.minute // 5) * 5
        last_boundary = now.replace(minute=current_minute, second=0, microsecond=0)

        # Go back to the previous boundary (current period might not be complete)
        last_completed_boundary = last_boundary - timedelta(minutes=5)

        # Calculate how many 1-min candles we need
        # We need 5 candles per period, plus some buffer
        total_candles_needed = num_periods * 5 + 10  # +10 for alignment buffer

        # Fetch candles
        candles = self.get_1min_candles(limit=total_candles_needed)

        if len(candles) < 10:
            return []

        # Find candles that align to 5-minute boundaries
        # Group candles by their 5-minute boundary
        boundary_groups = {}

        for candle in candles:
            candle_time = datetime.fromtimestamp(candle["open_time"] / 1000)
            # Round down to nearest 5-minute boundary
            boundary_minute = (candle_time.minute // 5) * 5
            boundary_time = candle_time.replace(minute=boundary_minute, second=0, microsecond=0)

            if boundary_time not in boundary_groups:
                boundary_groups[boundary_time] = []

            boundary_groups[boundary_time].append(candle)

        # Sort boundaries in descending order (most recent first)
        sorted_boundaries = sorted(boundary_groups.keys(), reverse=True)

        periods = []

        # Process each complete 5-minute period
        for boundary in sorted_boundaries:
            candles_in_period = boundary_groups[boundary]

            # We need exactly 5 candles for a complete period
            if len(candles_in_period) >= 5:
                # Sort candles by time
                candles_in_period.sort(key=lambda c: c["open_time"])
                period_candles = candles_in_period[:5]

                # Extract prices:
                # - Start: close of 1st candle (minute 0)
                # - Mid: close of 3rd candle (minute 2, closest to 2:30)
                # - End: close of 5th candle (minute 4/5)
                start_price = period_candles[0]["close"]
                mid_price = period_candles[2]["close"]
                end_price = period_candles[4]["close"]

                # Calculate directions
                direction = "UP" if end_price > start_price else "DOWN"
                mid_direction = "UP" if mid_price > start_price else "DOWN"

                period = {
                    "timestamp": boundary.isoformat(),
                    "start_price": start_price,
                    "mid_price": mid_price,
                    "end_price": end_price,
                    "direction": direction,
                    "mid_direction": mid_direction,
                    "change_pct": ((end_price - start_price) / start_price) * 100,
                    "mid_change_pct": ((mid_price - start_price) / start_price) * 100,
                    "source": "binance"
                }

                periods.append(period)

                # Stop when we have enough periods
                if len(periods) >= num_periods:
                    break

        # Return in chronological order (oldest first)
        return list(reversed(periods))


# Singleton instance
_price_fetcher = None

def get_price_fetcher():
    """Get singleton PriceFetcher instance"""
    global _price_fetcher
    if _price_fetcher is None:
        _price_fetcher = PriceFetcher()
    return _price_fetcher
