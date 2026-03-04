"""
Trade Storage - Persistent storage for trade history
Saves trades to JSON files in data/storage/
"""
import json
import os
from typing import Dict, List, Optional
from datetime import datetime
from config import STORAGE_DIR


class TradeStorage:
    """
    Handles persistent storage of trade history for strategies.
    """

    def __init__(self, strategy_name: str):
        """
        Initialize trade storage for a strategy.

        Args:
            strategy_name: Name of the strategy
        """
        self.strategy_name = strategy_name
        self.file_path = os.path.join(STORAGE_DIR, f"trade_history_{strategy_name}.json")

        # Ensure storage directory exists
        os.makedirs(STORAGE_DIR, exist_ok=True)

        # Load existing history
        self.trades = self._load_trades()

    def _load_trades(self) -> List[Dict]:
        """Load trades from JSON file"""
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Could not load trade history for {self.strategy_name}: {e}")
                return []
        return []

    def _save_trades(self):
        """Save trades to JSON file"""
        try:
            with open(self.file_path, 'w') as f:
                json.dump(self.trades, f, indent=2)
        except IOError as e:
            print(f"Error saving trade history for {self.strategy_name}: {e}")

    def save_trade(self, trade: Dict) -> Dict:
        """
        Save a new trade to history.

        Args:
            trade: Dict containing trade details
                   Required fields:
                   - timestamp (ISO format string)
                   - direction ("UP" or "DOWN")
                   - entry_price (float)
                   - bet_amount (float)
                   - is_midpoint_bet (bool)

                   Optional fields (filled on close):
                   - exit_price (float)
                   - profit_loss (float)
                   - result ("win" or "loss")

        Returns:
            Dict: The saved trade with added trade_id
        """
        # Add trade ID
        trade_id = f"{self.strategy_name}_{len(self.trades) + 1}_{datetime.now().timestamp()}"
        trade["trade_id"] = trade_id

        # Add to history
        self.trades.append(trade)
        self._save_trades()

        return trade

    def update_trade(self, trade_id: str, updates: Dict) -> Optional[Dict]:
        """
        Update an existing trade (e.g., when closing position).

        Args:
            trade_id: ID of trade to update
            updates: Dict with fields to update

        Returns:
            Updated trade dict, or None if not found
        """
        for trade in self.trades:
            if trade.get("trade_id") == trade_id:
                trade.update(updates)
                self._save_trades()
                return trade

        print(f"Warning: Trade {trade_id} not found")
        return None

    def get_history(self, limit: Optional[int] = None) -> List[Dict]:
        """
        Get trade history.

        Args:
            limit: Optional limit on number of trades to return (most recent)

        Returns:
            List of trade dicts
        """
        if limit:
            return self.trades[-limit:]
        return self.trades

    def get_stats(self) -> Dict:
        """
        Calculate statistics from trade history.

        Returns:
            Dict with total_trades, winning_trades, total_pnl, etc.
        """
        if not self.trades:
            return {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0.0,
                "total_pnl": 0.0,
                "avg_profit": 0.0,
                "avg_loss": 0.0
            }

        completed_trades = [t for t in self.trades if "profit_loss" in t]

        if not completed_trades:
            return {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0.0,
                "total_pnl": 0.0,
                "avg_profit": 0.0,
                "avg_loss": 0.0
            }

        winning_trades = [t for t in completed_trades if t.get("result") == "win"]
        losing_trades = [t for t in completed_trades if t.get("result") == "loss"]

        total_pnl = sum(t.get("profit_loss", 0.0) for t in completed_trades)
        avg_profit = sum(t.get("profit_loss", 0.0) for t in winning_trades) / len(winning_trades) if winning_trades else 0.0
        avg_loss = sum(t.get("profit_loss", 0.0) for t in losing_trades) / len(losing_trades) if losing_trades else 0.0

        return {
            "total_trades": len(completed_trades),
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "win_rate": len(winning_trades) / len(completed_trades) if completed_trades else 0.0,
            "total_pnl": total_pnl,
            "avg_profit": avg_profit,
            "avg_loss": avg_loss
        }

    def clear_history(self):
        """Clear all trade history"""
        self.trades = []
        self._save_trades()
