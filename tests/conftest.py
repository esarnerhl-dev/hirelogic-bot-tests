"""
tests/conftest.py
Shared pytest fixtures for the HireLogic bot test suite.

Each test gets:
  - A fresh meeting on the target platform
  - A started virtual mic
  - A BotTrigger + BotObserver
  - Auto-teardown (meeting ends even if test fails)
"""

import logging
import os
import time
from typing import Generator

import pytest

from audio.virtual_mic import VirtualMic
from assertions.join_check import JoinChecker
from assertions.timing_check import TimingChecker
from assertions.transcript_check import TranscriptChecker
from bot.observer import BotObserver
from bot.trigger import BotTrigger
from platforms.base import MeetingInfo
from platforms.zoom import ZoomPlatform
from platforms.meet import GoogleMeetPlatform
from platforms.teams import TeamsPlatform

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
#  Infrastructure fixtures                                             #
# ------------------------------------------------------------------ #

@pytest.fixture(scope="session")
def bot_trigger() -> BotTrigger:
    return BotTrigger()


@pytest.fixture(scope="session")
def bot_observer(bot_trigger) -> BotObserver:
    return BotObserver(bot_trigger)


@pytest.fixture(scope="session")
def join_checker() -> JoinChecker:
    return JoinChecker()


@pytest.fixture(scope="session")
def timing_checker() -> TimingChecker:
    return TimingChecker()


@pytest.fixture(scope="session")
def transcript_checker() -> TranscriptChecker:
    return TranscriptChecker()


@pytest.fixture(scope="function")
def virtual_mic() -> Generator[VirtualMic, None, None]:
    """Start/stop a PulseAudio virtual mic for each test."""
    mic = VirtualMic()
    mic.start()
    yield mic
    mic.stop()


# ------------------------------------------------------------------ #
#  Platform meeting fixtures — yield MeetingInfo, teardown on exit   #
# ------------------------------------------------------------------ #

@pytest.fixture(scope="function")
def zoom_meeting() -> Generator[tuple[ZoomPlatform, MeetingInfo], None, None]:
    platform = ZoomPlatform()
    meeting = platform.create_meeting(topic=f"HireLogic Test [{int(time.time())}]")
    logger.info(f"[Fixture] Zoom meeting created: {meeting.meeting_id}")
    try:
        yield platform, meeting
    finally:
        logger.info(f"[Fixture] Ending Zoom meeting {meeting.meeting_id}")
        platform.end_meeting(meeting.meeting_id)
        time.sleep(2)
        platform.delete_meeting(meeting.meeting_id)


@pytest.fixture(scope="function")
def google_meet_meeting() -> Generator[tuple[GoogleMeetPlatform, MeetingInfo], None, None]:
    platform = GoogleMeetPlatform()
    meeting = platform.create_meeting(topic=f"HireLogic Test [{int(time.time())}]")
    logger.info(f"[Fixture] Google Meet meeting created: {meeting.meeting_id}")
    try:
        yield platform, meeting
    finally:
        logger.info(f"[Fixture] Ending Google Meet {meeting.meeting_id}")
        platform.end_meeting(meeting.meeting_id)


@pytest.fixture(scope="function")
def teams_meeting() -> Generator[tuple[TeamsPlatform, MeetingInfo], None, None]:
    platform = TeamsPlatform()
    meeting = platform.create_meeting(topic=f"HireLogic Test [{int(time.time())}]")
    logger.info(f"[Fixture] Teams meeting created: {meeting.meeting_id}")
    try:
        yield platform, meeting
    finally:
        logger.info(f"[Fixture] Ending Teams meeting {meeting.meeting_id}")
        platform.end_meeting(meeting.meeting_id)


# ------------------------------------------------------------------ #
#  Helpers                                                             #
# ------------------------------------------------------------------ #

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "zoom: Zoom-specific tests")
    config.addinivalue_line("markers", "google_meet: Google Meet-specific tests")
    config.addinivalue_line("markers", "teams: Teams-specific tests")
    config.addinivalue_line("markers", "edge_case: Edge case / robustness tests")
    config.addinivalue_line("markers", "slow: Tests that take > 5 minutes")
