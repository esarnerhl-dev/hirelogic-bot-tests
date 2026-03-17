"""
config/settings.py
Central configuration for the HireLogic bot test framework.
All values are pulled from environment variables / GitHub secrets.
"""

import os
from dataclasses import dataclass, field


@dataclass
class HireLogicConfig:
    bot_email: str = os.getenv("HIRELOGIC_BOT_EMAIL", "")


@dataclass
class OutlookConfig:
    email: str = os.getenv("OUTLOOK_EMAIL", "")
    password: str = os.getenv("OUTLOOK_PASSWORD", "")


@dataclass
class ZoomConfig:
    account_id: str = os.getenv("ZOOM_ACCOUNT_ID", "")
    client_id: str = os.getenv("ZOOM_CLIENT_ID", "")
    client_secret: str = os.getenv("ZOOM_CLIENT_SECRET", "")
    host_email: str = os.getenv("ZOOM_HOST_EMAIL", "")
    api_base: str = "https://api.zoom.us/v2"
    recurring_meeting_url: str = os.getenv("ZOOM_RECURRING_URL", "")
    recurring_meeting_id: str = os.getenv("ZOOM_RECURRING_MEETING_ID", "")


@dataclass
class TestConfig:
    hirelogic: HireLogicConfig = field(default_factory=HireLogicConfig)
    outlook: OutlookConfig = field(default_factory=OutlookConfig)
    zoom: ZoomConfig = field(default_factory=ZoomConfig)


# Singleton — import this everywhere
config = TestConfig()
