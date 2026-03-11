"""
bot/trigger.py
Triggers the HireLogic notetaker bot by creating a Google Calendar event
with the Zoom meeting URL in the location field and inviting the bot's
dedicated email address as an attendee.

This replicates exactly how humans trigger the bot manually:
  - Create a calendar event
  - Paste the Zoom URL in the location field
  - Invite the bot email as an attendee
"""

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
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
    bot_email: str
    invited_at: float
    calendar_event_id: Optional[str] = None
    status: str = "invited"


class BotTrigger:
    """
    Triggers the HireLogic notetaker bot by creating a Google Calendar event
    with the Zoom URL in the location field and the bot's email as an attendee.
    """

    def __init__(self):
        self.bot_email = config.hirelogic.bot_email
        self.host_email = config.zoom.host_email
        self._access_token: Optional[str] = None
        self._token_expiry: float = 0

    def _get_sa_info(self) -> dict:
        sa_json = config.gmail.service_account_json
        if not sa_json:
            raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON secret is not set")
        try:
            return json.loads(sa_json)
        except (json.JSONDecodeError, ValueError):
            with open(sa_json) as f:
                return json.load(f)

    def _get_access_token(self) -> str:
        """Get a Google OAuth2 access token from the service account JSON."""
        if self._access_token and time.time() < self._token_expiry - 60:
            return self._access_token

        sa_info = self._get_sa_info()

        import base64
        from cryptography.hazmat.primitives import serialization, hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.backends import default_backend

        now = int(time.time())
        claim_set = {
            "iss": sa_info["client_email"],
            "scope": "https://www.googleapis.com/auth/calendar",
            "aud": "https://oauth2.googleapis.com/token",
            "exp": now + 3600,
            "iat": now,
        }

        def b64encode(data):
            if isinstance(data, dict):
                data = json.dumps(data, separators=(',', ':')).encode()
            return base64.urlsafe_b64encode(data).rstrip(b'=').decode()

        header = {"alg": "RS256", "typ": "JWT"}
        signing_input = f"{b64encode(header)}.{b64encode(claim_set)}"

        private_key = serialization.load_pem_private_key(
            sa_info["private_key"].encode(),
            password=None,
            backend=default_backend()
        )
        signature = private_key.sign(
            signing_input.encode(),
            padding.PKCS1v15(),
            hashes.SHA256()
        )
        jwt_token = f"{signing_input}.{b64encode(signature)}"

        resp = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": jwt_token,
            },
            timeout=15,
        )
        resp.raise_for_status()
        token_data = resp.json()
        self._access_token = token_data["access_token"]
        self._token_expiry = time.time() + token_data.get("expires_in", 3600)
        logger.info("[BotTrigger] Got Google OAuth token successfully")
        return self._access_token

    def send_bot(self, meeting: MeetingInfo) -> BotJobResult:
        """
        Create a Google Calendar event with the Zoom URL in the location field
        and invite the HireLogic bot email as an attendee.
        """
        invited_at = time.time()
        sa_info = self._get_sa_info()
        sa_email = sa_info["client_email"]

        start = datetime.now(timezone.utc)
        end = start + timedelta(minutes=30)

        event_body = {
            "summary": "HireLogic Bot Test Meeting",
            "location": meeting.join_url,
            "description": "Automated test meeting for HireLogic notetaker bot.",
            "start": {"dateTime": start.strftime("%Y-%m-%dT%H:%M:%SZ"), "timeZone": "UTC"},
            "end": {"dateTime": end.strftime("%Y-%m-%dT%H:%M:%SZ"), "timeZone": "UTC"},
            "attendees": [
                {"email": self.host_email, "responseStatus": "accepted"},
                {"email": self.bot_email},
            ],
            "reminders": {"useDefault": False},
            "sendUpdates": "all",
        }

        token = self._get_access_token()
        resp = requests.post(
            f"https://www.googleapis.com/calendar/v3/calendars/{sa_email}/events",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            params={"sendNotifications": "true"},
            json=event_body,
            timeout=20,
        )
        if not resp.ok:
            logger.error(f"[BotTrigger] Calendar API error: {resp.status_code} {resp.text}")
        resp.raise_for_status()

        event = resp.json()
        event_id = event.get("id")
        logger.info(f"[BotTrigger] Created calendar event {event_id}, invited {self.bot_email} to Zoom meeting {meeting.meeting_id}")

        return BotJobResult(
            platform=meeting.platform,
            meeting_id=meeting.meeting_id,
            join_url=meeting.join_url,
            bot_email=self.bot_email,
            invited_at=invited_at,
            calendar_event_id=event_id,
            status="invited",
        )

    def get_participants(self, meeting_id: str) -> list[str]:
        """Fetch the live participant list for a Zoom meeting."""
        try:
            zoom_cfg = config.zoom
            resp = requests.post(
                "https://zoom.us/oauth/token",
                params={"grant_type": "account_credentials", "account_id": zoom_cfg.account_id},
                auth=(zoom_cfg.client_id, zoom_cfg.client_secret),
                timeout=15,
            )
            resp.raise_for_status()
            token = resp.json()["access_token"]

            resp = requests.get(
                f"{zoom_cfg.api_base}/meetings/{meeting_id}/participants",
                headers={"Authorization": f"Bearer {token}"},
                timeout=15,
            )
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            return [p.get("name", "") for p in resp.json().get("participants", [])]
        except Exception as e:
            logger.warning(f"[BotTrigger] Could not fetch participants: {e}")
            return []
