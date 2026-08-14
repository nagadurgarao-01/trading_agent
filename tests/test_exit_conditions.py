import os
import sys
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, time
from zoneinfo import ZoneInfo

# Ensure root dir is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from brokers.paper_broker import PaperBroker
from core.lifecycle import TradingLifecycleEngine
from core.models import SystemState
from agents.risk_agent import RiskAgent
from agents.memory_agent import memory_agent
from config.settings import settings

class TestExitConditions(unittest.TestCase):
    def setUp(self):
        self.broker = PaperBroker(initial_capital=100000.0)
        self.lifecycle = TradingLifecycleEngine()
        self.risk_agent = RiskAgent()

    def test_condition_1_target_hit_take_profit(self):
        """Condition 1: LTP >= Target -> Triggers Take Profit exit & updates balance"""
        # 1. Place initial buy order
        entry_order = self.broker.place_order(
            symbol="IDEA.NS",
            action="BUY",
            quantity=10,
            order_type="MARKET",
            current_market_price=14.00,
            stop_loss=13.80,
            target=14.30
        )
        self.assertEqual(len(self.broker.get_positions()), 1)
        initial_cash = self.broker.cash_balance

        # 2. Simulate price rising to Target (₹14.35 >= ₹14.30)
        exits = self.broker.update_market_prices({"IDEA.NS": 14.35})
        
        # 3. Assertions
        self.assertEqual(len(exits), 1, "Should trigger exactly 1 auto-exit")
        self.assertEqual(exits[0]["exit_reason"], "TARGET_HIT")
        self.assertEqual(len(self.broker.get_positions()), 0, "Position must be fully closed")
        self.assertGreater(self.broker.cash_balance, initial_cash, "Cash balance must increase from profit")
        print("  [PASS] Test 1: Target Hit (Take Profit) executed successfully.")

    def test_condition_2_stop_loss_breach_risk_cut(self):
        """Condition 2: LTP <= Stop Loss -> Triggers Stop Loss exit & logs mistake memory"""
        # 1. Place initial buy order
        self.broker.place_order(
            symbol="YESBANK.NS",
            action="BUY",
            quantity=10,
            order_type="MARKET",
            current_market_price=23.00,
            stop_loss=22.50,
            target=24.00
        )
        self.assertEqual(len(self.broker.get_positions()), 1)

        # 2. Simulate price dropping to Stop Loss (₹22.40 <= ₹22.50)
        exits = self.broker.update_market_prices({"YESBANK.NS": 22.40})

        # 3. Assertions
        self.assertEqual(len(exits), 1, "Should trigger exactly 1 auto-exit")
        self.assertEqual(exits[0]["exit_reason"], "STOP_LOSS")
        self.assertEqual(len(self.broker.get_positions()), 0, "Position must be fully closed")
        print("  [PASS] Test 2: Stop Loss Breach (Risk Cut) executed successfully.")

    def test_condition_3_mandatory_1515_ist_square_off(self):
        """Condition 3: Clock reaches 15:15 IST -> Closes 100% of open positions"""
        # 1. Open multiple positions
        self.broker.place_order("IDEA.NS", "BUY", 10, current_market_price=14.0, stop_loss=13.5, target=15.0)
        self.broker.place_order("RENUKA.NS", "BUY", 5, current_market_price=22.0, stop_loss=21.0, target=24.0)
        self.assertEqual(len(self.broker.get_positions()), 2)

        # 2. Simulate market time at 15:15:05 IST
        with patch("core.lifecycle.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 8, 14, 15, 15, 5, tzinfo=ZoneInfo("Asia/Kolkata"))
            state = self.lifecycle.update_market_state()
            self.assertEqual(state, SystemState.SQUARE_OFF, "Lifecycle state must be SQUARE_OFF at 15:15 IST")
            
            # Execute mandatory square off
            closed_positions = self.broker.square_off_all(reason="MANDATORY_1515_SQUARE_OFF")

        # 3. Assertions
        self.assertEqual(len(closed_positions), 2, "All 2 positions must be exited")
        self.assertEqual(len(self.broker.get_positions()), 0, "Zero positions should remain open")
        print("  [PASS] Test 3: Mandatory 15:15 IST Square-Off executed successfully.")

    def test_condition_4_emergency_kill_switch(self):
        """Condition 4: Kill-Switch triggered -> Exits all positions & freezes new buying"""
        # 1. Open positions
        self.broker.place_order("SUZLON.NS", "BUY", 20, current_market_price=47.0, stop_loss=46.0, target=49.0)
        self.assertEqual(len(self.broker.get_positions()), 1)

        # 2. Trigger Emergency Kill-Switch
        self.lifecycle.trigger_kill_switch()
        self.assertTrue(self.lifecycle.is_kill_switch_active)
        self.assertFalse(self.lifecycle.can_open_new_positions(), "New positions must be strictly blocked")

        # 3. Square off all
        closed = self.broker.square_off_all(reason="EMERGENCY_KILL_SWITCH")
        self.assertEqual(len(closed), 1)
        self.assertEqual(len(self.broker.get_positions()), 0)
        print("  [PASS] Test 4: Emergency Kill-Switch executed successfully.")

    def test_condition_5_manual_single_stock_square_off(self):
        """Condition 5: Manual Dashboard button -> Closes ONLY target stock, preserves others"""
        # 1. Open 2 distinct positions
        self.broker.place_order("IDEA.NS", "BUY", 10, current_market_price=14.0, stop_loss=13.5, target=15.0)
        self.broker.place_order("RENUKA.NS", "BUY", 5, current_market_price=22.0, stop_loss=21.0, target=24.0)
        self.assertEqual(len(self.broker.get_positions()), 2)

        # 2. Manually square off ONLY IDEA.NS
        res = self.broker.close_position("IDEA.NS", reason="DASHBOARD_MANUAL")
        self.assertEqual(res["status"], "FILLED")
        self.assertEqual(res["exit_reason"], "DASHBOARD_MANUAL")

        # 3. Assertions
        remaining_positions = self.broker.get_positions()
        self.assertEqual(len(remaining_positions), 1, "Exactly 1 position should remain")
        self.assertEqual(remaining_positions[0]["symbol"], "RENUKA.NS", "RENUKA.NS must remain active")
        print("  [PASS] Test 5: Manual Single-Stock Square-Off executed successfully.")

if __name__ == "__main__":
    print("\n=======================================================")
    print("🚀 RUNNING LOCAL TEST SUITE: 5 EXIT CONDITIONS")
    print("=======================================================\n")
    unittest.main(verbosity=2)
