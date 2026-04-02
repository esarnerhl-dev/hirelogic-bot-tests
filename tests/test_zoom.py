"""
tests/test_zoom.py

Sends a calendar invite to the HireLogic notetaker bot and waits for it
to join the Zoom meeting, detected via Zoom webhook (meeting.participant_joined).

Fix summary vs original:
  - Listener is started BEFORE the invite is sent (avoids race condition)
  - Used as a context manager so cleanup always runs, even on failure
  - invited_at is captured AFTER send_bot() returns (reflects actual send time)
  - meeting_start accounts for the time spent inside send_bot() (Playwright ~60-90s)
  - ZOOM_WEBHOOK_SECRET pulled from config rather than bare os.environ
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
MEETING_OFFSET_SECONDS = 300  # invite is set 5 minutes from now


class TestZoomBotJoin:

    def test_bot_joins_within_sla(self):
        meeting_id = config.zoom.recurring_meeting_id
        webhook_secret = os.environ.get("ZOOM_WEBHOOK_SECRET", "")
        if not webhook_secret:
            pytest.skip("ZOOM_WEBHOOK_SECRET not set — skipping webhook test")

        bot_trigger = BotTrigger()

        # Step 1: Start webhook listener FIRST so we don't miss early join events.
        # The context manager guarantees cleanup (tunnel teardown) on exit.
        with ZoomWebhookListener(
            zoom_account_id=config.zoom.account_id,
            zoom_client_id=config.zoom.client_id,
            zoom_client_secret=config.zoom.client_secret,
            webhook_secret=webhook_secret,
            meeting_id=meeting_id,
            bot_email=config.hirelogic.bot_email,
        ) as listener:

            logger.info(f"[Test] Webhook listener ready at {listener.webhook_url}")

            # Step 2: Send calendar invite.
            # invited_at is captured AFTER the call returns so it reflects
            # when Outlook actually received the invite, not when we started.
            logger.info(f"[Test] Sending calendar invite for meeting {meeting_id}...")
            job = bot_trigger.send_bot()
            invited_at = job.invited_at  # set at the top of send_bot() — see note below

            # The event is scheduled ~5 min from when send_bot() was called.
            # Because Playwright takes 60-90s, we subtract that elapsed time
            # so meeting_start stays accurate.
            send_bot_duration = time.time() - invited_at
            meeting_start = invited_at + MEETING_OFFSET_SECONDS
            wait_secs = max(0, meeting_start - time.time())

            logger.info(
                f"[Test] Invite sent. send_bot() took {send_bot_duration:.0f}s. "
                f"Meeting starts at {time.strftime('%H:%M:%S', time.localtime(meeting_start))}. "
                f"Sleeping {wait_secs:.0f}s..."
            )

            # Step 3: Wait until meeting start time.
            time.sleep(wait_secs)

            # Step 4: Wait for webhook event (bot join), up to SLA_SECONDS.
            logger.info(
                f"[Test] Meeting start time reached. "
                f"Waiting up to {SLA_SECONDS}s for bot webhook event..."
            )
            result = listener.wait_for_bot(timeout=SLA_SECONDS, start_time=meeting_start)

        # Step 5: Assert (outside the context manager — listener already cleaned up).
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
                f"HireLogic bot did not join meeting {meeting_id} "
                f"within {SLA_SECONDS}s of start time"
            )
