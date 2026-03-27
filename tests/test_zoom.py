"""
tests/test_zoom.py

Sends a calendar invite to the HireLogic bot and waits for it to join the Zoom
meeting, detected via Zoom webhook (meeting.participant_joined event).
"""

import logging
import os
import time

import pytest

from bot.trigger import BotTrigger
from bot.webhook_listener import ZoomWebhookListener
from config.settings import config

logger = logging.getLogger(__name__)

SLA_SECONDS = 300  # bot must join within 5 minutes of meeting start


class TestZoomBotJoin:
    def test_bot_joins_within_sla(self):
        meeting_id = config.zoom.recurring_meeting_id
        bot_trigger = BotTrigger()

        # Step 1: Send calendar invite
        logger.info(f"[Test] Sending calendar invite to bot for meeting {meeting_id}")
        job = bot_trigger.send_bot()
        invited_at = job.invited_at
        meeting_start = invited_at + 300  # event is set 5 min from now

        logger.info(f"[Test] Invite sent at {time.strftime('%H:%M:%S', time.localtime(invited_at))}. "
                    f"Meeting starts at {time.strftime('%H:%M:%S', time.localtime(meeting_start))}")

        # Step 2: Set up webhook listener (starts tunnel + updates Zoom endpoint)
        listener = ZoomWebhookListener(
            zoom_account_id=config.zoom.account_id,
            zoom_client_id=config.zoom.client_id,
            zoom_client_secret=config.zoom.client_secret,
            webhook_secret=os.environ["ZOOM_WEBHOOK_SECRET"],
            meeting_id=meeting_id,
        )

        # Step 3: Wait until meeting start time
        now = time.time()
        wait_secs = max(0, meeting_start - now)
        logger.info(f"[Test] Sleeping {wait_secs:.0f}s until meeting start...")
        time.sleep(wait_secs)

        # Step 4: Wait for webhook event (bot join), up to SLA_SECONDS
        logger.info(f"[Test] Meeting start time reached. Waiting up to {SLA_SECONDS}s for bot via webhook...")
        result = listener.wait_for_bot(timeout=SLA_SECONDS, start_time=meeting_start)

        # Step 5: Assert
        if result.detected:
            secs = result.seconds_after_start or 0
            logger.info(
                f"[Test] ✅ PASS — Bot '{result.participant_name}' joined "
                f"{secs:.1f}s after meeting start"
            )
            assert secs <= SLA_SECONDS, (
                f"Bot joined {secs:.1f}s after start, exceeding SLA of {SLA_SECONDS}s"
            )
        else:
            pytest.fail(
                f"HireLogic bot did not join meeting {meeting_id} within {SLA_SECONDS}s of start time"
            )
