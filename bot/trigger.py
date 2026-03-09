"""
bot/trigger.py
Sends a meeting invite link to the HireLogic API to trigger the notetaker bot.
Adjust the request shape (fields, headers, auth method) to match your actual API.
"""

import logging
from dataclasses import dataclass
from typing import Optional

import requests

from config.settings import config
from platforms.base import MeetingInfo

logger = logging.getLogger(__name__)


@dataclass
class BotJobResult:
    """Returned after triggering the bot."""
    job_id: str               # HireLogic's internal ID for this bot session
    platform: str
    meeting_id: str           # Platform-native meeting ID
    join_url: str
    status: str               # "pending" | "joining" | "in_meeting" | "completed" | "failed"
    raw: Optional[dict] = None


class BotTrigger:
    """
    Calls the HireLogic API to dispatch the notetaker bot to a meeting.

    ⚠️  Adjust the endpoint paths, request body shape, and auth headers
        to match your actual HireLogic API contract.
    """

    def __init__(self):
        self.cfg = config.hirelogic
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.cfg.api_key}",
            "Content-Type": "application/json",
            "X-Test-Mode": "true",  # Signal to HireLogic that this is an automated test
        })

    def send_bot(
        self,
        meeting: MeetingInfo,
        bot_name: str = "HireLogic Notetaker",
        extra_metadata: Optional[dict] = None,
    ) -> BotJobResult:
        """
        Dispatch the bot to the given meeting.

        The bot receives the join_url (invite link) and joins as a participant.
        Returns a BotJobResult with a job_id you can poll for status.
        """
        payload = {
            "meeting_url": meeting.join_url,
            "platform": meeting.platform,
            "bot_name": bot_name,
            "meeting_id": meeting.meeting_id,
            # Optional: attach metadata for correlation in reports
            "metadata": {
                "test_run": True,
                "platform": meeting.platform,
                **(extra_metadata or {}),
            },
        }

        # Include password if the platform requires it
        if meeting.password:
            payload["meeting_password"] = meeting.password

        logger.info(f"[Bot] Sending bot to {meeting.platform} meeting {meeting.meeting_id}")
        logger.debug(f"[Bot] POST {self.cfg.api_url}{self.cfg.join_endpoint} payload={payload}")

        resp = self.session.post(
            f"{self.cfg.api_url}{self.cfg.join_endpoint}",
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        result = BotJobResult(
            job_id=data.get("job_id") or data.get("id") or data.get("session_id", ""),
            platform=meeting.platform,
            meeting_id=meeting.meeting_id,
            join_url=meeting.join_url,
            status=data.get("status", "pending"),
            raw=data,
        )

        logger.info(f"[Bot] Job created: {result.job_id} (status={result.status})")
        return result

    def get_status(self, job_id: str, meeting_id: str) -> dict:
        """
        Fetch current bot job status.
        Returns a dict with at minimum: {"status": "...", "job_id": "..."}
        Expected statuses: pending | joining | in_meeting | recording | completed | failed
        """
        endpoint = self.cfg.status_endpoint.format(meeting_id=meeting_id)
        resp = self.session.get(
            f"{self.cfg.api_url}{endpoint}",
            params={"job_id": job_id},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def get_transcript(self, job_id: str, meeting_id: str) -> Optional[dict]:
        """
        Fetch the transcript for a completed meeting.

        Expected response shape:
        {
          "transcript": [
            {
              "speaker": "John Smith",
              "text": "Hello everyone...",
              "start_time": 0.0,
              "end_time": 4.2
            },
            ...
          ],
          "full_text": "Hello everyone...",
          "word_count": 142,
          "duration_seconds": 180
        }
        Returns None if transcript is not yet ready.
        """
        endpoint = self.cfg.transcript_endpoint.format(meeting_id=meeting_id)
        try:
            resp = self.session.get(
                f"{self.cfg.api_url}{endpoint}",
                params={"job_id": job_id},
                timeout=15,
            )
            if resp.status_code == 404:
                return None  # Not ready yet
            resp.raise_for_status()
            return resp.json()
        except requests.HTTPError as e:
            if e.response.status_code in (404, 202):
                return None  # Still processing
            raise
