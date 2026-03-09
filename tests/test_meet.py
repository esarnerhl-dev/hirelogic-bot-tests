"""
tests/test_meet.py
Google Meet bot integration tests.
Mirrors test_zoom.py — same scenarios, different platform fixture.
"""

import os
import time
import pytest

from config.settings import config

pytestmark = pytest.mark.google_meet


class TestGoogleMeetBotJoin:

    def test_bot_joins_within_sla(
        self, google_meet_meeting, bot_trigger, bot_observer, join_checker
    ):
        platform, meeting = google_meet_meeting
        job = bot_trigger.send_bot(meeting, extra_metadata={"test": "join_sla"})
        obs = bot_observer.wait_for_join(
            job, platform=platform,
            timeout_seconds=config.sla.bot_join_max_seconds + 30
        )
        result = join_checker.check(obs)
        assert result.joined, f"Bot did not join Google Meet. Timeline: {obs.status_timeline}"
        assert result.passed, f"Join SLA failed: {result.summary()}"


class TestGoogleMeetTranscriptAccuracy:

    def test_single_speaker_accuracy(
        self, google_meet_meeting, virtual_mic, bot_trigger, bot_observer,
        join_checker, timing_checker, transcript_checker
    ):
        platform, meeting = google_meet_meeting
        fixture = "single_speaker_30s"

        job = bot_trigger.send_bot(meeting)
        obs = bot_observer.wait_for_join(job, platform=platform)
        assert join_checker.check(obs).passed, "Bot did not join Google Meet"

        audio_path = os.path.join(config.audio.fixtures_dir, f"{fixture}.wav")
        virtual_mic.play_sync(audio_path)

        meeting_end_time = time.time()
        platform.end_meeting(meeting.meeting_id)
        bot_observer.wait_for_transcript(job, obs, meeting_end_time)

        assert timing_checker.check(obs).passed, "Transcript delivery SLA failed"
        assert obs.transcript_data, "No transcript received"
        result = transcript_checker.check_accuracy(obs.transcript_data, fixture)
        assert result.passed, f"Google Meet transcript accuracy failed: {result.summary()}"

    def test_two_speaker_accuracy(
        self, google_meet_meeting, virtual_mic, bot_trigger, bot_observer,
        join_checker, timing_checker, transcript_checker
    ):
        platform, meeting = google_meet_meeting
        fixture = "two_speaker_2min"

        job = bot_trigger.send_bot(meeting)
        obs = bot_observer.wait_for_join(job, platform=platform)
        assert join_checker.check(obs).passed

        audio_path = os.path.join(config.audio.fixtures_dir, f"{fixture}.wav")
        virtual_mic.play_sync(audio_path)

        meeting_end_time = time.time()
        platform.end_meeting(meeting.meeting_id)
        bot_observer.wait_for_transcript(job, obs, meeting_end_time)

        assert obs.transcript_data, "No transcript received"
        result = transcript_checker.check_accuracy(obs.transcript_data, fixture)
        assert result.passed, f"Two-speaker accuracy failed on Google Meet: {result.summary()}"


class TestGoogleMeetEdgeCases:

    @pytest.mark.edge_case
    def test_silent_meeting_no_transcript(
        self, google_meet_meeting, virtual_mic, bot_trigger, bot_observer,
        join_checker, transcript_checker
    ):
        platform, meeting = google_meet_meeting
        job = bot_trigger.send_bot(meeting)
        obs = bot_observer.wait_for_join(job, platform=platform)
        assert join_checker.check(obs).passed

        virtual_mic.play_silence(30)

        platform.end_meeting(meeting.meeting_id)
        bot_observer.wait_for_transcript(job, obs, time.time(), timeout_seconds=120)
        result = transcript_checker.check_silence(obs.transcript_data)
        assert result.passed, f"Silence test failed on Google Meet: {result.issues}"

    @pytest.mark.edge_case
    def test_bot_joins_late(
        self, google_meet_meeting, virtual_mic, bot_trigger, bot_observer,
        join_checker, transcript_checker
    ):
        platform, meeting = google_meet_meeting
        fixture = "late_join_content"

        # Wait 30s before sending bot (simulates late trigger)
        time.sleep(30)

        job = bot_trigger.send_bot(meeting, extra_metadata={"scenario": "late_join"})
        obs = bot_observer.wait_for_join(job, platform=platform)
        assert join_checker.check(obs).passed, "Bot did not join (late join)"

        audio_path = os.path.join(config.audio.fixtures_dir, f"{fixture}.wav")
        virtual_mic.play_sync(audio_path)

        meeting_end_time = time.time()
        platform.end_meeting(meeting.meeting_id)
        bot_observer.wait_for_transcript(job, obs, meeting_end_time)

        assert obs.transcript_data, "No transcript for late join"
        result = transcript_checker.check_accuracy(obs.transcript_data, fixture)
        assert result.passed, f"Late join accuracy failed (Google Meet): {result.summary()}"
