import os
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

class TradingSettings(BaseModel):
    # System & Environment
    ENV: str = os.getenv("ENV", "paper")  # "paper" or "live"
    TIMEZONE: str = "Asia/Kolkata"
    LIVE_TRADING_ENABLED: bool = os.getenv("LIVE_TRADING_ENABLED", "false").lower() == "true"
    ALLOW_SHORT_SELLING: bool = os.getenv("ALLOW_SHORT_SELLING", "false").lower() == "true"
    ORDER_STATUS_TIMEOUT_SECONDS: int = int(os.getenv("ORDER_STATUS_TIMEOUT_SECONDS", "12"))
    
    # Market Trading Hours (IST)
    PRE_MARKET_START: str = "09:00"
    MARKET_OPEN: str = "09:15"
    MARKET_CLOSE: str = "15:30"
    NO_NEW_TRADES_AFTER: str = "15:00"
    AUTO_SQUARE_OFF_TIME: str = "15:15"
    
    # Risk Management Parameters
    INITIAL_CAPITAL: float = 100000.0  # INR ₹1,00,000 for paper trading
    MAX_DAILY_LOSS_PCT: float = 2.0     # Max 2% loss per day before circuit breaker
    MAX_POSITION_SIZE_PCT: float = 15.0 # Max 15% capital per trade
    MAX_OPEN_POSITIONS: int = 3         # Max simultaneous open trades
    MIN_RISK_REWARD_RATIO: float = 1.5  # Minimum 1:1.5 Risk-Reward
    DEFAULT_STOP_LOSS_PCT: float = 1.0  # 1% default SL below entry
    DEFAULT_TARGET_PCT: float = 2.0     # 2% default Target above entry
    
    # LLM Settings
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gemini-1.5-flash")
    
    # Broker API Config (DhanHQ / Zerodha / Paper)
    BROKER_TYPE: str = os.getenv("BROKER_TYPE", "paper")  # "paper", "dhan", "kite"
    DHAN_CLIENT_ID: str = os.getenv("DHAN_CLIENT_ID", "")
    DHAN_ACCESS_TOKEN: str = os.getenv("DHAN_ACCESS_TOKEN", "")
    
    # Dashboard Server Config
    DASHBOARD_HOST: str = os.getenv("DASHBOARD_HOST", "0.0.0.0")
    DASHBOARD_PORT: int = int(os.getenv("DASHBOARD_PORT", "8000"))
    WEBSOCKET_URL: str = "ws://127.0.0.1:8000/ws/telemetry"
    DASHBOARD_USER: str = os.getenv("DASHBOARD_USER", "admin")
    DASHBOARD_PASS: str = os.getenv("DASHBOARD_PASS", "CHANGE_ME_SECURE_PASSWORD")

    def is_live_trading_permitted(self) -> bool:
        return self.ENV.lower() == "live" and self.BROKER_TYPE.lower() == "dhan" and self.LIVE_TRADING_ENABLED

settings = TradingSettings()
