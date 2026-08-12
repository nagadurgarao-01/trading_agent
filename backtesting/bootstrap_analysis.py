import os
import json
import numpy as np
import pandas as pd
from typing import Dict, List, Any
from utils.logger import logger

def run_gross_vs_net_analysis(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Splits trade outcomes into Gross Expectancy (before friction) vs Net Expectancy (after friction).
    Isolates whether the problem is raw signal quality or transaction cost drag.
    """
    if not trades:
        return {"error": "No trades provided"}

    gross_pnls = np.array([t.get("gross_pnl", t.get("net_pnl", 0)) for t in trades])
    net_pnls = np.array([t.get("net_pnl", 0) for t in trades])
    costs = np.array([t.get("transaction_cost", 0) for t in trades])

    total_trades = len(trades)
    
    gross_wins = gross_pnls[gross_pnls > 0]
    gross_losses = gross_pnls[gross_pnls <= 0]
    
    gross_win_rate = (len(gross_wins) / total_trades) * 100.0 if total_trades > 0 else 0.0
    avg_gross_win = float(np.mean(gross_wins)) if len(gross_wins) > 0 else 0.0
    avg_gross_loss = float(np.abs(np.mean(gross_losses))) if len(gross_losses) > 0 else 0.0

    gross_expectancy_inr = float(np.mean(gross_pnls))
    net_expectancy_inr = float(np.mean(net_pnls))
    avg_cost_per_trade_inr = float(np.mean(costs))

    gross_profit_factor = (sum(gross_wins) / abs(sum(gross_losses))) if abs(sum(gross_losses)) > 0 else 999.0

    # Diagnosis logic
    if gross_expectancy_inr > 0 and net_expectancy_inr <= 0:
        diagnosis = "COST_DRAG_PROBLEM: Raw signal has positive gross edge (+EV), but transaction costs & slippage consume all profit."
    elif gross_expectancy_inr <= 0:
        diagnosis = "SIGNAL_QUALITY_PROBLEM: Raw technical signal itself has negative/zero edge before costs."
    else:
        diagnosis = "ROBUST_EDGE: Strategy is positive gross and net of transaction costs."

    return {
        "sample_size_trades": total_trades,
        "gross_win_rate_pct": round(gross_win_rate, 2),
        "avg_gross_win_inr": round(avg_gross_win, 2),
        "avg_gross_loss_inr": round(avg_gross_loss, 2),
        "gross_expectancy_inr": round(gross_expectancy_inr, 2),
        "net_expectancy_inr": round(net_expectancy_inr, 2),
        "avg_transaction_cost_per_trade_inr": round(avg_cost_per_trade_inr, 2),
        "gross_profit_factor": round(gross_profit_factor, 2),
        "diagnostic_verdict": diagnosis
    }

def run_block_bootstrap(trades_pnl: List[float], block_size: int = 3, iterations: int = 10000) -> Dict[str, Any]:
    """
    Performs Moving Block Resampling (Block Bootstrap) on time-ordered trade series.
    Accounts for trade autocorrelation and streak clustering.
    """
    pnl_array = np.array(trades_pnl)
    sample_size = len(pnl_array)
    if sample_size < block_size:
        return {"error": "Sample size too small for block bootstrap"}

    num_blocks = int(np.ceil(sample_size / block_size))
    bootstrapped_means = []
    
    np.random.seed(42)

    for _ in range(iterations):
        resample_blocks = []
        for _ in range(num_blocks):
            start_idx = np.random.randint(0, sample_size - block_size + 1)
            block = pnl_array[start_idx : start_idx + block_size]
            resample_blocks.extend(block)
        
        resample = np.array(resample_blocks[:sample_size])
        bootstrapped_means.append(np.mean(resample))

    exp_mean = float(np.mean(bootstrapped_means))
    exp_std = float(np.std(bootstrapped_means))
    
    ci_95_lower = float(np.percentile(bootstrapped_means, 2.5))
    ci_95_upper = float(np.percentile(bootstrapped_means, 97.5))
    prob_positive = float(np.mean(np.array(bootstrapped_means) > 0) * 100.0)

    return {
        "bootstrap_method": "Moving Block Bootstrap (Autocorrelation-Adjusted)",
        "block_size": block_size,
        "sample_size_trades": sample_size,
        "iterations": iterations,
        "observed_mean_inr": round(float(np.mean(pnl_array)), 2),
        "block_bootstrapped_mean_inr": round(exp_mean, 2),
        "block_standard_error_inr": round(exp_std, 2),
        "ci_95_lower_inr": round(ci_95_lower, 2),
        "ci_95_upper_inr": round(ci_95_upper, 2),
        "ci_95_includes_zero": ci_95_lower <= 0 <= ci_95_upper,
        "probability_of_positive_edge_pct": round(prob_positive, 2),
        "statistical_verdict": "NOT_STATISTICALLY_SIGNIFICANT (95% CI includes zero)" if (ci_95_lower <= 0 <= ci_95_upper) else "STATISTICALLY_SIGNIFICANT"
    }

if __name__ == "__main__":
    test_trades_pnl = [
        239.04, -271.91, -165.95, 207.13, 217.28, 495.86, -803.08, -401.93,
        512.40, -310.20, 189.50, 410.10, -520.00, -290.40, 680.12, -412.30,
        305.10, -220.00, -180.50, 450.60, -390.20, -150.00, 520.30, -610.20,
        140.20, -280.10, 310.40, -320.00
    ]
    res = run_block_bootstrap(test_trades_pnl, block_size=3, iterations=10000)
    print(json.dumps(res, indent=2))
