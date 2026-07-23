"""
Advanced features for Kronos TradingView interface:
- Portfolio Management
- Backtesting Engine
- Risk Analysis
- Performance Metrics
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from enum import Enum

class OrderType(Enum):
    BUY = "BUY"
    SELL = "SELL"

class OrderStatus(Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"

@dataclass
class Order:
    """Represents a trading order"""
    symbol: str
    order_type: OrderType
    quantity: float
    price: float
    timestamp: datetime
    status: OrderStatus = OrderStatus.PENDING
    fees: float = 0.0

@dataclass
class Position:
    """Represents an open position"""
    symbol: str
    quantity: float
    entry_price: float
    entry_time: datetime
    current_price: float = 0.0
    
    @property
    def pnl(self) -> float:
        """Unrealized P&L"""
        return self.quantity * (self.current_price - self.entry_price)
    
    @property
    def pnl_percentage(self) -> float:
        """Unrealized P&L percentage"""
        if self.entry_price == 0:
            return 0
        return (self.pnl / (self.quantity * self.entry_price)) * 100

class Portfolio:
    """Portfolio management system"""
    
    def __init__(self, initial_capital: float = 10000.0, commission_pct: float = 0.001):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.commission_pct = commission_pct
        self.positions: Dict[str, Position] = {}
        self.orders: List[Order] = []
        self.trades_history: List[Dict] = []
        self.cash = initial_capital
        
    def buy(self, symbol: str, quantity: float, price: float, timestamp: datetime) -> bool:
        """Execute a buy order"""
        cost = quantity * price * (1 + self.commission_pct)
        
        if cost > self.cash:
            return False
        
        self.cash -= cost
        
        if symbol in self.positions:
            # Average the entry price for existing positions
            old_pos = self.positions[symbol]
            new_qty = old_pos.quantity + quantity
            new_entry = (old_pos.entry_price * old_pos.quantity + price * quantity) / new_qty
            self.positions[symbol].quantity = new_qty
            self.positions[symbol].entry_price = new_entry
        else:
            self.positions[symbol] = Position(
                symbol=symbol,
                quantity=quantity,
                entry_price=price,
                entry_time=timestamp,
                current_price=price
            )
        
        self.orders.append(Order(
            symbol=symbol,
            order_type=OrderType.BUY,
            quantity=quantity,
            price=price,
            timestamp=timestamp,
            fees=cost - (quantity * price)
        ))
        
        return True
    
    def sell(self, symbol: str, quantity: float, price: float, timestamp: datetime) -> Tuple[bool, float]:
        """Execute a sell order"""
        if symbol not in self.positions or self.positions[symbol].quantity < quantity:
            return False, 0
        
        position = self.positions[symbol]
        proceeds = quantity * price * (1 - self.commission_pct)
        pnl = quantity * (price - position.entry_price)
        
        self.cash += proceeds
        
        position.quantity -= quantity
        if position.quantity == 0:
            del self.positions[symbol]
        
        self.orders.append(Order(
            symbol=symbol,
            order_type=OrderType.SELL,
            quantity=quantity,
            price=price,
            timestamp=timestamp,
            fees=quantity * price * self.commission_pct
        ))
        
        self.trades_history.append({
            'symbol': symbol,
            'entry_price': position.entry_price,
            'exit_price': price,
            'quantity': quantity,
            'entry_time': position.entry_time,
            'exit_time': timestamp,
            'pnl': pnl,
            'pnl_pct': (pnl / (quantity * position.entry_price)) * 100 if position.entry_price > 0 else 0,
            'type': 'long'
        })
        
        return True, pnl
    
    def get_portfolio_value(self) -> float:
        """Calculate total portfolio value"""
        position_value = sum(
            pos.quantity * pos.current_price 
            for pos in self.positions.values()
        )
        return self.cash + position_value
    
    def get_unrealized_pnl(self) -> float:
        """Get total unrealized P&L"""
        return sum(pos.pnl for pos in self.positions.values())
    
    def get_realized_pnl(self) -> float:
        """Get total realized P&L"""
        return sum(trade['pnl'] for trade in self.trades_history)
    
    def update_prices(self, prices: Dict[str, float]):
        """Update current prices for all positions"""
        for symbol, price in prices.items():
            if symbol in self.positions:
                self.positions[symbol].current_price = price


class BacktestEngine:
    """Backtesting engine for strategy evaluation"""
    
    def __init__(self, initial_capital: float = 10000.0, commission_pct: float = 0.001):
        self.portfolio = Portfolio(initial_capital, commission_pct)
        self.initial_capital = initial_capital
        self.equity_curve = []
        self.returns = []
        
    def execute_strategy(self, 
                        data: pd.DataFrame,
                        signals: pd.DataFrame,
                        symbol: str = 'BTC/USDT') -> Dict:
        """
        Execute a trading strategy based on signals
        
        Args:
            data: OHLCV data with 'close' column
            signals: Signal data with 'signal' column (1=BUY, 0=HOLD, -1=SELL)
            symbol: Trading symbol
            
        Returns:
            Performance metrics dictionary
        """
        
        for i in range(1, len(data)):
            current_price = data.iloc[i]['close']
            signal = signals.iloc[i]['signal'] if i < len(signals) else 0
            timestamp = data.index[i]
            
            # Update portfolio prices
            self.portfolio.update_prices({symbol: current_price})
            
            # Execute trades based on signals
            if signal > 0.5:  # Buy signal
                # Risk management: allocate 10% of capital per trade
                allocation = self.portfolio.capital * 0.1
                quantity = allocation / current_price
                self.portfolio.buy(symbol, quantity, current_price, timestamp)
                
            elif signal < -0.5:  # Sell signal
                if symbol in self.portfolio.positions:
                    quantity = self.portfolio.positions[symbol].quantity
                    self.portfolio.sell(symbol, quantity, current_price, timestamp)
            
            # Record equity
            self.equity_curve.append({
                'timestamp': timestamp,
                'value': self.portfolio.get_portfolio_value(),
                'cash': self.portfolio.cash
            })
        
        return self.calculate_metrics()
    
    def calculate_metrics(self) -> Dict:
        """Calculate performance metrics"""
        equity_values = np.array([e['value'] for e in self.equity_curve])
        
        if len(equity_values) < 2:
            return {}
        
        # Returns
        returns = np.diff(equity_values) / equity_values[:-1]
        total_return = (equity_values[-1] - self.initial_capital) / self.initial_capital
        
        # Volatility and risk metrics
        volatility = np.std(returns) * np.sqrt(252)  # Annualized
        sharpe_ratio = np.mean(returns) / np.std(returns) * np.sqrt(252) if np.std(returns) > 0 else 0
        
        # Drawdown
        cumulative = np.cumprod(1 + returns)
        running_max = np.maximum.accumulate(cumulative)
        drawdown = (cumulative - running_max) / running_max
        max_drawdown = np.min(drawdown)
        
        # Win rate
        trades = self.portfolio.trades_history
        winning_trades = sum(1 for t in trades if t['pnl'] > 0)
        total_trades = len(trades)
        win_rate = winning_trades / total_trades if total_trades > 0 else 0
        
        # Profit factor
        gross_profit = sum(t['pnl'] for t in trades if t['pnl'] > 0)
        gross_loss = abs(sum(t['pnl'] for t in trades if t['pnl'] < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
        
        return {
            'total_return': round(total_return * 100, 2),
            'annual_volatility': round(volatility * 100, 2),
            'sharpe_ratio': round(sharpe_ratio, 2),
            'max_drawdown': round(max_drawdown * 100, 2),
            'win_rate': round(win_rate * 100, 2),
            'profit_factor': round(profit_factor, 2),
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': total_trades - winning_trades,
            'avg_win': round(np.mean([t['pnl'] for t in trades if t['pnl'] > 0]) if winning_trades > 0 else 0, 2),
            'avg_loss': round(np.mean([t['pnl'] for t in trades if t['pnl'] < 0]) if (total_trades - winning_trades) > 0 else 0, 2),
            'final_value': round(equity_values[-1], 2),
        }


class TechnicalAnalyzer:
    """Technical analysis indicators"""
    
    @staticmethod
    def moving_average(prices: np.ndarray, period: int) -> np.ndarray:
        """Simple Moving Average"""
        return np.convolve(prices, np.ones(period)/period, mode='valid')
    
    @staticmethod
    def rsi(prices: np.ndarray, period: int = 14) -> np.ndarray:
        """Relative Strength Index"""
        deltas = np.diff(prices)
        seed = deltas[:period]
        up = seed[seed >= 0].sum() / period
        down = -seed[seed < 0].sum() / period
        
        rs = np.zeros_like(prices)
        rs[:period] = 100. - 100. / (1. + up / down if down != 0 else 1)
        
        for i in range(period, len(prices)):
            delta = deltas[i - 1]
            if delta > 0:
                upval = delta
                downval = 0.
            else:
                upval = 0.
                downval = -delta
            
            up = (up * (period - 1) + upval) / period
            down = (down * (period - 1) + downval) / period
            
            rs[i] = 100. - 100. / (1. + up / down if down != 0 else 1)
        
        return rs
    
    @staticmethod
    def macd(prices: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """MACD - Moving Average Convergence Divergence"""
        ema_fast = pd.Series(prices).ewm(span=fast).mean().values
        ema_slow = pd.Series(prices).ewm(span=slow).mean().values
        macd_line = ema_fast - ema_slow
        signal_line = pd.Series(macd_line).ewm(span=signal).mean().values
        histogram = macd_line - signal_line
        
        return macd_line, signal_line, histogram
    
    @staticmethod
    def bollinger_bands(prices: np.ndarray, period: int = 20, std_dev: float = 2) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Bollinger Bands"""
        sma = pd.Series(prices).rolling(window=period).mean().values
        std = pd.Series(prices).rolling(window=period).std().values
        
        upper = sma + (std * std_dev)
        lower = sma - (std * std_dev)
        
        return upper, sma, lower
    
    @staticmethod
    def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
        """Average True Range"""
        tr1 = high - low
        tr2 = np.abs(high - close[:-1])
        tr3 = np.abs(low - close[:-1])
        
        tr = np.max([tr1[1:], tr2, tr3], axis=0)
        atr = pd.Series(tr).rolling(window=period).mean().values
        
        return atr


class RiskManager:
    """Risk management calculations"""
    
    @staticmethod
    def calculate_position_size(
        account_size: float,
        entry_price: float,
        stop_loss_price: float,
        risk_percentage: float = 2.0
    ) -> float:
        """
        Calculate position size based on risk management rules
        
        Args:
            account_size: Total account size
            entry_price: Entry price
            stop_loss_price: Stop loss price
            risk_percentage: Percentage of account to risk (default 2%)
            
        Returns:
            Position size
        """
        risk_amount = account_size * (risk_percentage / 100)
        price_risk = abs(entry_price - stop_loss_price)
        
        if price_risk == 0:
            return 0
        
        position_size = risk_amount / price_risk
        return position_size
    
    @staticmethod
    def calculate_kelly_fraction(
        win_rate: float,
        avg_win: float,
        avg_loss: float
    ) -> float:
        """
        Calculate Kelly Criterion fraction for position sizing
        
        f* = (bp - q) / b
        where: b = odds, p = win probability, q = loss probability
        """
        if avg_loss == 0:
            return 0
        
        q = 1 - win_rate
        b = avg_win / avg_loss
        
        kelly = (b * win_rate - q) / b
        
        # Return fractional kelly (typically 25% of full kelly for safety)
        return max(0, kelly * 0.25)
