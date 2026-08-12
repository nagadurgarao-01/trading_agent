import pandas as pd
import numpy as np
from typing import Dict, Any
from utils.logger import logger

class TechnicalAgent:
    def __init__(self):
        logger.info("Technical Analysis Agent initialized")

    def calculate_rsi(self, series: pd.Series, period: int = 14) -> pd.Series:
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / (loss + 1e-10)
        return 100 - (100 / (1 + rs))

    def calculate_vwap(self, df: pd.DataFrame) -> pd.Series:
        tp = (df["high"] + df["low"] + df["close"]) / 3
        vwap = (tp * df["volume"]).cumsum() / (df["volume"].cumsum() + 1e-10)
        return vwap

    def calculate_supertrend(self, df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> pd.DataFrame:
        high = df["high"]
        low = df["low"]
        close = df["close"]
        
        # ATR calculation
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(period).mean()

        hl2 = (high + low) / 2
        final_upperband = hl2 + (multiplier * atr)
        final_lowerband = hl2 - (multiplier * atr)

        supertrend = [True] * len(df)
        for i in range(1, len(df)):
            if close.iloc[i] > final_upperband.iloc[i-1]:
                supertrend[i] = True
            elif close.iloc[i] < final_lowerband.iloc[i-1]:
                supertrend[i] = False
            else:
                supertrend[i] = supertrend[i-1]

        df_res = pd.DataFrame(index=df.index)
        df_res["supertrend"] = supertrend
        df_res["upper_band"] = final_upperband
        df_res["lower_band"] = final_lowerband
        return df_res

    def analyze(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Calculates indicators and produces technical breakdown."""
        if df.empty or len(df) < 30:
            return {
                "signal": "NEUTRAL",
                "reason": "Insufficient historical candles for indicators",
                "metrics": {}
            }

        df = df.copy()
        df["rsi"] = self.calculate_rsi(df["close"])
        df["vwap"] = self.calculate_vwap(df)
        df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
        df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()
        
        # MACD
        ema12 = df["close"].ewm(span=12, adjust=False).mean()
        ema26 = df["close"].ewm(span=26, adjust=False).mean()
        df["macd"] = ema12 - ema26
        df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()

        # Supertrend
        st_df = self.calculate_supertrend(df)
        df["supertrend_bullish"] = st_df["supertrend"]

        latest = df.iloc[-1]
        
        rsi_val = round(float(latest["rsi"]), 2)
        close_price = round(float(latest["close"]), 2)
        vwap_val = round(float(latest["vwap"]), 2)
        ema20_val = round(float(latest["ema20"]), 2)
        ema50_val = round(float(latest["ema50"]), 2)
        macd_val = round(float(latest["macd"]), 2)
        macd_sig = round(float(latest["macd_signal"]), 2)
        supertrend_is_bullish = bool(latest["supertrend_bullish"])

        # Bullish / Bearish scoring
        bullish_score = 0
        bearish_score = 0

        if close_price > vwap_val:
            bullish_score += 1
        else:
            bearish_score += 1

        if supertrend_is_bullish:
            bullish_score += 2
        else:
            bearish_score += 2

        if ema20_val > ema50_val:
            bullish_score += 1
        else:
            bearish_score += 1

        if macd_val > macd_sig:
            bullish_score += 1
        else:
            bearish_score += 1

        if 40 <= rsi_val <= 65:
            bullish_score += 1
        elif rsi_val > 70:
            bearish_score += 1  # Overbought caution

        if bullish_score >= 4 and bullish_score > bearish_score:
            signal = "BULLISH"
        elif bearish_score >= 4 and bearish_score > bullish_score:
            signal = "BEARISH"
        else:
            signal = "NEUTRAL"

        return {
            "signal": signal,
            "bullish_score": bullish_score,
            "bearish_score": bearish_score,
            "rsi": rsi_val,
            "close": close_price,
            "vwap": vwap_val,
            "ema20": ema20_val,
            "ema50": ema50_val,
            "macd": macd_val,
            "macd_signal": macd_sig,
            "supertrend": "BULLISH" if supertrend_is_bullish else "BEARISH"
        }

technical_agent = TechnicalAgent()
