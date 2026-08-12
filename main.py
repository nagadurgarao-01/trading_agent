import os
import json
import time
import asyncio
import threading
import uvicorn
from datetime import datetime
from typing import Dict, List, Any

from config.settings import settings
from utils.logger import logger
from utils.notifier import notifier
from brokers.paper_broker import PaperBroker
from brokers.dhan_broker import DhanBroker
from agents.market_data_agent import market_data_agent
from agents.technical_agent import technical_agent
from agents.sentiment_agent import sentiment_agent
from agents.strategy_agent import strategy_agent
from agents.risk_agent import risk_agent
from agents.execution_agent import ExecutionAgent

from storage.db import db_repo
from core.lifecycle import lifecycle_engine

# Dashboard Telemetry Integration
from dashboard.backend.app import app, agent_system_ref
from dashboard.backend.telemetry import telemetry_hub

class TradingSystemOrchestrator:
    def __init__(self):
        logger.info("Initializing Autonomous Multi-Agent Trading System for Indian Stock Market...")
        db_repo.log_audit("SYSTEM_INIT", "Main", "Autonomous Multi-Agent Trading System initialized")
        
        # Load Watchlist
        watchlist_path = os.path.join(os.path.dirname(__file__), "config", "stocks_watchlist.json")
        with open(watchlist_path, "r") as f:
            data = json.load(f)
            self.watchlist = data.get("watchlist", [])
            
        # Initialize Broker & Execution Agent (DhanHQ vs Paper)
        if settings.BROKER_TYPE == "dhan" and settings.ENV == "live":
            logger.info("Connecting to LIVE DhanHQ Broker API...")
            self.broker = DhanBroker()
        else:
            logger.info(f"Running on PaperBroker (Simulated Execution - BROKER_TYPE={settings.BROKER_TYPE}, ENV={settings.ENV})")
            self.broker = PaperBroker(initial_capital=settings.INITIAL_CAPITAL)

        self.execution_agent = ExecutionAgent(self.broker)
        
        # Inject reference for dashboard APIs
        global agent_system_ref
        agent_system_ref = self

        self.is_running = True

    async def broadcast_log(self, message: str, level: str = "INFO"):
        logger.info(message)
        await telemetry_hub.broadcast("LOG_EVENT", {"message": message, "level": level})

    async def run_market_cycle(self):
        await self.broadcast_log("--- Starting Market Analysis Cycle ---", "INFO")
        
        account_bal = self.broker.get_account_balance()
        await telemetry_hub.broadcast("METRICS_UPDATE", account_bal)

        price_map = {}

        for item in self.watchlist:
            symbol = item["symbol"]
            name = item["name"]

            # 1. Fetch Latest Market Quote
            quote = market_data_agent.get_latest_quote(symbol)
            if not quote:
                continue
            
            ltp = quote["ltp"]
            price_map[symbol] = ltp

            # 2. Technical Analysis Agent (Frozen 60m Intraday Candles)
            df_candles = market_data_agent.fetch_stock_data(symbol, period="30d", interval="60m")
            tech_summary = technical_agent.analyze(df_candles)
            
            # 3. Sentiment Analysis Agent
            sentiment_summary = sentiment_agent.analyze_sentiment(symbol)

            await self.broadcast_log(
                f"{symbol} (INR {ltp}) | Tech: {tech_summary['signal']} | Sentiment: {sentiment_summary['sentiment_score']}", 
                "INFO"
            )

            # 4. Strategy & Reasoning Agent Proposal
            proposal = strategy_agent.evaluate_opportunity(quote, tech_summary, sentiment_summary)
            
            if proposal["action"] != "HOLD":
                open_positions = self.broker.get_positions()
                
                # 5. Risk Management Agent Validation (with Mistake Memory check)
                is_approved, quantity, risk_reason = risk_agent.validate_trade(
                    proposal=proposal,
                    account_balance=account_bal,
                    open_positions=open_positions,
                    tech_summary=tech_summary
                )

                if is_approved:
                    # 6. Execution Agent Order Placement
                    order = self.execution_agent.execute_trade(proposal, quantity)
                    await self.broadcast_log(
                        f"TRADE EXECUTED: [{proposal['action']}] {quantity}x {symbol} @ INR {ltp:.2f} | SL: INR {proposal['suggested_stop_loss']} | TGT: INR {proposal['suggested_target']}",
                        "CRITICAL"
                    )
                else:
                    await self.broadcast_log(
                        f"RISK REJECTED [{proposal['action']}] {symbol}: {risk_reason}",
                        "WARNING"
                    )

        # 7. Update Positions and Check Stop Loss / Target Triggers
        auto_exits = self.broker.update_market_prices(price_map)
        for exit_item in auto_exits:
            await self.broadcast_log(
                f"AUTO EXIT: {exit_item.get('symbol')} ({exit_item.get('exit_reason')}) @ INR {exit_item.get('price')}",
                "CRITICAL"
            )

        # Broadcast updated positions and telemetry to Dashboard
        updated_positions = self.broker.get_positions()
        await telemetry_hub.broadcast("POSITIONS_UPDATE", updated_positions)
        await telemetry_hub.broadcast("METRICS_UPDATE", self.broker.get_account_balance())

    async def main_loop(self):
        await self.broadcast_log("Agent Core Event Loop Started. Running intraday cycles every 10 seconds...", "INFO")
        while self.is_running:
            try:
                await self.run_market_cycle()
            except Exception as e:
                await self.broadcast_log(f"Error in market cycle: {e}", "CRITICAL")
            await asyncio.sleep(10)

def start_dashboard_server():
    uvicorn.run(app, host=settings.DASHBOARD_HOST, port=settings.DASHBOARD_PORT, log_level="warning")

if __name__ == "__main__":
    print(f"""
    ========================================================================
    AUTONOMOUS MULTI-AGENT TRADING SYSTEM (INDIAN STOCK MARKETS)
    ========================================================================
    * Target Market   : NSE / BSE (India)
    * Dashboard URL   : http://{settings.DASHBOARD_HOST}:{settings.DASHBOARD_PORT}
    * WebSocket Telemetry: ws://{settings.DASHBOARD_HOST}:{settings.DASHBOARD_PORT}/ws/telemetry
    ========================================================================
    """)
    
    # Start FastAPI Dashboard in background thread
    server_thread = threading.Thread(target=start_dashboard_server, daemon=True)
    server_thread.start()
    time.sleep(2) # Give server time to bind port

    # Start Agent System Loop
    orchestrator = TradingSystemOrchestrator()
    asyncio.run(orchestrator.main_loop())

