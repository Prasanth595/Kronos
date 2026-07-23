"""
Integration module for real market data sources
Supports: Crypto, Stocks, Commodities
"""

import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)

class DataSource(ABC):
    """Abstract base class for data sources"""
    
    @abstractmethod
    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        """Fetch OHLCV data"""
        pass
    
    @abstractmethod
    def fetch_latest_price(self, symbol: str) -> float:
        """Fetch latest price"""
        pass


class CryptoDataSource(DataSource):
    """Cryptocurrency data from various exchanges"""
    
    def __init__(self, source: str = 'binance'):
        """
        Initialize crypto data source
        
        Args:
            source: 'binance', 'kraken', 'coinbase', 'bybit'
        """
        self.source = source.lower()
        self.base_url = self._get_base_url()
    
    def _get_base_url(self) -> str:
        """Get API base URL for exchange"""
        urls = {
            'binance': 'https://api.binance.com',
            'kraken': 'https://api.kraken.com',
            'coinbase': 'https://api.coinbase.com',
            'bybit': 'https://api.bybit.com',
        }
        return urls.get(self.source, 'https://api.binance.com')
    
    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 500) -> pd.DataFrame:
        """
        Fetch cryptocurrency OHLCV data
        
        Args:
            symbol: e.g., 'BTCUSDT', 'BTC/USDT'
            timeframe: '1m', '5m', '1h', '4h', '1d'
            limit: Number of candles to fetch
            
        Returns:
            DataFrame with OHLCV data
        """
        try:
            symbol = symbol.replace('/', '').upper()
            
            if self.source == 'binance':
                return self._fetch_binance(symbol, timeframe, limit)
            elif self.source == 'kraken':
                return self._fetch_kraken(symbol, timeframe, limit)
            else:
                logger.warning(f"Source {self.source} not implemented, using Binance")
                return self._fetch_binance(symbol, timeframe, limit)
                
        except Exception as e:
            logger.error(f"Error fetching data: {e}")
            return pd.DataFrame()
    
    def _fetch_binance(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        """Fetch from Binance API"""
        url = f"{self.base_url}/api/v3/klines"
        params = {
            'symbol': symbol,
            'interval': timeframe,
            'limit': limit
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        df = pd.DataFrame(data, columns=[
            'open_time', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_asset_volume', 'trades', 'taker_buy_base',
            'taker_buy_quote', 'ignore'
        ])
        
        df['timestamp'] = pd.to_datetime(df['open_time'], unit='ms')
        df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']].astype(float)
        
        return df
    
    def _fetch_kraken(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        """Fetch from Kraken API"""
        url = f"{self.base_url}/0/public/OHLC"
        
        # Map timeframes to Kraken format
        tf_map = {'1m': 1, '5m': 5, '15m': 15, '30m': 30, '1h': 60, '4h': 240, '1d': 1440}
        
        params = {
            'pair': symbol,
            'interval': tf_map.get(timeframe, 240),
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        if data['error']:
            raise Exception(f"Kraken API error: {data['error']}")
        
        ohlc_data = list(data['result'].values())[0]
        df = pd.DataFrame(ohlc_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'vwap', 'volume', 'count'])
        
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
        df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']].astype(float)
        
        return df[-limit:]
    
    def fetch_latest_price(self, symbol: str) -> float:
        """Fetch latest price"""
        try:
            symbol = symbol.replace('/', '').upper()
            url = f"{self.base_url}/api/v3/ticker/price"
            response = requests.get(url, params={'symbol': symbol}, timeout=10)
            response.raise_for_status()
            return float(response.json()['price'])
        except Exception as e:
            logger.error(f"Error fetching latest price: {e}")
            return 0.0


class StockDataSource(DataSource):
    """Stock market data"""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize stock data source
        
        Args:
            api_key: API key for premium services (optional)
        """
        self.api_key = api_key
    
    def fetch_ohlcv(self, symbol: str, timeframe: str = '1d', limit: int = 500) -> pd.DataFrame:
        """
        Fetch stock OHLCV data (using yfinance)
        
        Args:
            symbol: e.g., 'AAPL', 'GOOGL'
            timeframe: '1m', '5m', '1h', '1d', '1wk', '1mo'
            limit: Number of candles
            
        Returns:
            DataFrame with OHLCV data
        """
        try:
            import yfinance as yf
            
            # Map timeframes
            tf_map = {
                '1m': '1m', '5m': '5m', '15m': '15m', '30m': '30m',
                '1h': '1h', '1d': '1d', '1w': '1wk', '1mo': '1mo'
            }
            
            ticker = yf.Ticker(symbol)
            period = self._get_period(limit, timeframe)
            
            df = ticker.history(period=period, interval=tf_map.get(timeframe, '1d'))
            df = df.reset_index()
            df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'dividends', 'stock_splits']
            df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
            
            return df.tail(limit)
            
        except ImportError:
            logger.error("yfinance not installed. Install with: pip install yfinance")
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"Error fetching stock data: {e}")
            return pd.DataFrame()
    
    def fetch_latest_price(self, symbol: str) -> float:
        """Fetch latest stock price"""
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            return ticker.info.get('currentPrice', 0.0)
        except Exception as e:
            logger.error(f"Error fetching latest price: {e}")
            return 0.0
    
    def _get_period(self, limit: int, timeframe: str) -> str:
        """Convert limit and timeframe to period string"""
        if timeframe in ['1m', '5m', '15m', '30m', '1h']:
            days = (limit * int(timeframe.replace('m', '').replace('h', '')) // 60) // 24 + 1
            return f"{days}d"
        elif timeframe == '1d':
            return f"{limit}d"
        elif timeframe == '1w':
            return f"{limit * 7}d"
        else:
            return f"{limit}d"


class ForexDataSource(DataSource):
    """Foreign exchange (Forex) data"""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Forex data source
        
        Args:
            api_key: API key for service (optional)
        """
        self.api_key = api_key
        self.base_url = 'https://api.exchangerate-api.com'
    
    def fetch_ohlcv(self, symbol: str, timeframe: str = '1d', limit: int = 500) -> pd.DataFrame:
        """
        Fetch Forex OHLCV data
        
        Args:
            symbol: e.g., 'EURUSD', 'EUR/USD'
            timeframe: '1m', '5m', '1h', '1d'
            limit: Number of candles
            
        Returns:
            DataFrame with OHLCV data
        """
        # Simplified implementation - use dedicated Forex API in production
        logger.warning("Forex data fetching is simplified. Use a dedicated Forex API in production.")
        return pd.DataFrame()
    
    def fetch_latest_price(self, symbol: str) -> float:
        """Fetch latest Forex rate"""
        try:
            pair = symbol.replace('/', '')
            from_currency = pair[:3]
            to_currency = pair[3:]
            
            url = f"{self.base_url}/v4/latest/{from_currency}"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            return data['rates'].get(to_currency, 0.0)
        except Exception as e:
            logger.error(f"Error fetching Forex price: {e}")
            return 0.0


class DataAggregator:
    """Aggregate data from multiple sources"""
    
    def __init__(self):
        self.sources: Dict[str, DataSource] = {}
        self.cache = {}
    
    def register_source(self, name: str, source: DataSource):
        """Register a data source"""
        self.sources[name] = source
    
    def fetch_data(self, 
                   symbol: str,
                   timeframe: str = '1h',
                   limit: int = 200,
                   source: str = 'auto') -> pd.DataFrame:
        """
        Fetch data from registered source
        
        Args:
            symbol: Trading symbol
            timeframe: Time interval
            limit: Number of candles
            source: Which source to use ('auto' = detect from symbol)
            
        Returns:
            DataFrame with OHLCV data
        """
        cache_key = f"{symbol}_{timeframe}_{limit}"
        
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        # Auto-detect source from symbol
        if source == 'auto':
            source = self._detect_source(symbol)
        
        if source not in self.sources:
            logger.error(f"Source {source} not registered")
            return pd.DataFrame()
        
        data = self.sources[source].fetch_ohlcv(symbol, timeframe, limit)
        
        # Cache result
        self.cache[cache_key] = data
        
        return data
    
    def _detect_source(self, symbol: str) -> str:
        """Detect data source from symbol"""
        if '/' in symbol:
            parts = symbol.split('/')
            if parts[1] in ['USDT', 'BUSD', 'USDC']:
                return 'crypto'
            else:
                return 'forex'
        else:
            return 'stock'


# Helper functions for Flask integration

def get_data_aggregator() -> DataAggregator:
    """Get configured data aggregator"""
    aggregator = DataAggregator()
    
    # Register all sources
    aggregator.register_source('crypto', CryptoDataSource('binance'))
    aggregator.register_source('stock', StockDataSource())
    aggregator.register_source('forex', ForexDataSource())
    
    return aggregator


def fetch_market_data(symbol: str, 
                     timeframe: str = '1h',
                     lookback: int = 200) -> Optional[pd.DataFrame]:
    """
    Fetch market data for Kronos prediction
    
    Args:
        symbol: Trading symbol
        timeframe: Time interval
        lookback: Number of candles
        
    Returns:
        DataFrame with OHLCV data or None if error
    """
    try:
        aggregator = get_data_aggregator()
        data = aggregator.fetch_data(symbol, timeframe, lookback)
        
        if data.empty:
            logger.warning(f"No data fetched for {symbol}")
            return None
        
        # Ensure required columns
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        if not all(col in data.columns for col in required_cols):
            logger.error(f"Missing required columns. Got: {data.columns.tolist()}")
            return None
        
        return data
        
    except Exception as e:
        logger.error(f"Error fetching market data: {e}")
        return None


if __name__ == '__main__':
    # Example usage
    logging.basicConfig(level=logging.INFO)
    
    # Crypto example
    crypto = CryptoDataSource('binance')
    btc_data = crypto.fetch_ohlcv('BTC/USDT', '1h', 100)
    print(f"BTC Data shape: {btc_data.shape}")
    print(btc_data.head())
    
    # Stock example
    stock = StockDataSource()
    aapl_data = stock.fetch_ohlcv('AAPL', '1d', 100)
    print(f"\nAAPL Data shape: {aapl_data.shape}")
    print(aapl_data.head())
