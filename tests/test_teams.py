"""
tests/test_teams.py
Microsoft Teams bot integration tests.
"""

import os
import time
import pytest

from config.settings import config

pytestmark = pytest.mark.teams


class TestTeamsBotJoin:

    def test_bot_joins_within_sla(
        self, teams_meeting, bot_trigger, bot_observer, join_checker
    ):
        """
        Teams lobby bypass must be enabled (configured in create_meeting).
        Bot should join without being held in lobby.
        """
        platform, meeting = teams_meeting
        job = bot_trigger.send_bot(meeting, extra_metadata={"test": "join_sla"})
        obs = bot_observer.wait_for_join(
            job,
            # Note: Teams doesn't expose live participant list via Graph,
            # so we rely solely on the HireLogic status API here
            platform=None,
            timeout_seconds=config.sla.bot_join_max_seconds + 30,
        )
        result = join_checker.check(obs)
        assert result.joined, f"Bot did not join Teams. Timeline: {obs.status_timeline}"
        assert result.passed, f"Teams join SLA failed: {result.summary()}"


class TestTeamsTranscriptAccuracy:

    def test_single_speaker_accuracy(
        self, teams_meeting, virtual_mic, bot_trigger, bot_observer,
        join_checker, timing_checker, transcript_checker
    ):
        platform, meeting = teams_meeting
        fixture = "single_speaker_30s"

        job = bot_trigger.send_bot(meeting)
        obs = bot_observer.wait_for_join(job)
        assert join_checker.check(obs).passed, "Bot did not join Teams"

        audio_path = os.path.join(config.audio.fixtures_dir, f"{fixture}.wav")
        virtual_mic.play_sync(audio_path)

        meeting_end_time = time.time()
        platform.end_meeting(meeting.meeting_id)
        bot_observer.wait_for_transcript(job, obs, meeting_end_time)

        assert timing_checker.check(obs).passed, "Transcript delivery SLA failed"
        assert obs.transcript_data, "No transcript received"
        result = transcript_checker.check_accuracy(obs.transcript_data, fixture)
        assert result.passed, f"Teams transcript accuracy failed: {result.summary()}"

    def test_two_speaker_accuracy(
        self, teams_meeting, virtual_mic, bot_trigger, bot_observer,
        join_checker, timing_checker, transcript_checker
    ):
        platform, meeting = teams_meeting
        fixture = "two_speaker_2min"

        job = bot_trigger.send_bot(meeting)
        obs = bot_observer.wait_for_join(job)
        assert join_checker.check(obs).passed

        audio_path = os.path.join(config.audio.fixtures_dir, f"{fixture}.wav")
        virtual_mic.play_sync(audio_path)

        meeting_end_time = time.time()
        platform.end_meeting(meeting.meeting_id)
        bot_observer.wait_for_transcript(job, obs, meeting_end_time)

        assert obs.transcript_data
        result = transcript_checker.check_accuracy(obs.transcript_data, fixture)
        assert result.passed, f"Two-speaker accuracy failed on Teams: {result.summary()}"


class TestTeamsEdgeCases:

    @pytest.mark.edge_case
    def test_silent_meeting_no_transcript(
        self, teams_meeting, virtual_mic, bot_trigger, bot_observer,
        join_checker, transcript_checker
    ):
        platform, meeting = teams_meeting
        job = bot_trigger.send_bot(meeting)
        obs = bot_observer.wait_for_join(job)
        assert join_checker.check(obs).passed

        virtual_mic.play_silence(30)
        platform.end_meeting(meeting.meeting_id)
        bot_observer.wait_for_transcript(job, obs, time.time(), timeout_seconds=120)

        result = transcript_checker.check_silence(obs.transcript_data)
        assert result.passed, f"Silent meeting produced transcript on Teams: {result.issues}"

    @pytest.mark.edge_case
    def test_bot_joins_late(
        self, teams_meeting, virtual_mic, bot_trigger, bot_observer,
        join_checker, transcript_checker
    ):
        platform, meeting = teams_meeting
        fixture = "late_join_content"

        time.sleep(30)  # Simulate meeting running before bot is triggered

        job = bot_trigger.send_bot(meeting, extra_metadata={"scenario": "late_join"})
        obs = bot_observer.wait_for_join(job)
        assert join_checker.check(obs).passed, "Bot did not join Teams (late join)"

        audio_path = os.path.join(config.audio.fixtures_dir, f"{fixture}.wav")
        virtual_mic.play_sync(audio_path)

        meeting_end_time = time.time()
        platform.end_meeting(meeting.meeting_id)
        bot_observer.wait_for_transcript(job, obs, meeting_end_time)

        assert obs.transcript_data
        result = transcript_checker.check_accuracy(obs.transcript_data, fixture)
        assert result.passed, f"Late join failed on Teams: {result.summary()}"
