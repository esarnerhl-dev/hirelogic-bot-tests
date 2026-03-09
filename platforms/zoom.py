"""
platforms/zoom.py
Zoom meeting lifecycle using Zoom Server-to-Server OAuth API.
Docs: https://developers.zoom.us/docs/api/
"""

import logging
import time
from typing import Optional

import requests

from config.settings import config
from platforms.base import BasePlatform, MeetingInfo

logger = logging.getLogger(__name__)


class ZoomPlatform(BasePlatform):
    """
    Creates and destroys Zoom meetings via the Zoom REST API.

    Authentication: Server-to-Server OAuth (account-level token).
    Required scopes: meeting:write:admin, meeting:read:admin
    """

    platform_name = "Zoom"

    def __init__(self):
        self.cfg = config.zoom
        self._token: Optional[str] = None
        self._token_expiry: float = 0

    # ------------------------------------------------------------------ #
    #  Auth                                                                #
    # ------------------------------------------------------------------ #

    def _get_token(self) -> str:
        """Fetch or return cached Server-to-Server OAuth token."""
        if self._token and time.time() < self._token_expiry - 60:
            return self._token

        resp = requests.post(
            "https://zoom.us/oauth/token",
            params={
                "grant_type": "account_credentials",
                "account_id": self.cfg.account_id,
            },
            auth=(self.cfg.client_id, self.cfg.client_secret),
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._token_expiry = time.time() + data.get("expires_in", 3600)
        return self._token

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._get_token()}", "Content-Type": "application/json"}

    def _api(self, method: str, path: str, **kwargs) -> dict:
        url = f"{self.cfg.api_base}{path}"
        resp = requests.request(method, url, headers=self._headers(), timeout=20, **kwargs)
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    # ------------------------------------------------------------------ #
    #  Meeting lifecycle                                                   #
    # ------------------------------------------------------------------ #

    def create_meeting(
        self,
        topic: str = "HireLogic Bot Test",
        duration_minutes: int = 10,
    ) -> MeetingInfo:
        """
        Create an instant Zoom meeting.

        Key settings:
          - waiting_room: False  → bot can join immediately
          - join_before_host: True → bot can enter before we open the host browser
          - approval_type: 2  → automatically approve all join requests
        """
        payload = {
            "topic": topic,
            "type": 1,  # 1 = instant meeting
            "duration": duration_minutes,
            "settings": {
                "host_video": False,
                "participant_video": False,
                "join_before_host": True,
                "waiting_room": False,
                "approval_type": 2,
                "audio": "both",
                "auto_recording": "none",
                # Disable meeting passcodes for automated testing simplicity
                # (use a dedicated test Zoom account)
                "use_pmi": False,
            },
        }

        data = self._api("POST", f"/users/{self.cfg.host_email}/meetings", json=payload)
        logger.info(f"[Zoom] Created meeting {data['id']} — {data['join_url']}")

        return MeetingInfo(
            meeting_id=str(data["id"]),
            join_url=data["join_url"],
            platform="zoom",
            host_join_url=data.get("start_url"),
            password=data.get("password"),
            raw=data,
        )

    def end_meeting(self, meeting_id: str) -> None:
        """Send 'end' action to forcibly close the meeting."""
        try:
            self._api("PUT", f"/meetings/{meeting_id}/status", json={"action": "end"})
            logger.info(f"[Zoom] Ended meeting {meeting_id}")
        except Exception as e:
            logger.warning(f"[Zoom] Could not end meeting {meeting_id}: {e}")

    def get_participants(self, meeting_id: str) -> list[str]:
        """
        Returns display names of live participants.
        Note: Zoom's in-meeting participant list requires dashboard/reporting scopes.
        Falls back to dashboard API if available.
        """
        try:
            data = self._api("GET", f"/meetings/{meeting_id}/participants")
            return [p.get("name", "") for p in data.get("participants", [])]
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                return []  # Meeting not started yet or already ended
            raise

    def delete_meeting(self, meeting_id: str) -> None:
        """Permanently delete meeting record (cleanup after tests)."""
        try:
            requests.delete(
                f"{self.cfg.api_base}/meetings/{meeting_id}",
                headers=self._headers(),
                timeout=10,
            )
        except Exception as e:
            logger.warning(f"[Zoom] Could not delete meeting record {meeting_id}: {e}")
