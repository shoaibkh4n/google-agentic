from email.mime.text import MIMEText
from configs.config import get_settings
import logfire
import traceback
from datetime import datetime
import pytz

logger = logfire.configure()
settings = get_settings()

def convert_to_utc(start_time: datetime, timezone: str) -> datetime:
    """Convert given local time to UTC."""
    try:
        local_tz = pytz.timezone(timezone)
        local_dt = local_tz.localize(start_time)
        utc_dt = local_dt.astimezone(pytz.utc)
        return utc_dt
    except Exception as e:
        raise ValueError(f"Invalid timezone: {timezone}, Error: {e}")

    
