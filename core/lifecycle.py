from datetime import datetime, time
from zoneinfo import ZoneInfo
from core.models import SystemState
from config.settings import settings
from utils.logger import logger

class TradingLifecycleEngine:
    def __init__(self):
        self.state = SystemState.STOPPED
        self.is_kill_switch_active = False

    def update_market_state(self) -> SystemState:
        if self.is_kill_switch_active:
            self.state = SystemState.STOPPED
            return self.state

        now_time = datetime.now(ZoneInfo(settings.TIMEZONE)).time()
        
        # Parse time strings (e.g. "09:15", "15:30")
        t_pre = time.fromisoformat(settings.PRE_MARKET_START)
        t_open = time.fromisoformat(settings.MARKET_OPEN)
        t_no_new = time.fromisoformat(settings.NO_NEW_TRADES_AFTER)
        t_square = time.fromisoformat(settings.AUTO_SQUARE_OFF_TIME)
        t_close = time.fromisoformat(settings.MARKET_CLOSE)

        if now_time < t_pre:
            self.state = SystemState.PRE_MARKET
        elif t_pre <= now_time < t_open:
            self.state = SystemState.PRE_MARKET
        elif t_open <= now_time < t_no_new:
            self.state = SystemState.MARKET_OPEN
        elif t_no_new <= now_time < t_square:
            self.state = SystemState.NO_NEW_ENTRIES
        elif t_square <= now_time < t_close:
            self.state = SystemState.SQUARE_OFF
        else:
            self.state = SystemState.CLOSED

        return self.state

    def can_open_new_positions(self) -> bool:
        current = self.update_market_state()
        return current == SystemState.MARKET_OPEN and not self.is_kill_switch_active

    def trigger_kill_switch(self):
        self.is_kill_switch_active = True
        self.state = SystemState.STOPPED
        logger.critical("Lifecycle Engine: KILL-SWITCH ACTIVATED. All new entries blocked.")

    def reset_kill_switch(self):
        self.is_kill_switch_active = False
        self.update_market_state()
        logger.warning("Lifecycle Engine: kill-switch reset; market-hours rules remain active.")

lifecycle_engine = TradingLifecycleEngine()
