"""
bot/observer.py
Simple observer that watches the Zoom participant list.
Not used directly in the simplified test — participant polling
is handled inside test_zoom.py itself.
Kept for compatibility.
"""

import logging
from config.settings import config

logger = logging.getLogger(__name__)

BOT_NAME_FRAGMENTS = ["hirelogic", "notetaker", "meeting assistant", "meeting notes"]


class BotObserver:
    def __init__(self):
        self.poll_interval = 10

    def bot_joined(self, participants: list[str]) -> bool:
        for name in participants:
            if any(f in name.lower() for f in BOT_NAME_FRAGMENTS):
                return True
        return False
