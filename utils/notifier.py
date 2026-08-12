from utils.logger import logger

class NotificationManager:
    def __init__(self):
        logger.info("Notification Manager initialized (Console + Telemetry Log)")
        
    def send_alert(self, title: str, message: str, level: str = "INFO"):
        prefix = "🚨" if level == "CRITICAL" else ("⚠️" if level == "WARNING" else "📢")
        formatted = f"{prefix} [{title}] {message}"
        if level == "CRITICAL":
            logger.error(formatted)
        elif level == "WARNING":
            logger.warning(formatted)
        else:
            logger.info(formatted)

notifier = NotificationManager()
