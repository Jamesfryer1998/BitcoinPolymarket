"""
Trading Engine - P&L Simulation for Polymarket BTC Markets
Handles bet placement, position tracking, and profit/loss calculation
"""
from typing import Dict, Optional, List, Tuple
from datetime import datetime


class Position:
    """Represents a single bet position"""

    def __init__(self, direction: str, bet_amount: float, entry_price: float,
                 timestamp: datetime, is_midpoint: bool = False):
        self.direction = direction  # "UP" or "DOWN"
        self.bet_amount = bet_amount
        self.entry_price = entry_price
        self.timestamp = timestamp
        self.is_midpoint = is_midpoint

        # Calculate shares purchased
        # shares = bet_amount / price
        self.shares = bet_amount / entry_price if entry_price > 0 else 0

    def calculate_pnl(self, outcome: str) -> float:
        """
        Calculate profit/loss for this position.

        Args:
            outcome: Actual outcome "UP" or "DOWN"

        Returns:
            float: Profit (positive) or loss (negative)
        """
        if outcome == self.direction:
            # Win: shares * $1.00 - bet_amount
            return self.shares * 1.0 - self.bet_amount
        else:
            # Loss: -bet_amount
            return -self.bet_amount

    def potential_profit(self) -> float:
        """Calculate potential profit if bet wins"""
        return self.shares * 1.0 - self.bet_amount

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization"""
        return {
            "direction": self.direction,
            "bet_amount": self.bet_amount,
            "entry_price": self.entry_price,
            "shares": self.shares,
            "timestamp": self.timestamp.isoformat(),
            "is_midpoint": self.is_midpoint,
            "potential_profit": self.potential_profit()
        }


class TradingEngine:
    """
    Manages trading simulation for a single strategy.
    Tracks balance, open positions, and P&L.
    """

    def __init__(self, strategy_name: str, starting_capital: float, bet_amount: float):
        """
        Initialize trading engine.

        Args:
            strategy_name: Name of the strategy
            starting_capital: Starting balance
            bet_amount: Default bet amount per position
        """
        self.strategy_name = strategy_name
        self.starting_capital = starting_capital
        self.balance = starting_capital
        self.bet_amount = bet_amount

        # Current open positions
        self.open_positions: List[Position] = []

        # Tracking
        self.total_trades = 0
        self.winning_trades = 0
        self.total_profit_loss = 0.0

    def place_bet(self, direction: str, entry_price: float,
                  timestamp: datetime, is_midpoint: bool = False) -> Position:
        """
        Place a bet (open a position).

        Args:
            direction: "UP" or "DOWN"
            entry_price: Price at which bet is placed (0.0 to 1.0)
            timestamp: Time of bet
            is_midpoint: Whether this is a midpoint reversal bet

        Returns:
            Position object

        Raises:
            ValueError: If insufficient balance
        """
        if self.balance < self.bet_amount:
            raise ValueError(f"Insufficient balance: ${self.balance:.2f} < ${self.bet_amount:.2f}")

        position = Position(direction, self.bet_amount, entry_price, timestamp, is_midpoint)
        self.open_positions.append(position)
        self.balance -= self.bet_amount

        return position

    def close_positions(self, outcome: str, timestamp: datetime) -> Tuple[float, List[Dict]]:
        """
        Close all open positions and calculate P&L.

        Args:
            outcome: Actual market outcome "UP" or "DOWN"
            timestamp: Time of close

        Returns:
            Tuple of (net_pnl, closed_positions_details)
        """
        net_pnl = 0.0
        closed_positions = []

        for position in self.open_positions:
            pnl = position.calculate_pnl(outcome)
            net_pnl += pnl

            closed_positions.append({
                "direction": position.direction,
                "bet_amount": position.bet_amount,
                "entry_price": position.entry_price,
                "shares": position.shares,
                "is_midpoint": position.is_midpoint,
                "pnl": pnl,
                "won": outcome == position.direction,
                "entry_timestamp": position.timestamp.isoformat(),
                "close_timestamp": timestamp.isoformat()
            })

            # Track statistics
            self.total_trades += 1
            if pnl > 0:
                self.winning_trades += 1

        # Update balance with winnings
        self.balance += net_pnl + sum(p.bet_amount for p in self.open_positions)
        self.total_profit_loss += net_pnl

        # Clear open positions
        self.open_positions = []

        return net_pnl, closed_positions

    def get_unrealized_pnl(self, current_up_price: float, current_down_price: float) -> float:
        """
        Calculate unrealized P&L for open positions.

        Args:
            current_up_price: Current UP token price
            current_down_price: Current DOWN token price

        Returns:
            float: Unrealized profit/loss
        """
        unrealized = 0.0

        for position in self.open_positions:
            current_price = current_up_price if position.direction == "UP" else current_down_price

            # Current position value = shares * current_price
            current_value = position.shares * current_price

            # Unrealized P&L = current_value - bet_amount
            unrealized += current_value - position.bet_amount

        return unrealized

    def get_status(self) -> Dict:
        """
        Get current status of the trading engine.

        Returns:
            Dict with balance, P&L, stats, and open positions
        """
        return {
            "strategy": self.strategy_name,
            "balance": self.balance,
            "starting_capital": self.starting_capital,
            "total_profit_loss": self.total_profit_loss,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "win_rate": self.winning_trades / self.total_trades if self.total_trades > 0 else 0.0,
            "open_positions": [p.to_dict() for p in self.open_positions],
            "num_open_positions": len(self.open_positions)
        }

    def reset(self):
        """Reset engine to starting state"""
        self.balance = self.starting_capital
        self.open_positions = []
        self.total_trades = 0
        self.winning_trades = 0
        self.total_profit_loss = 0.0
