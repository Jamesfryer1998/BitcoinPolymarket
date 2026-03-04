"""
Polymarket API Integration
Handles fetching BTC 5-minute market data and prices
"""
import requests
import json
from datetime import datetime
from typing import Dict, Tuple, Optional
from config import POLYMARKET_GAMMA_API, POLYMARKET_CLOB_API


class PolymarketAPI:
    """
    Interface to Polymarket Gamma and CLOB APIs for BTC 5-minute markets.
    """

    def __init__(self):
        self.gamma_api = POLYMARKET_GAMMA_API
        self.clob_api = POLYMARKET_CLOB_API

    def get_boundary_slug(self, timestamp: Optional[datetime] = None) -> str:
        """
        Calculate Polymarket market slug for a given 5-minute boundary.

        Args:
            timestamp: Datetime at or near the boundary. If None, uses current time.

        Returns:
            str: Market slug in format btc-updown-5m-{unix_timestamp}
        """
        if timestamp is None:
            timestamp = datetime.now()

        # Round down to nearest 5-minute boundary
        minute = (timestamp.minute // 5) * 5
        boundary = timestamp.replace(minute=minute, second=0, microsecond=0)

        # Convert to Unix timestamp
        unix_ts = int(boundary.timestamp())

        return f"btc-updown-5m-{unix_ts}"

    def get_market_tokens(self, slug: str) -> Dict[str, str]:
        """
        Fetch Up and Down token IDs for a given market slug.

        Args:
            slug: Market slug (e.g., btc-updown-5m-1772621400)

        Returns:
            Dict with keys 'Up' and 'Down' mapping to clobTokenIds

        Raises:
            Exception: If API call fails or market not found
        """
        try:
            r = requests.get(
                f"{self.gamma_api}/events",
                params={"slug": slug},
                timeout=10
            )
            r.raise_for_status()

            events = r.json()
            if not events:
                raise Exception(f"No market found for slug: {slug}")

            event = events[0]
            market = event["markets"][0]

            # Parse JSON strings to actual lists
            outcomes = json.loads(market["outcomes"])
            token_ids = json.loads(market["clobTokenIds"])

            # Map outcomes to token IDs
            tokens = dict(zip(outcomes, token_ids))

            if "Up" not in tokens or "Down" not in tokens:
                raise Exception(f"Market does not have Up/Down outcomes: {slug}")

            return {
                "Up": tokens["Up"],
                "Down": tokens["Down"]
            }

        except requests.RequestException as e:
            raise Exception(f"Failed to fetch market tokens for {slug}: {e}")

    def get_token_prices(self, token_ids: Dict[str, str]) -> Dict[str, float]:
        """
        Fetch current prices (best bid/ask midpoint) for Up and Down tokens.

        Args:
            token_ids: Dict with keys 'Up' and 'Down' mapping to token IDs

        Returns:
            Dict with keys 'Up' and 'Down' mapping to prices (0.0 to 1.0)

        Raises:
            Exception: If API call fails
        """
        prices = {}

        for outcome, token_id in token_ids.items():
            try:
                # Fetch orderbook from CLOB API
                r = requests.get(
                    f"{self.clob_api}/price",
                    params={"token_id": token_id},
                    timeout=10
                )
                r.raise_for_status()

                data = r.json()

                # Get midpoint price (average of best bid and best ask)
                # If no orderbook data, default to 0.5
                if "mid" in data and data["mid"]:
                    prices[outcome] = float(data["mid"])
                else:
                    # Fallback: calculate from bid/ask if available
                    best_bid = float(data.get("bid", 0.5))
                    best_ask = float(data.get("ask", 0.5))
                    prices[outcome] = (best_bid + best_ask) / 2.0

            except requests.RequestException as e:
                # On error, default to 0.5 (neutral)
                print(f"Warning: Failed to fetch price for {outcome} token {token_id}: {e}")
                prices[outcome] = 0.5

        return prices

    def get_market_prices(self, slug: str) -> Tuple[float, float]:
        """
        Convenience method to get Up and Down prices for a market slug.

        Args:
            slug: Market slug

        Returns:
            Tuple of (up_price, down_price)

        Raises:
            Exception: If API calls fail
        """
        tokens = self.get_market_tokens(slug)
        prices = self.get_token_prices(tokens)
        return prices["Up"], prices["Down"]

    def get_current_market_prices(self, timestamp: Optional[datetime] = None) -> Tuple[float, float, str]:
        """
        Get current market Up/Down prices for the current or specified boundary.

        Args:
            timestamp: Optional timestamp for specific boundary

        Returns:
            Tuple of (up_price, down_price, slug)

        Raises:
            Exception: If API calls fail
        """
        slug = self.get_boundary_slug(timestamp)
        up_price, down_price = self.get_market_prices(slug)
        return up_price, down_price, slug


# Singleton instance
_polymarket_api = None


def get_polymarket_api():
    """Get singleton PolymarketAPI instance"""
    global _polymarket_api
    if _polymarket_api is None:
        _polymarket_api = PolymarketAPI()
    return _polymarket_api
