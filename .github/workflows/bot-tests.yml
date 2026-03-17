"""
config/settings.py
Central configuration for the HireLogic bot test framework.
All values can be overridden via environment variables.
"""

import os
from dataclasses import dataclass, field


@dataclass
class HireLogicConfig:
    # The dedicated email address of the HireLogic notetaker bot.
    # This is the address you invite to Zoom meetings to trigger it to join.
    bot_email: str = os.getenv("HIRELOGIC_BOT_EMAIL", "")


@dataclass
class GmailConfig:
    # The Gmail address used as Zoom host AND that receives transcript emails.
    # Must be the same as ZOOM_HOST_EMAIL — the bot sends the transcript
    # to the meeting organizer, which is this address.
    test_address: str = os.getenv("GMAIL_TEST_ADDRESS", "")
    # Path to Google service account JSON (used in CI/GitHub Actions)
    service_account_json: str = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    # Path to OAuth token file (used in local development)
    token_path: str = os.getenv("GMAIL_TOKEN_PATH", "config/gmail_token.json")


@dataclass
class ZoomConfig:
    account_id: str = os.getenv("ZOOM_ACCOUNT_ID", "")
    client_id: str = os.getenv("ZOOM_CLIENT_ID", "")
    client_secret: str = os.getenv("ZOOM_CLIENT_SECRET", "")
    host_email: str = os.getenv("ZOOM_HOST_EMAIL", "")
    api_base: str = "https://api.zoom.us/v2"


@dataclass
class GoogleMeetConfig:
    service_account_json: str = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    calendar_id: str = os.getenv("GOOGLE_CALENDAR_ID", "")


@dataclass
class TeamsConfig:
    tenant_id: str = os.getenv("TEAMS_TENANT_ID", "")
    client_id: str = os.getenv("TEAMS_CLIENT_ID", "")
    client_secret: str = os.getenv("TEAMS_CLIENT_SECRET", "")
    user_id: str = os.getenv("TEAMS_USER_ID", "")
    graph_base: str = "https://graph.microsoft.com/v1.0"


@dataclass
class SLAThresholds:
    """Pass/fail thresholds for assertions."""
    bot_join_max_seconds: int = int(os.getenv("SLA_BOT_JOIN_SECONDS", "45"))
    transcript_delivery_max_seconds: int = int(os.getenv("SLA_TRANSCRIPT_SECONDS", "300"))
    wer_fail_threshold: float = float(os.getenv("SLA_WER_FAIL", "0.20"))
    wer_warn_threshold: float = float(os.getenv("SLA_WER_WARN", "0.10"))
    speaker_accuracy_fail: float = float(os.getenv("SLA_SPEAKER_FAIL", "0.80"))
    speaker_accuracy_warn: float = float(os.getenv("SLA_SPEAKER_WARN", "0.90"))


@dataclass
class AudioConfig:
    fixtures_dir: str = os.path.join(os.path.dirname(__file__), "../fixtures/audio")
    ground_truth_dir: str = os.path.join(os.path.dirname(__file__), "../fixtures/ground_truth")
    pulse_sink_name: str = "hirelogic_test_sink"
    pulse_source_name: str = "hirelogic_test_sink.monitor"
    tts_lang: str = "en"


@dataclass
class BrowserConfig:
    headless: bool = os.getenv("BROWSER_HEADLESS", "true").lower() == "true"
    slow_mo: int = int(os.getenv("BROWSER_SLOW_MO", "0"))
    use_fake_ui_for_media_stream: bool = True
    navigation_timeout: int = 30_000


@dataclass
class TestConfig:
    hirelogic: HireLogicConfig = field(default_factory=HireLogicConfig)
    gmail: GmailConfig = field(default_factory=GmailConfig)
    zoom: ZoomConfig = field(default_factory=ZoomConfig)
    google_meet: GoogleMeetConfig = field(default_factory=GoogleMeetConfig)
    teams: TeamsConfig = field(default_factory=TeamsConfig)
    sla: SLAThresholds = field(default_factory=SLAThresholds)
    audio: AudioConfig = field(default_factory=AudioConfig)
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    poll_interval: int = int(os.getenv("POLL_INTERVAL", "5"))
    max_test_duration_minutes: int = int(os.getenv("MAX_TEST_MINUTES", "30"))


# Singleton — import this everywhere
config = TestConfig()
