"""
platforms/base.py
Abstract interface all platform implementations must satisfy.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class MeetingInfo:
    """Returned by create_meeting(). Contains everything needed to join."""
    meeting_id: str           # Platform-native ID (Zoom meeting ID, etc.)
    join_url: str             # The invite link sent to HireLogic bot
    platform: str             # "zoom" | "google_meet" | "teams"
    host_join_url: Optional[str] = None   # URL for our synthetic host browser
    password: Optional[str] = None
    raw: Optional[dict] = None            # Full API response for debugging


class BasePlatform(ABC):
    """
    Abstract meeting platform.

    Each platform must implement:
      - create_meeting()  → MeetingInfo
      - end_meeting()     → None
      - get_participants() → list[str]  (display names currently in meeting)

    The test framework calls these in order:
      1. meeting = platform.create_meeting(duration_minutes=10)
      2. ... [run test] ...
      3. platform.end_meeting(meeting.meeting_id)
    """

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Human-readable name: 'Zoom', 'Google Meet', 'Microsoft Teams'"""
        ...

    @abstractmethod
    def create_meeting(
        self,
        topic: str = "HireLogic Bot Test",
        duration_minutes: int = 10,
    ) -> MeetingInfo:
        """
        Create a meeting and return its info.
        The meeting should be immediately joinable (no waiting room by default).
        """
        ...

    @abstractmethod
    def end_meeting(self, meeting_id: str) -> None:
        """
        Forcibly end the meeting (equivalent to host clicking 'End for All').
        Called in test teardown even if the test fails.
        """
        ...

    @abstractmethod
    def get_participants(self, meeting_id: str) -> list[str]:
        """
        Return list of participant display names currently in the meeting.
        Used to verify the bot has joined (look for 'HireLogic' or 'Notetaker').
        """
        ...

    def bot_is_in_meeting(self, meeting_id: str, bot_name_fragment: str = "HireLogic") -> bool:
        """Convenience: check if any participant name contains bot_name_fragment."""
        try:
            participants = self.get_participants(meeting_id)
            return any(bot_name_fragment.lower() in p.lower() for p in participants)
        except Exception as e:
            logger.warning(f"Could not fetch participants for {meeting_id}: {e}")
            return False
