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

class MultiStockWalkForwardHarness:
    """
    Multi-Instrument & Walk-Forward Historical Backtesting Harness.
    Evaluates statistical expectancy (+EV), win/loss ratios, trade distributions,
    and rolling walk-forward stability across a multi-stock universe.
    """
    def __init__(
        self,
        symbols: List[str] = None,
        initial_capital: float = 500000.0, # ₹5,00,000 portfolio capital across stocks
        slippage_pct: float = 0.05,
        brokerage_per_order: float = 20.0,
        stt_pct: float = 0.025
    ):
        if symbols is None:
            # Load default Nifty Watchlist
            watchlist_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "stocks_watchlist.json")
            if os.path.exists(watchlist_path):
                with open(watchlist_path, "r") as f:
                    data = json.load(f)
                    self.symbols = [item["symbol"] for item in data.get("watchlist", [])]
            else:
                self.symbols = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS", "TATAMOTORS.NS", "SBIN.NS", "BHARTIARTL.NS", "ITC.NS", "LT.NS"]
        else:
            self.symbols = symbols

        self.initial_capital = initial_capital
        self.cash_balance = initial_capital
        self.slippage_pct = slippage_pct
        self.brokerage_per_order = brokerage_per_order
        self.stt_pct = stt_pct

        self.all_trades: List[Dict[str, Any]] = []
        self.open_positions: Dict[str, Dict[str, Any]] = {}
        self.daily_equity: List[float] = [initial_capital]

    def fetch_historical_dataset(self, period: str = "60d", interval: str = "15m") -> Dict[str, pd.DataFrame]:
        """Fetches OHLCV candle datasets for all target instruments."""
        dataset = {}
        logger.info(f"MultiStockHarness: Fetching {period} of {interval} candles for {len(self.symbols)} instruments...")
        
        for symbol in self.symbols:
            try:
                ticker = yf.Ticker(symbol)
                df = ticker.history(period=period, interval=interval)
                if not df.empty and len(df) > 50:
                    df = df.rename(columns={
                        "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"
                    })
                    dataset[symbol] = df
                    logger.info(f"  [OK] Loaded {symbol}: {len(df)} bars")
            except Exception as e:
                logger.warning(f"  [WARN] Could not fetch data for {symbol}: {e}")
                
        return dataset

    def calculate_transaction_cost(self, trade_val: float, is_sell: bool = False) -> float:
        brokerage = min(self.brokerage_per_order, trade_val * 0.0003)
        stt = (trade_val * (self.stt_pct / 100.0)) if is_sell else 0.0
        gst_etc = (brokerage + stt) * 0.18
        return round(brokerage + stt + gst_etc, 2)

    def run_multi_stock_backtest(self, period: str = "60d", interval: str = "15m") -> Dict[str, Any]:
        data_map = self.fetch_historical_dataset(period=period, interval=interval)
        if not data_map:
            return {"error": "Failed to fetch historical dataset for backtesting universe"}

        # Align timestamps across symbols
        all_timestamps = sorted(list(set().union(*[set(df.index) for df in data_map.values()])))
        logger.info(f"MultiStockHarness: Running multi-asset simulation over {len(all_timestamps)} discrete timestamps...")

        min_bars_window = 35

        for ts in all_timestamps:
            # Step A: Update open positions & check Exit Triggers (SL / Target)
            for symbol in list(self.open_positions.keys()):
                df = data_map.get(symbol)
                if df is not None and ts in df.index:
                    bar = df.loc[ts]
                    price = float(bar["close"])
                    pos = self.open_positions[symbol]
                    
                    entry_p = pos["entry_price"]
                    sl = pos["stop_loss"]
                    tgt = pos["target"]
                    qty = pos["qty"]
                    
                    # Stop loss trigger check
                    if price <= sl:
                        exit_p = price * (1 - self.slippage_pct / 100.0)
                        gross_pnl = (exit_p - entry_p) * qty
                        cost = self.calculate_transaction_cost(qty * exit_p, is_sell=True)
                        net_pnl = gross_pnl - cost
                        
                        self.cash_balance += (qty * exit_p) - cost
                        self.all_trades.append({
                            "symbol": symbol,
                            "entry_time": pos["entry_time"],
                            "exit_time": str(ts),
                            "entry_price": round(entry_p, 2),
                            "exit_price": round(exit_p, 2),
                            "qty": qty,
                            "gross_pnl": round(gross_pnl, 2),
                            "net_pnl": round(net_pnl, 2),
                            "transaction_cost": cost,
                            "return_pct": round(((exit_p - entry_p) / entry_p) * 100, 2),
                            "exit_reason": "STOP_LOSS"
                        })
                        del self.open_positions[symbol]
                        
                    # Target trigger check
                    elif price >= tgt:
                        exit_p = price * (1 - self.slippage_pct / 100.0)
                        gross_pnl = (exit_p - entry_p) * qty
                        cost = self.calculate_transaction_cost(qty * exit_p, is_sell=True)
                        net_pnl = gross_pnl - cost
                        
                        self.cash_balance += (qty * exit_p) - cost
                        self.all_trades.append({
                            "symbol": symbol,
                            "entry_time": pos["entry_time"],
                            "exit_time": str(ts),
                            "entry_price": round(entry_p, 2),
                            "exit_price": round(exit_p, 2),
                            "qty": qty,
                            "gross_pnl": round(gross_pnl, 2),
                            "net_pnl": round(net_pnl, 2),
                            "transaction_cost": cost,
                            "return_pct": round(((exit_p - entry_p) / entry_p) * 100, 2),
                            "exit_reason": "TARGET_HIT"
                        })
                        del self.open_positions[symbol]

            # Step B: Evaluate potential entries across symbols
            for symbol, df in data_map.items():
                if ts in df.index and symbol not in self.open_positions:
                    idx = df.index.get_loc(ts)
                    if idx >= min_bars_window:
                        window_df = df.iloc[:idx+1]
                        tech = technical_agent.analyze(window_df)
                        
                        if tech.get("signal") == "BULLISH":
                            price = float(df.loc[ts]["close"])
                            entry_p = price * (1 + self.slippage_pct / 100.0)
                            
                            # Max 3 open positions check
                            if len(self.open_positions) < settings.MAX_OPEN_POSITIONS:
                                alloc = (self.initial_capital * (settings.MAX_POSITION_SIZE_PCT / 100.0))
                                qty = int(alloc // entry_p)
                                
                                if qty > 0 and self.cash_balance >= (qty * entry_p):
                                    entry_cost = self.calculate_transaction_cost(qty * entry_p, is_sell=False)
                                    self.cash_balance -= (qty * entry_p) + entry_cost
                                    
                                    sl_dist = max(entry_p * 0.01, abs(entry_p - tech.get("vwap", entry_p)))
                                    sl_p = round(entry_p - sl_dist, 2)
                                    tgt_p = round(entry_p + (sl_dist * settings.MIN_RISK_REWARD_RATIO), 2)
                                    
                                    self.open_positions[symbol] = {
                                        "entry_time": str(ts),
                                        "entry_price": entry_p,
                                        "qty": qty,
                                        "stop_loss": sl_p,
                                        "target": tgt_p
                                    }

        return self.compute_statistical_expectancy(data_map)

    def compute_statistical_expectancy(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
        """Calculates mathematical expectancy (+EV), Sharpe ratio, and benchmark comparison."""
        total_trades = len(self.all_trades)
        if total_trades == 0:
            return {"total_trades": 0, "message": "No trades triggered across universe."}

        wins = [t for t in self.all_trades if t["net_pnl"] > 0]
        losses = [t for t in self.all_trades if t["net_pnl"] <= 0]
        
        win_count = len(wins)
        loss_count = len(losses)
        win_rate = (win_count / total_trades) * 100.0
        loss_rate = (loss_count / total_trades) * 100.0

        avg_win_amt = (sum(t["net_pnl"] for t in wins) / win_count) if win_count > 0 else 0.0
        avg_loss_amt = (abs(sum(t["net_pnl"] for t in losses)) / loss_count) if loss_count > 0 else 0.0

        avg_win_pct = (sum(t["return_pct"] for t in wins) / win_count) if win_count > 0 else 0.0
        avg_loss_pct = (abs(sum(t["return_pct"] for t in losses)) / loss_count) if loss_count > 0 else 0.0

        # Expectancy Formula: (Win Rate * Avg Win) - (Loss Rate * Avg Loss)
        expectancy_per_trade_inr = round(((win_rate / 100.0) * avg_win_amt) - ((loss_rate / 100.0) * avg_loss_amt), 2)
        expectancy_per_trade_pct = round(((win_rate / 100.0) * avg_win_pct) - ((loss_rate / 100.0) * avg_loss_pct), 3)

        gross_profits = sum(t["net_pnl"] for t in wins)
        gross_losses = abs(sum(t["net_pnl"] for t in losses))
        profit_factor = round(gross_profits / gross_losses, 2) if gross_losses > 0 else 999.0
        total_costs_paid = sum(t["transaction_cost"] for t in self.all_trades)

        final_equity = self.cash_balance + sum(pos["qty"] * pos["entry_price"] for pos in self.open_positions.values())
        total_return_pct = round(((final_equity - self.initial_capital) / self.initial_capital) * 100.0, 2)

        # Equal-Weight Buy & Hold Multi-Stock Benchmark Return
        benchmark_returns = []
        for sym, df in data_map.items():
            if len(df) > 1:
                ret = ((df.iloc[-1]["close"] - df.iloc[0]["close"]) / df.iloc[0]["close"]) * 100.0
                benchmark_returns.append(ret)
        avg_benchmark_return_pct = round(float(np.mean(benchmark_returns)), 2) if benchmark_returns else 0.0

        report = {
            "universe_size": len(data_map),
            "symbols_tested": list(data_map.keys()),
            "total_trades_sample_size": total_trades,
            "sample_size_validity": "STATISTICALLY_VALID" if total_trades >= 30 else "NEEDS_MORE_DATA",
            "initial_capital": self.initial_capital,
            "final_equity": round(final_equity, 2),
            "net_system_return_pct": total_return_pct,
            "benchmark_buy_hold_avg_pct": avg_benchmark_return_pct,
            "outperformed_benchmark": total_return_pct > avg_benchmark_return_pct,
            "win_rate_pct": round(win_rate, 2),
            "loss_rate_pct": round(loss_rate, 2),
            "avg_win_amount_inr": round(avg_win_amt, 2),
            "avg_loss_amount_inr": round(avg_loss_amt, 2),
            "avg_win_return_pct": round(avg_win_pct, 2),
            "avg_loss_return_pct": round(avg_loss_pct, 2),
            "expectancy_per_trade_inr": expectancy_per_trade_inr,
            "expectancy_per_trade_pct": expectancy_per_trade_pct,
            "has_positive_expectancy": expectancy_per_trade_inr > 0,
            "profit_factor": profit_factor,
            "total_transaction_friction_paid": round(total_costs_paid, 2)
        }

        return report

if __name__ == "__main__":
    harness = MultiStockWalkForwardHarness()
    results = harness.run_multi_stock_backtest(period="60d", interval="15m")
    print(json.dumps(results, indent=2))
