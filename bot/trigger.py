"""
bot/trigger.py
Triggers the HireLogic notetaker bot by inviting its dedicated email address
to the Zoom meeting via the Zoom API.

No HireLogic API calls needed — the bot monitors its inbox and joins
automatically when invited from a recognized email address.
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
    """Tracks a bot session for a single meeting."""
    platform: str
    meeting_id: str
    join_url: str
    bot_email: str            # The HireLogic bot email that was invited
    invited_at: float         # Unix timestamp of when invite was sent
    status: str = "invited"   # "invited" | "joined" | "completed" | "failed"


class BotTrigger:
    """
    Invites the HireLogic notetaker bot to a Zoom meeting by adding its
    dedicated email address as a meeting invitee via the Zoom API.

    The bot joins automatically when it receives an invite from a
    recognized (whitelisted) email address — in this case ZOOM_HOST_EMAIL.
    """

    def __init__(self):
        self.zoom_cfg = config.zoom
        self.bot_email = config.hirelogic.bot_email
        self._token: Optional[str] = None
        self._token_expiry: float = 0

    def _get_zoom_token(self) -> str:
        """Get a fresh Zoom OAuth token (reuses cached token if still valid)."""
        import time
        if self._token and time.time() < self._token_expiry - 60:
            return self._token

        resp = requests.post(
            "https://zoom.us/oauth/token",
            params={
                "grant_type": "account_credentials",
                "account_id": self.zoom_cfg.account_id,
            },
            auth=(self.zoom_cfg.client_id, self.zoom_cfg.client_secret),
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._token_expiry = time.time() + data.get("expires_in", 3600)
        return self._token

    def _zoom_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_zoom_token()}",
            "Content-Type": "application/json",
        }

    def send_bot(self, meeting: MeetingInfo) -> BotJobResult:
        """
        Invite the HireLogic bot email to the Zoom meeting.

        Zoom will send a meeting invitation email to the bot's address.
        The bot recognises the host email (ZOOM_HOST_EMAIL) as a trusted
        sender and joins the meeting automatically.
        """
        import time

        # First enable registration on the meeting, then add the bot as a registrant.
        # This works on free Zoom accounts unlike invite_links which is paid-only.
        # Step 1: Update meeting to require registration (type 1 = register to attend)
        patch_resp = requests.patch(
            f"{self.zoom_cfg.api_base}/meetings/{meeting.meeting_id}",
            headers=self._zoom_headers(),
            json={"registration_type": 1},
            timeout=20,
        )
        # 204 = success, ignore other errors as meeting may already allow registration
        logger.debug(f"[BotTrigger] Meeting patch status: {patch_resp.status_code}")

        # Step 2: Add the bot email as a registrant
        resp = requests.post(
            f"{self.zoom_cfg.api_base}/meetings/{meeting.meeting_id}/registrants",
            headers=self._zoom_headers(),
            json={
                "email": self.bot_email,
                "first_name": "HireLogic",
                "last_name": "Notetaker",
            },
            timeout=20,
        )
        resp.raise_for_status()

        invited_at = time.time()
        logger.info(
            f"[BotTrigger] Invited {self.bot_email} to Zoom meeting {meeting.meeting_id}"
        )

        return BotJobResult(
            platform=meeting.platform,
            meeting_id=meeting.meeting_id,
            join_url=meeting.join_url,
            bot_email=self.bot_email,
            invited_at=invited_at,
            status="invited",
        )

    def get_participants(self, meeting_id: str) -> list[str]:
        """
        Fetch the live participant list for a Zoom meeting.
        Returns display names of everyone currently in the meeting.
        Used by the observer to detect when the bot has joined.
        """
        try:
            resp = requests.get(
                f"{self.zoom_cfg.api_base}/meetings/{meeting_id}/participants",
                headers=self._zoom_headers(),
                timeout=15,
            )
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            data = resp.json()
            return [p.get("name", "") for p in data.get("participants", [])]
        except Exception as e:
            logger.warning(f"[BotTrigger] Could not fetch participants: {e}")
            return []
