import os
import json
import time
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime
from typing import Dict, List, Any
from agents.technical_agent import technical_agent
from agents.risk_agent import risk_agent
from config.settings import settings
from utils.logger import logger

class ControlledMultiPeriodHarness:
    """
    Controlled Multi-Timeframe Backtesting Harness.
    Isolates the timeframe variable by running ALL configurations across the
    EXACT SAME Controlled Historical Windows:
    
    - Config A: 15-Minute Candles (Controlled 60d)
    - Config B: 30-Minute Candles (Controlled 60d)
    - Config C: 60-Minute Candles (Controlled 60d Matched)
    - Config D: 60-Minute Candles (Full 2-Year Window)
    
    Evaluates Block Bootstrap Sensitivity across k = 2, 3, 5, 10.
    """
    def __init__(
        self,
        symbols: List[str] = None,
        initial_capital: float = 500000.0,
        slippage_pct: float = 0.05,
        brokerage_per_order: float = 20.0,
        stt_pct: float = 0.025
    ):
        if symbols is None:
            self.symbols = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "BHARTIARTL.NS", "ITC.NS", "LT.NS"]
        else:
            self.symbols = symbols

        self.initial_capital = initial_capital
        self.slippage_pct = slippage_pct
        self.brokerage_per_order = brokerage_per_order
        self.stt_pct = stt_pct

    def fetch_dataset(self, period: str = "60d", interval: str = "15m") -> Dict[str, pd.DataFrame]:
        """Fetches historical datasets using bulk download with retry fallback."""
        dataset = {}
        logger.info(f"ControlledHarness: Bulk downloading {period} of {interval} candles for {len(self.symbols)} instruments...")
        
        try:
            bulk_df = yf.download(self.symbols, period=period, interval=interval, group_by='ticker', progress=False)
            for symbol in self.symbols:
                try:
                    if len(self.symbols) == 1:
                        df_sym = bulk_df.copy()
                    else:
                        df_sym = bulk_df[symbol].copy()
                        
                    df_sym = df_sym.dropna(subset=['Close'])
                    if not df_sym.empty and len(df_sym) > 35:
                        df_sym = df_sym.rename(columns={
                            "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"
                        })
                        dataset[symbol] = df_sym
                        logger.info(f"  [OK] Loaded {symbol}: {len(df_sym)} bars")
                except Exception as ex_sym:
                    logger.warning(f"  [WARN] Missing ticker data for {symbol}: {ex_sym}")
        except Exception as e:
            logger.error(f"  [ERROR] Bulk download failed: {e}")

        # Fallback to individual fetch if bulk returned partial data
        if not dataset:
            for symbol in self.symbols:
                time.sleep(0.5)
                try:
                    t = yf.Ticker(symbol)
                    df_sym = t.history(period=period, interval=interval)
                    if not df_sym.empty and len(df_sym) > 35:
                        df_sym = df_sym.rename(columns={
                            "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"
                        })
                        dataset[symbol] = df_sym
                        logger.info(f"  [OK Fallback] Loaded {symbol}: {len(df_sym)} bars")
                except Exception as ex_single:
                    logger.warning(f"  [WARN Fallback] Failed {symbol}: {ex_single}")

        return dataset

    def calculate_cost(self, trade_val: float, is_sell: bool = False) -> float:
        brokerage = min(self.brokerage_per_order, trade_val * 0.0003)
        stt = (trade_val * (self.stt_pct / 100.0)) if is_sell else 0.0
        gst_etc = (brokerage + stt) * 0.18
        return round(brokerage + stt + gst_etc, 2)

    def run_config(self, interval: str = "15m", period: str = "60d") -> Dict[str, Any]:
        data_map = self.fetch_dataset(period=period, interval=interval)
        if not data_map:
            return {"error": f"No data for interval {interval} period {period}"}

        all_timestamps = sorted(list(set().union(*[set(df.index) for df in data_map.values()])))
        
        cash_balance = self.initial_capital
        open_positions: Dict[str, Dict[str, Any]] = {}
        trades: List[Dict[str, Any]] = []

        min_bars_needed = 35

        for ts in all_timestamps:
            # Exit check for open positions
            for symbol in list(open_positions.keys()):
                df = data_map.get(symbol)
                if df is not None and ts in df.index:
                    bar = df.loc[ts]
                    price = float(bar["close"])
                    pos = open_positions[symbol]
                    
                    entry_p = pos["entry_price"]
                    sl = pos["stop_loss"]
                    tgt = pos["target"]
                    qty = pos["qty"]

                    if price <= sl:
                        exit_p = price * (1 - self.slippage_pct / 100.0)
                        gross_pnl = (exit_p - entry_p) * qty
                        cost = self.calculate_cost(qty * exit_p, is_sell=True)
                        net_pnl = gross_pnl - cost
                        
                        cash_balance += (qty * exit_p) - cost
                        trades.append({
                            "symbol": symbol,
                            "entry_price": entry_p,
                            "exit_price": exit_p,
                            "qty": qty,
                            "gross_pnl": round(gross_pnl, 2),
                            "net_pnl": round(net_pnl, 2),
                            "transaction_cost": cost,
                            "return_pct": round(((exit_p - entry_p) / entry_p) * 100, 2),
                            "exit_reason": "STOP_LOSS"
                        })
                        del open_positions[symbol]

                    elif price >= tgt:
                        exit_p = price * (1 - self.slippage_pct / 100.0)
                        gross_pnl = (exit_p - entry_p) * qty
                        cost = self.calculate_cost(qty * exit_p, is_sell=True)
                        net_pnl = gross_pnl - cost
                        
                        cash_balance += (qty * exit_p) - cost
                        trades.append({
                            "symbol": symbol,
                            "entry_price": entry_p,
                            "exit_price": exit_p,
                            "qty": qty,
                            "gross_pnl": round(gross_pnl, 2),
                            "net_pnl": round(net_pnl, 2),
                            "transaction_cost": cost,
                            "return_pct": round(((exit_p - entry_p) / entry_p) * 100, 2),
                            "exit_reason": "TARGET_HIT"
                        })
                        del open_positions[symbol]

            # Entry check
            for symbol, df in data_map.items():
                if ts in df.index and symbol not in open_positions:
                    idx = df.index.get_loc(ts)
                    if idx >= min_bars_needed:
                        window_df = df.iloc[:idx+1]
                        tech = technical_agent.analyze(window_df)
                        
                        if tech.get("signal") == "BULLISH":
                            price = float(df.loc[ts]["close"])
                            proposal = {
                                "symbol": symbol,
                                "action": "BUY",
                                "ltp": price,
                                "suggested_stop_loss": round(price * 0.99, 2),
                                "suggested_target": round(price * 1.02, 2)
                            }
                            
                            current_portfolio_val = cash_balance + sum(pos["qty"] * pos["entry_price"] for pos in open_positions.values())
                            account_bal = {
                                "cash_balance": cash_balance,
                                "portfolio_value": current_portfolio_val,
                                "initial_capital": current_portfolio_val
                            }
                            
                            is_approved, qty, reason = risk_agent.validate_trade(
                                proposal=proposal,
                                account_balance=account_bal,
                                open_positions=list(open_positions.values()),
                                tech_summary=tech
                            )

                            if is_approved and qty > 0 and cash_balance >= (qty * price):
                                entry_p = price * (1 + self.slippage_pct / 100.0)
                                entry_cost = self.calculate_cost(qty * entry_p, is_sell=False)
                                cash_balance -= (qty * entry_p) + entry_cost
                                
                                sl_dist = max(entry_p * 0.01, abs(entry_p - tech.get("vwap", entry_p)))
                                sl_p = round(entry_p - sl_dist, 2)
                                tgt_p = round(entry_p + (sl_dist * settings.MIN_RISK_REWARD_RATIO), 2)
                                
                                open_positions[symbol] = {
                                    "symbol": symbol,
                                    "entry_price": entry_p,
                                    "qty": qty,
                                    "stop_loss": sl_p,
                                    "target": tgt_p
                                }

        return self.analyze_results(interval, period, trades, cash_balance, open_positions)

    def analyze_results(self, interval: str, period: str, trades: List[Dict[str, Any]], cash_balance: float, open_positions: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        total_trades = len(trades)
        if total_trades == 0:
            return {"config_interval": interval, "period_tested": period, "total_trades": 0, "message": "No trades triggered"}

        gross_pnls = [t["gross_pnl"] for t in trades]
        net_pnls = [t["net_pnl"] for t in trades]
        costs = [t["transaction_cost"] for t in trades]

        wins = [t for t in trades if t["net_pnl"] > 0]
        win_rate = (len(wins) / total_trades) * 100.0 if total_trades > 0 else 0.0

        avg_gross_exp = float(np.mean(gross_pnls))
        avg_net_exp = float(np.mean(net_pnls))
        avg_cost_per_trade = float(np.mean(costs))
        
        final_equity = cash_balance + sum(pos["qty"] * pos["entry_price"] for pos in open_positions.values())
        net_return_pct = ((final_equity - self.initial_capital) / self.initial_capital) * 100.0

        # Extended Block Bootstrap Sensitivity Test (k = 2, 3, 5, 10)
        bootstrap_sensitivity = {}
        for k in [2, 3, 5, 10]:
            bs_res = self.block_bootstrap(net_pnls, block_size=k, iterations=5000)
            bootstrap_sensitivity[f"block_size_{k}"] = bs_res

        ci_k3_includes_zero = bootstrap_sensitivity.get("block_size_3", {}).get("ci_95_includes_zero", True)
        if avg_net_exp > 0 and not ci_k3_includes_zero:
            verdict = "STATISTICALLY_VERIFIED_NET_EDGE"
        elif avg_net_exp > 0 and ci_k3_includes_zero:
            verdict = "PROMISING_NET_PROFIT_WITH_UNCERTAINTY (95% CI Includes Zero)"
        elif avg_gross_exp > 0 and avg_net_exp <= 0:
            verdict = "COST_DRAG_DOMINATED (Gross Positive, Net Negative)"
        else:
            verdict = "UNVERIFIED_OR_NEGATIVE_SIGNAL"

        return {
            "config_interval": interval,
            "period_tested": period,
            "total_trades_count": total_trades,
            "initial_capital": self.initial_capital,
            "final_equity": round(final_equity, 2),
            "net_return_pct": round(net_return_pct, 2),
            "win_rate_pct": round(win_rate, 2),
            "gross_expectancy_per_trade_inr": round(avg_gross_exp, 2),
            "net_expectancy_per_trade_inr": round(avg_net_exp, 2),
            "avg_transaction_friction_per_trade_inr": round(avg_cost_per_trade, 2),
            "honest_verdict": verdict,
            "bootstrap_sensitivity": bootstrap_sensitivity
        }

    def block_bootstrap(self, net_pnls: List[float], block_size: int = 3, iterations: int = 5000) -> Dict[str, Any]:
        pnl_arr = np.array(net_pnls)
        sample_size = len(pnl_arr)
        if sample_size < block_size:
            return {"ci_95_includes_zero": True, "prob_positive_pct": 0.0}

        num_blocks = int(np.ceil(sample_size / block_size))
        bootstrapped_means = []
        np.random.seed(42)

        for _ in range(iterations):
            blocks = []
            for _ in range(num_blocks):
                start = np.random.randint(0, sample_size - block_size + 1)
                blocks.extend(pnl_arr[start : start + block_size])
            bootstrapped_means.append(np.mean(blocks[:sample_size]))

        ci_lower = float(np.percentile(bootstrapped_means, 2.5))
        ci_upper = float(np.percentile(bootstrapped_means, 97.5))
        prob_pos = float(np.mean(np.array(bootstrapped_means) > 0) * 100.0)

        return {
            "mean": round(float(np.mean(bootstrapped_means)), 2),
            "ci_95_lower": round(ci_lower, 2),
            "ci_95_upper": round(ci_upper, 2),
            "ci_95_includes_zero": ci_lower <= 0 <= ci_upper,
            "prob_positive_pct": round(prob_pos, 2)
        }

def run_controlled_experiment():
    harness = ControlledMultiPeriodHarness()
    results = {}
    
    # CONTROLLED EXPERIMENT: 15m, 30m, 60m across matched 60d period + 60m 2-Year window
    logger.info("=== CONTROLLED EXPERIMENT 1: 15-MINUTE (60d) ===")
    results["Config_A_15m_60d"] = harness.run_config(interval="15m", period="60d")

    logger.info("=== CONTROLLED EXPERIMENT 2: 30-MINUTE (60d MATCHED) ===")
    results["Config_B_30m_60d"] = harness.run_config(interval="30m", period="60d")

    logger.info("=== CONTROLLED EXPERIMENT 3: 60-MINUTE (60d MATCHED) ===")
    results["Config_C_60m_60d"] = harness.run_config(interval="60m", period="60d")

    logger.info("=== CONTROLLED EXPERIMENT 4: 60-MINUTE (730d FULL 2-YEAR) ===")
    results["Config_D_60m_730d"] = harness.run_config(interval="60m", period="730d")

    return results

if __name__ == "__main__":
    output = run_controlled_experiment()
    print(json.dumps(output, indent=2))
