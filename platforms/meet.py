"""
platforms/meet.py
Google Meet meeting lifecycle via Google Calendar + Meet REST APIs.
Docs: https://developers.google.com/meet/api
      https://developers.google.com/calendar/api

Auth: Service Account with domain-wide delegation.
Required scopes:
  - https://www.googleapis.com/auth/calendar
  - https://www.googleapis.com/auth/meetings.space.created
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from config.settings import config
from platforms.base import BasePlatform, MeetingInfo

logger = logging.getLogger(__name__)


class GoogleMeetPlatform(BasePlatform):
    """
    Strategy: Use Google Calendar API to create an event with a Meet link.
    The conferenceData.createRequest produces a stable Meet URL.

    For participant listing, use the Google Meet REST API (v2) which provides
    real-time participant data.
    """

    platform_name = "Google Meet"

    def __init__(self):
        self.cfg = config.google_meet
        self._calendar_service = None
        self._meet_service = None
        # Maps our meeting_id → Google Calendar event_id + space_name
        self._meeting_registry: dict[str, dict] = {}

    def _get_services(self):
        """Lazy-initialize Google API clients."""
        if self._calendar_service is None:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            SCOPES = [
                "https://www.googleapis.com/auth/calendar",
                "https://www.googleapis.com/auth/meetings.space.created",
            ]
            creds = service_account.Credentials.from_service_account_file(
                self.cfg.service_account_json, scopes=SCOPES
            )
            # Impersonate the calendar owner
            delegated = creds.with_subject(self.cfg.calendar_id)
            self._calendar_service = build("calendar", "v3", credentials=delegated, cache_discovery=False)
            self._meet_service = build("meet", "v2", credentials=delegated, cache_discovery=False)

        return self._calendar_service, self._meet_service

    def create_meeting(
        self,
        topic: str = "HireLogic Bot Test",
        duration_minutes: int = 10,
    ) -> MeetingInfo:
        calendar_svc, _ = self._get_services()

        now = datetime.now(timezone.utc)
        end_time = now + timedelta(minutes=duration_minutes)

        request_id = str(uuid.uuid4())[:16]

        event_body = {
            "summary": topic,
            "start": {"dateTime": now.isoformat(), "timeZone": "UTC"},
            "end": {"dateTime": end_time.isoformat(), "timeZone": "UTC"},
            "conferenceData": {
                "createRequest": {
                    "requestId": request_id,
                    "conferenceSolutionKey": {"type": "hangoutsMeet"},
                }
            },
            # Add ourselves as attendee so meet link is fully provisioned
            "attendees": [{"email": self.cfg.calendar_id}],
        }

        event = (
            calendar_svc.events()
            .insert(
                calendarId=self.cfg.calendar_id,
                body=event_body,
                conferenceDataVersion=1,
            )
            .execute()
        )

        conf = event.get("conferenceData", {})
        meet_url = None
        for ep in conf.get("entryPoints", []):
            if ep.get("entryPointType") == "video":
                meet_url = ep["uri"]
                break

        if not meet_url:
            raise RuntimeError(f"[Google Meet] No video entry point in event: {event}")

        # Google Meet space name looks like "spaces/abc123"
        space_name = conf.get("conferenceId", "")

        meeting_id = event["id"]
        self._meeting_registry[meeting_id] = {
            "event_id": event["id"],
            "space_name": space_name,
        }

        logger.info(f"[Google Meet] Created meeting {meeting_id} — {meet_url}")

        return MeetingInfo(
            meeting_id=meeting_id,
            join_url=meet_url,
            platform="google_meet",
            host_join_url=meet_url,  # Same URL for host
            raw=event,
        )

    def end_meeting(self, meeting_id: str) -> None:
        """Delete the calendar event, which ends the Meet session."""
        try:
            calendar_svc, _ = self._get_services()
            calendar_svc.events().delete(
                calendarId=self.cfg.calendar_id,
                eventId=meeting_id,
                sendUpdates="none",
            ).execute()
            logger.info(f"[Google Meet] Deleted event {meeting_id}")
        except Exception as e:
            logger.warning(f"[Google Meet] Could not delete event {meeting_id}: {e}")

    def get_participants(self, meeting_id: str) -> list[str]:
        """
        Use Google Meet v2 API to list active participants.
        Requires the space_name from creation.
        """
        try:
            _, meet_svc = self._get_services()
            registry = self._meeting_registry.get(meeting_id, {})
            space_name = registry.get("space_name")

            if not space_name:
                logger.warning(f"[Google Meet] No space_name for {meeting_id}")
                return []

            result = (
                meet_svc.spaces()
                .participants()
                .list(parent=f"spaces/{space_name}")
                .execute()
            )
            return [
                p.get("displayName", p.get("anonymousUser", {}).get("displayName", "Unknown"))
                for p in result.get("participants", [])
            ]
        except Exception as e:
            logger.warning(f"[Google Meet] Could not fetch participants: {e}")
            return []
