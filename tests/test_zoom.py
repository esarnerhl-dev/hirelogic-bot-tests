"""
tests/test_zoom.py
Simplified Zoom bot join test.
Creates a calendar invite via Outlook, waits up to 5 minutes for the
HireLogic notetaker to join the recurring Zoom meeting, and reports
exactly how long it took.
"""

import time
import pytest
import logging

from bot.trigger import BotTrigger
from bot.observer import BotObserver
from config.settings import config

logger = logging.getLogger(__name__)


class TestZoomBotJoin:

    def test_bot_joins_within_sla(self):
        """
        Invite the HireLogic bot via Outlook calendar and verify it joins
        the recurring Zoom meeting within 5 minutes. Reports exact join time.
        """
        bot_trigger = BotTrigger()
        bot_observer = BotObserver()

        meeting_id = config.zoom.recurring_meeting_id
        zoom_url = config.zoom.recurring_meeting_url
        max_wait = 300  # 5 minutes
        poll_interval = 10  # check every 10 seconds

        logger.info(f"[Test] Sending calendar invite to bot for meeting {meeting_id}")

        # Step 1: Create Outlook calendar invite
        job = bot_trigger.send_bot()
        invite_sent_at = time.time()

        logger.info(f"[Test] Invite sent at {invite_sent_at:.0f}, waiting up to {max_wait}s for bot to join...")

        # Step 2: Poll Zoom participant list for up to 5 minutes
        joined = False
        elapsed = 0
        attempt = 0

        while elapsed < max_wait:
            attempt += 1
            time.sleep(poll_interval)
            elapsed = time.time() - invite_sent_at

            participants = bot_trigger.get_participants(meeting_id)
            logger.info(f"[Test] t+{elapsed:.0f}s — participants: {participants}")

            # Check if bot joined
            for name in participants:
                name_lower = name.lower()
                if any(fragment in name_lower for fragment in ["hirelogic", "notetaker", "meeting assistant", "meeting notes"]):
                    joined = True
                    logger.info(f"[Test] ✅ Bot joined after {elapsed:.1f} seconds! (name: '{name}')")
                    break

            if joined:
                break

        # Step 3: Report result
        if joined:
            print(f"\n✅ HireLogic Notetaker joined after {elapsed:.1f} seconds")
            assert True
        else:
            print(f"\n❌ HireLogic Notetaker did NOT join within {max_wait} seconds")
            pytest.fail(
                f"Bot did not join the Zoom meeting within {max_wait} seconds. "
                f"Meeting ID: {meeting_id}, Zoom URL: {zoom_url}"
            )
