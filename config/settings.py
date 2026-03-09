"""
config/settings.py
Central configuration for the HireLogic bot test framework.
All values can be overridden via environment variables.
"""

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class HireLogicConfig:
    api_url: str = os.getenv("HIRELOGIC_API_URL", "https://api.hirelogic.com")
    api_key: str = os.getenv("HIRELOGIC_API_KEY", "")
    # Endpoint to trigger bot join — adjust to your actual API shape
    join_endpoint: str = "/v1/meetings/join"
    status_endpoint: str = "/v1/meetings/{meeting_id}/status"
    transcript_endpoint: str = "/v1/meetings/{meeting_id}/transcript"


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
    # How long (seconds) we allow for the bot to appear in the meeting
    bot_join_max_seconds: int = int(os.getenv("SLA_BOT_JOIN_SECONDS", "45"))

    # How long (seconds) we wait for transcript delivery after meeting ends
    transcript_delivery_max_seconds: int = int(os.getenv("SLA_TRANSCRIPT_SECONDS", "300"))

    # Word Error Rate: % at which test fails (0.0–1.0)
    wer_fail_threshold: float = float(os.getenv("SLA_WER_FAIL", "0.20"))
    wer_warn_threshold: float = float(os.getenv("SLA_WER_WARN", "0.10"))

    # Speaker attribution accuracy: % correct (0.0–1.0)
    speaker_accuracy_fail: float = float(os.getenv("SLA_SPEAKER_FAIL", "0.80"))
    speaker_accuracy_warn: float = float(os.getenv("SLA_SPEAKER_WARN", "0.90"))


@dataclass
class AudioConfig:
    """Virtual audio settings."""
    # Path to fixture WAV files
    fixtures_dir: str = os.path.join(os.path.dirname(__file__), "../fixtures/audio")
    ground_truth_dir: str = os.path.join(os.path.dirname(__file__), "../fixtures/ground_truth")

    # PulseAudio sink name for virtual mic
    pulse_sink_name: str = "hirelogic_test_sink"
    pulse_source_name: str = "hirelogic_test_sink.monitor"

    # TTS voice for generating fixtures (uses gTTS or pyttsx3)
    tts_lang: str = "en"


@dataclass
class BrowserConfig:
    """Playwright headless browser settings for hosting synthetic meetings."""
    headless: bool = os.getenv("BROWSER_HEADLESS", "true").lower() == "true"
    slow_mo: int = int(os.getenv("BROWSER_SLOW_MO", "0"))
    # Fake media flags — tells browser to use virtual mic/camera
    use_fake_ui_for_media_stream: bool = True
    # Timeout (ms) for page navigations
    navigation_timeout: int = 30_000


@dataclass
class TestConfig:
    hirelogic: HireLogicConfig = field(default_factory=HireLogicConfig)
    zoom: ZoomConfig = field(default_factory=ZoomConfig)
    google_meet: GoogleMeetConfig = field(default_factory=GoogleMeetConfig)
    teams: TeamsConfig = field(default_factory=TeamsConfig)
    sla: SLAThresholds = field(default_factory=SLAThresholds)
    audio: AudioConfig = field(default_factory=AudioConfig)
    browser: BrowserConfig = field(default_factory=BrowserConfig)

    # How often (seconds) to poll for bot status
    poll_interval: int = int(os.getenv("POLL_INTERVAL", "5"))

    # Max test duration guard (minutes) — prevents runaway tests
    max_test_duration_minutes: int = int(os.getenv("MAX_TEST_MINUTES", "30"))


# Singleton — import this everywhere
config = TestConfig()
