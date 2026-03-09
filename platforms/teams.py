"""
platforms/teams.py
Microsoft Teams meeting lifecycle via Microsoft Graph API.
Docs: https://learn.microsoft.com/en-us/graph/api/application-post-onlinemeetings

Auth: Client Credentials (app-only) with Graph permissions:
  - OnlineMeetings.ReadWrite.All
  - OnlineMeetings.Read.All
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

from config.settings import config
from platforms.base import BasePlatform, MeetingInfo

logger = logging.getLogger(__name__)


class TeamsPlatform(BasePlatform):
    """
    Creates and destroys Teams online meetings via Microsoft Graph.

    Note: Graph app-only tokens cannot create meetings on behalf of users
    without proper consent. The test setup requires the app to be granted
    OnlineMeetings.ReadWrite.All with admin consent in Azure AD.
    """

    platform_name = "Microsoft Teams"

    def __init__(self):
        self.cfg = config.teams
        self._token: Optional[str] = None
        self._token_expiry: float = 0

    # ------------------------------------------------------------------ #
    #  Auth                                                                #
    # ------------------------------------------------------------------ #

    def _get_token(self) -> str:
        if self._token and time.time() < self._token_expiry - 60:
            return self._token

        resp = requests.post(
            f"https://login.microsoftonline.com/{self.cfg.tenant_id}/oauth2/v2.0/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.cfg.client_id,
                "client_secret": self.cfg.client_secret,
                "scope": "https://graph.microsoft.com/.default",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._token_expiry = time.time() + data.get("expires_in", 3600)
        return self._token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
        }

    def _api(self, method: str, path: str, **kwargs) -> dict:
        url = f"{self.cfg.graph_base}{path}"
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
        now = datetime.now(timezone.utc)
        end_time = now + timedelta(minutes=duration_minutes)

        payload = {
            "subject": topic,
            "startDateTime": now.isoformat(),
            "endDateTime": end_time.isoformat(),
            "lobbyBypassSettings": {
                "scope": "everyone",          # No lobby — bot joins immediately
                "isDialInBypassEnabled": True,
            },
            "allowedPresenters": "everyone",
            "isEntryExitAnnounced": False,
        }

        # Create on behalf of the configured user (app-only with user context)
        data = self._api(
            "POST",
            f"/users/{self.cfg.user_id}/onlineMeetings",
            json=payload,
        )

        join_url = data["joinUrl"]
        meeting_id = data["id"]

        logger.info(f"[Teams] Created meeting {meeting_id} — {join_url}")

        return MeetingInfo(
            meeting_id=meeting_id,
            join_url=join_url,
            platform="teams",
            host_join_url=join_url,
            raw=data,
        )

    def end_meeting(self, meeting_id: str) -> None:
        """
        Teams doesn't have a direct 'end meeting' API call.
        We delete the online meeting resource, which causes it to expire.
        In practice, for instant meetings the session ends when all participants leave.
        """
        try:
            requests.delete(
                f"{self.cfg.graph_base}/users/{self.cfg.user_id}/onlineMeetings/{meeting_id}",
                headers=self._headers(),
                timeout=15,
            )
            logger.info(f"[Teams] Deleted meeting {meeting_id}")
        except Exception as e:
            logger.warning(f"[Teams] Could not delete meeting {meeting_id}: {e}")

    def get_participants(self, meeting_id: str) -> list[str]:
        """
        Teams doesn't expose live participant lists via Graph without
        Communication Services integration. We use the call records API
        as a best-effort fallback, or the Communications API if configured.

        For bot join verification, consider using HireLogic's own status API
        (observer.py) as the primary signal instead.
        """
        try:
            # callRecords requires CallRecords.Read.All permission
            data = self._api(
                "GET",
                f"/communications/callRecords?$filter=meetingId eq '{meeting_id}'",
            )
            records = data.get("value", [])
            if not records:
                return []
            # This is a post-meeting API — during a live meeting it returns empty
            # Use HireLogic bot status API as primary join check for Teams
            return []
        except Exception as e:
            logger.debug(f"[Teams] participant list not available live: {e}")
            return []
