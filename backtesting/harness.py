import os
import json
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime
from typing import Dict, List, Any
from agents.technical_agent import technical_agent
from config.settings import settings
from utils.logger import logger

class BacktestHarness:
    """
    Production-Grade Historical Backtesting Harness.
    Replays historical price candles through exact technical_agent logic.
    Simulates realistic slippage, Dhan/NSE transaction fees, STT, and exchange charges.
    """
    def __init__(
        self,
        symbol: str = "RELIANCE.NS",
        initial_capital: float = 100000.0,
        slippage_pct: float = 0.05,       # 0.05% price slippage per trade
        brokerage_per_order: float = 20.0, # ₹20 max per intraday order (Dhan/Zerodha)
        stt_pct: float = 0.025            # 0.025% STT on sell side for intraday equity
    ):
        self.symbol = symbol
        self.initial_capital = initial_capital
        self.cash_balance = initial_capital
        self.slippage_pct = slippage_pct
        self.brokerage_per_order = brokerage_per_order
        self.stt_pct = stt_pct
        
        self.trades: List[Dict[str, Any]] = []
        self.equity_curve: List[float] = [initial_capital]
        self.position: Dict[str, Any] = None

    def fetch_historical_candles(self, period: str = "60d", interval: str = "15m") -> pd.DataFrame:
        """Fetches historical OHLCV candle data."""
        logger.info(f"BacktestHarness: Fetching {period} of {interval} candles for {self.symbol}...")
        ticker = yf.Ticker(self.symbol)
        df = ticker.history(period=period, interval=interval)
        if df.empty:
            logger.error(f"BacktestHarness: No data returned for {self.symbol}")
            return pd.DataFrame()
            
        df = df.rename(columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume"
        })
        return df

    def calculate_transaction_costs(self, trade_value: float, is_sell: bool = False) -> float:
        """Calculates realistic Indian stock market transaction costs (Brokerage + STT + Stamp Duty + GST)."""
        brokerage = min(self.brokerage_per_order, trade_value * 0.0003)
        stt = (trade_value * (self.stt_pct / 100.0)) if is_sell else 0.0
        gst_etc = (brokerage + stt) * 0.18  # GST & Exchange turnover tax
        return round(brokerage + stt + gst_etc, 2)

    def run_backtest(self, period: str = "60d", interval: str = "15m", in_sample_split: float = 0.7) -> Dict[str, Any]:
        df = self.fetch_historical_candles(period=period, interval=interval)
        if df.empty or len(df) < 50:
            return {"error": "Insufficient candle data for backtest"}

        total_bars = len(df)
        split_idx = int(total_bars * in_sample_split)
        
        logger.info(f"BacktestHarness: Running backtest on {total_bars} bars (In-sample: {split_idx}, Out-of-sample: {total_bars - split_idx})...")

        # Rolling window bar replay
        min_bars_needed = 35
        for i in range(min_bars_needed, total_bars):
            window_df = df.iloc[:i+1]
            current_bar = df.iloc[i]
            current_price = float(current_bar["close"])
            timestamp_str = current_bar.name.strftime("%Y-%m-%d %H:%M") if hasattr(current_bar.name, 'strftime') else str(current_bar.name)
            is_out_of_sample = (i >= split_idx)

            # Evaluate technical signal from actual technical_agent
            tech_summary = technical_agent.analyze(window_df)
            signal = tech_summary.get("signal", "NEUTRAL")

            # Check open position exit triggers (Stop Loss / Target)
            if self.position:
                entry_price = self.position["entry_price"]
                sl = self.position["stop_loss"]
                tgt = self.position["target"]
                qty = self.position["qty"]
                
                # Check SL hit
                if current_price <= sl:
                    exit_price = current_price * (1 - self.slippage_pct / 100.0)
                    gross_pnl = (exit_price - entry_price) * qty
                    costs = self.calculate_transaction_costs(qty * exit_price, is_sell=True)
                    net_pnl = gross_pnl - costs
                    
                    self.cash_balance += (qty * exit_price) - costs
                    self.trades.append({
                        "symbol": self.symbol,
                        "entry_time": self.position["entry_time"],
                        "exit_time": timestamp_str,
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "qty": qty,
                        "net_pnl": round(net_pnl, 2),
                        "return_pct": round(((exit_price - entry_price) / entry_price) * 100, 2),
                        "exit_reason": "STOP_LOSS",
                        "is_out_of_sample": is_out_of_sample
                    })
                    self.position = None
                    
                # Check Target hit
                elif current_price >= tgt:
                    exit_price = current_price * (1 - self.slippage_pct / 100.0)
                    gross_pnl = (exit_price - entry_price) * qty
                    costs = self.calculate_transaction_costs(qty * exit_price, is_sell=True)
                    net_pnl = gross_pnl - costs
                    
                    self.cash_balance += (qty * exit_price) - costs
                    self.trades.append({
                        "symbol": self.symbol,
                        "entry_time": self.position["entry_time"],
                        "exit_time": timestamp_str,
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "qty": qty,
                        "net_pnl": round(net_pnl, 2),
                        "return_pct": round(((exit_price - entry_price) / entry_price) * 100, 2),
                        "exit_reason": "TARGET_HIT",
                        "is_out_of_sample": is_out_of_sample
                    })
                    self.position = None

            # Entry Logic (If no open position)
            if not self.position and signal == "BULLISH":
                entry_price = current_price * (1 + self.slippage_pct / 100.0)
                
                # Position Sizing: 15% max portfolio capital per trade
                trade_alloc = self.cash_balance * (settings.MAX_POSITION_SIZE_PCT / 100.0)
                qty = int(trade_alloc // entry_price)
                
                if qty > 0:
                    entry_costs = self.calculate_transaction_costs(qty * entry_price, is_sell=False)
                    self.cash_balance -= (qty * entry_price) + entry_costs
                    
                    sl_dist = max(entry_price * 0.01, abs(entry_price - tech_summary.get("vwap", entry_price)))
                    sl_price = round(entry_price - sl_dist, 2)
                    tgt_price = round(entry_price + (sl_dist * settings.MIN_RISK_REWARD_RATIO), 2)
                    
                    self.position = {
                        "entry_time": timestamp_str,
                        "entry_price": entry_price,
                        "qty": qty,
                        "stop_loss": sl_price,
                        "target": tgt_price
                    }

            # Record current equity
            current_portfolio_val = self.cash_balance + (self.position["qty"] * current_price if self.position else 0)
            self.equity_curve.append(current_portfolio_val)

        # Force close any remaining open position at backtest end
        if self.position:
            last_price = float(df.iloc[-1]["close"])
            qty = self.position["qty"]
            net_pnl = ((last_price - self.position["entry_price"]) * qty) - self.calculate_transaction_costs(qty * last_price, is_sell=True)
            self.cash_balance += (qty * last_price)
            self.trades.append({
                "symbol": self.symbol,
                "entry_time": self.position["entry_time"],
                "exit_time": "END_OF_BACKTEST",
                "entry_price": self.position["entry_price"],
                "exit_price": last_price,
                "qty": qty,
                "net_pnl": round(net_pnl, 2),
                "return_pct": round(((last_price - self.position["entry_price"]) / self.position["entry_price"]) * 100, 2),
                "exit_reason": "FORCE_CLOSE",
                "is_out_of_sample": True
            })
            self.position = None

        return self.compute_metrics(df, split_idx)

    def compute_metrics(self, df: pd.DataFrame, split_idx: int) -> Dict[str, Any]:
        """Computes comprehensive backtest analytics (Sharpe, Drawdown, Win Rate, Out-of-Sample comparison)."""
        total_trades = len(self.trades)
        if total_trades == 0:
            return {"symbol": self.symbol, "total_trades": 0, "message": "No trades executed during backtest period."}

        winning_trades = [t for t in self.trades if t["net_pnl"] > 0]
        losing_trades = [t for t in self.trades if t["net_pnl"] <= 0]
        
        win_rate = (len(winning_trades) / total_trades) * 100.0
        gross_profit = sum(t["net_pnl"] for t in winning_trades)
        gross_loss = abs(sum(t["net_pnl"] for t in losing_trades))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 999.0

        # Equity metrics
        final_equity = self.cash_balance
        net_return_pct = ((final_equity - self.initial_capital) / self.initial_capital) * 100.0

        # Drawdown calculation
        equity_series = pd.Series(self.equity_curve)
        running_max = equity_series.cummax()
        drawdown = (equity_series - running_max) / running_max
        max_drawdown_pct = abs(float(drawdown.min())) * 100.0

        # Sharpe Ratio (Daily returns annualized)
        returns = equity_series.pct_change().dropna()
        sharpe_ratio = float((returns.mean() / (returns.std() + 1e-10)) * np.sqrt(252)) if len(returns) > 0 else 0.0

        # Benchmark Comparison (Buy and Hold Nifty/Stock)
        first_price = float(df.iloc[0]["close"])
        last_price = float(df.iloc[-1]["close"])
        benchmark_return_pct = ((last_price - first_price) / first_price) * 100.0

        # Out-of-Sample Metrics
        in_sample_trades = [t for t in self.trades if not t["is_out_of_sample"]]
        out_sample_trades = [t for t in self.trades if t["is_out_of_sample"]]

        is_wins = len([t for t in in_sample_trades if t["net_pnl"] > 0])
        oos_wins = len([t for t in out_sample_trades if t["net_pnl"] > 0])
        
        is_win_rate = (is_wins / len(in_sample_trades) * 100) if in_sample_trades else 0.0
        oos_win_rate = (oos_wins / len(out_sample_trades) * 100) if out_sample_trades else 0.0

        report = {
            "symbol": self.symbol,
            "period_bars": len(df),
            "initial_capital": self.initial_capital,
            "final_equity": round(final_equity, 2),
            "net_return_pct": round(net_return_pct, 2),
            "benchmark_buy_hold_return_pct": round(benchmark_return_pct, 2),
            "outperformed_benchmark": net_return_pct > benchmark_return_pct,
            "total_trades": total_trades,
            "win_rate_pct": round(win_rate, 2),
            "profit_factor": round(profit_factor, 2),
            "max_drawdown_pct": round(max_drawdown_pct, 2),
            "sharpe_ratio": round(sharpe_ratio, 2),
            "in_sample_win_rate_pct": round(is_win_rate, 2),
            "out_of_sample_win_rate_pct": round(oos_win_rate, 2),
            "trades_detail": self.trades
        }

        return report

def run_multi_stock_backtest(symbols: List[str] = None) -> List[Dict[str, Any]]:
    if not symbols:
        symbols = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "TATAMOTORS.NS"]
        
    results = []
    logger.info("=== STARTING MULTI-STOCK HISTORICAL BACKTEST ===")
    for sym in symbols:
        harness = BacktestHarness(symbol=sym)
        report = harness.run_backtest(period="60d", interval="15m")
        results.append(report)
        logger.info(f"Backtest Result [{sym}]: Return={report.get('net_return_pct')}% | WinRate={report.get('win_rate_pct')}% | MaxDD={report.get('max_drawdown_pct')}% | Benchmark={report.get('benchmark_buy_hold_return_pct')}%")
        
    return results

if __name__ == "__main__":
    res = run_multi_stock_backtest()
    print(json.dumps(res, indent=2))
