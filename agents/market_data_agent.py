import pandas as pd
import numpy as np
import yfinance as yf
from typing import Dict, Any, Optional
from utils.logger import logger

class MarketDataAgent:
    def __init__(self):
        logger.info("Market Data Agent initialized")

    def fetch_stock_data(self, symbol: str, period: str = "5d", interval: str = "15m") -> pd.DataFrame:
        """Fetches OHLCV candlestick data for an Indian stock symbol (e.g. RELIANCE.NS)."""
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period, interval=interval)
            if df.empty:
                logger.warning(f"MarketDataAgent: Empty data fetched for {symbol}")
                return pd.DataFrame()
            
            # Clean dataframe column names
            df = df.rename(columns={
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume"
            })
            return df
        except Exception as e:
            logger.error(f"MarketDataAgent: Error fetching data for {symbol}: {e}")
            return pd.DataFrame()

    def get_latest_quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Retrieves latest price tick and daily OHLC for a stock."""
        df = self.fetch_stock_data(symbol, period="2d", interval="1m")
        if df.empty:
            return None
        
        latest_row = df.iloc[-1]
        prev_close = df.iloc[0]["close"]
        current_price = round(float(latest_row["close"]), 2)
        change_pct = round(((current_price - prev_close) / prev_close) * 100, 2)
        
        return {
            "symbol": symbol,
            "ltp": current_price,
            "open": round(float(latest_row["open"]), 2),
            "high": round(float(latest_row["high"]), 2),
            "low": round(float(latest_row["low"]), 2),
            "close": current_price,
            "volume": int(latest_row["volume"]),
            "change_pct": change_pct,
            "timestamp": latest_row.name.strftime("%Y-%m-%d %H:%M:%S") if hasattr(latest_row.name, 'strftime') else str(latest_row.name)
        }

market_data_agent = MarketDataAgent()
