import os
import json
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime
from typing import Dict, List, Any
from agents.technical_agent import technical_agent
from agents.risk_agent import risk_agent
from config.settings import settings
from utils.logger import logger

class OutOfSampleValidationHarness:
    """
    STRICT OUT-OF-SAMPLE VALIDATION HARNESS.
    Runs Frozen Config D ONCE on a time slice strictly disjoint from all
    in-sample iteration data seen during strategy development.
    
    Full Available 730d Dataset: 2024-08-11 to 2026-08-11
    In-Sample Development Window (Touched): 2025-08-11 to 2026-08-11 (including 60d window)
    Out-of-Sample Disjoint Window (Untouched): 2024-08-11 to 2025-08-11 (Year 1)
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

    def fetch_disjoint_oos_dataset(self, interval: str = "60m") -> Dict[str, pd.DataFrame]:
        dataset = {}
        logger.info(f"OOS Harness: Fetching 730d dataset and extracting DISJOINT Year 1 slice (2024-08-11 to 2025-08-11)...")
        
        try:
            bulk_df = yf.download(self.symbols, period="730d", interval=interval, group_by='ticker', progress=False)
            for symbol in self.symbols:
                try:
                    df_sym = bulk_df[symbol].copy() if len(self.symbols) > 1 else bulk_df.copy()
                    df_sym = df_sym.dropna(subset=['Close'])
                    
                    # Slice strictly to Year 1 (2024-08-11 to 2025-08-11)
                    # Disjoint from Year 2 (2025-08-11 to 2026-08-11) used during iterative development
                    df_sym = df_sym[df_sym.index < "2025-08-11"]
                    
                    if not df_sym.empty and len(df_sym) > 35:
                        df_sym = df_sym.rename(columns={
                            "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"
                        })
                        dataset[symbol] = df_sym
                        logger.info(f"  [OK OOS] Loaded {symbol} Disjoint Slice: {len(df_sym)} bars ({df_sym.index.min()} to {df_sym.index.max()})")
                except Exception as ex_sym:
                    logger.warning(f"  [WARN OOS] Missing {symbol}: {ex_sym}")
        except Exception as e:
            logger.error(f"  [ERROR OOS] Download failed: {e}")
            
        return dataset

    def calculate_cost(self, trade_val: float, is_sell: bool = False) -> float:
        brokerage = min(self.brokerage_per_order, trade_val * 0.0003)
        stt = (trade_val * (self.stt_pct / 100.0)) if is_sell else 0.0
        gst_etc = (brokerage + stt) * 0.18
        return round(brokerage + stt + gst_etc, 2)

    def run_disjoint_oos_test(self) -> Dict[str, Any]:
        data_map = self.fetch_disjoint_oos_dataset(interval="60m")
        if not data_map:
            return {"error": "Failed to load disjoint OOS dataset"}

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

        return self.analyze_oos_results(trades, cash_balance, open_positions)

    def analyze_oos_results(self, trades: List[Dict[str, Any]], cash_balance: float, open_positions: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        total_trades = len(trades)
        if total_trades == 0:
            return {"total_trades": 0, "message": "No trades triggered in OOS period"}

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
            verdict = "STATISTICALLY_VERIFIED_OUT_OF_SAMPLE_EDGE"
        elif avg_net_exp > 0 and ci_k3_includes_zero:
            verdict = "PROMISING_OUT_OF_SAMPLE_PROFIT_WITH_UNCERTAINTY (95% CI Spans Zero)"
        else:
            verdict = "OUT_OF_SAMPLE_NEGATIVE_OR_UNVERIFIED_SIGNAL"

        return {
            "dataset_window": "2024-08-11 to 2025-08-11 (Year 1 Strictly Disjoint Out-Of-Sample)",
            "config_interval": "60m",
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

if __name__ == "__main__":
    harness = OutOfSampleValidationHarness()
    output = harness.run_disjoint_oos_test()
    print(json.dumps(output, indent=2))
