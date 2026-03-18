"""
tests/test_zoom.py
Simplified Zoom bot join test.
- Schedules a calendar invite 5 minutes from now
- Waits until the meeting start time
- Then polls for up to 5 minutes for the bot to join
- Reports exactly how long it took
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
        Invite the HireLogic bot via Outlook calendar (5 min from now),
        wait for the meeting to start, then verify the bot joins within 5 minutes.
        """
        bot_trigger = BotTrigger()
        meeting_id = config.zoom.recurring_meeting_id
        zoom_url = config.zoom.recurring_meeting_url
        max_wait = 300  # 5 minutes after meeting start
        poll_interval = 10

        logger.info(f"[Test] Sending calendar invite to bot for meeting {meeting_id}")

        # Step 1: Create Outlook calendar invite (5 min from now)
        job = bot_trigger.send_bot()
        invite_sent_at = time.time()
        meeting_start_at = invite_sent_at + (5 * 60)  # 5 minutes from now

        logger.info(f"[Test] Invite sent. Meeting starts at t+5min. Waiting until then...")

        # Step 2: Wait until meeting start time
        wait_until_start = meeting_start_at - time.time()
        if wait_until_start > 0:
            logger.info(f"[Test] Sleeping {wait_until_start:.0f}s until meeting start time...")
            time.sleep(wait_until_start)

        logger.info(f"[Test] Meeting start time reached. Now polling for bot to join (up to {max_wait}s)...")

        # Step 3: Poll Zoom participant list for up to 5 minutes
        joined = False
        elapsed_since_start = 0
        attempt = 0

        while elapsed_since_start < max_wait:
            attempt += 1
            time.sleep(poll_interval)
            elapsed_since_start = time.time() - meeting_start_at
            elapsed_since_invite = time.time() - invite_sent_at

            participants = bot_trigger.get_participants(meeting_id)
            logger.info(f"[Test] t+{elapsed_since_start:.0f}s after start ({elapsed_since_invite:.0f}s after invite) — participants: {participants}")

            for name in participants:
                name_lower = name.lower()
                if any(fragment in name_lower for fragment in ["hirelogic", "notetaker", "meeting assistant", "meeting notes"]):
                    joined = True
                    logger.info(f"[Test] ✅ Bot joined {elapsed_since_start:.1f}s after meeting start ({elapsed_since_invite:.1f}s after invite)! Name: '{name}'")
                    break

            if joined:
                break

        # Step 4: Report result
        if joined:
            print(f"\n✅ HireLogic Notetaker joined {elapsed_since_start:.1f}s after meeting start ({elapsed_since_invite:.1f}s after invite was sent)")
            assert True
        else:
            print(f"\n❌ HireLogic Notetaker did NOT join within {max_wait}s of meeting start")
            pytest.fail(
                f"Bot did not join within {max_wait}s of meeting start. "
                f"Meeting ID: {meeting_id}, Zoom URL: {zoom_url}"
            )
