"""
tests/test_zoom.py
Zoom-specific bot integration tests.
"""

import time
import pytest

from config.settings import config

pytestmark = pytest.mark.zoom


class TestZoomBotJoin:
    """Bot join tests on Zoom."""

    def test_bot_joins_within_sla(
        self,
        zoom_meeting,
        bot_trigger,
        bot_observer,
        join_checker,
    ):
        """
        Bot should join the Zoom meeting within the configured SLA window.
        This is the most fundamental test — everything else depends on this working.
        """
        platform, meeting = zoom_meeting

        # Trigger the bot
        job = bot_trigger.send_bot(meeting, extra_metadata={"test": "test_bot_joins_within_sla"})

        # Wait for join
        obs = bot_observer.wait_for_join(
            job,
            platform=platform,
            timeout_seconds=config.sla.bot_join_max_seconds + 30,
        )

        # Assert
        result = join_checker.check(obs)
        assert result.joined, f"Bot did not join Zoom meeting. Timeline: {obs.status_timeline}"
        assert result.passed, f"Join SLA failed: {result.summary()}"

    def test_bot_join_idempotent(self, zoom_meeting, bot_trigger, bot_observer, join_checker):
        """
        Triggering the bot twice for the same meeting should not cause errors.
        Second call should either join once or gracefully indicate already joined.
        """
        platform, meeting = zoom_meeting

        job1 = bot_trigger.send_bot(meeting, extra_metadata={"attempt": 1})
        obs = bot_observer.wait_for_join(job1, platform=platform)

        assert obs.joined, "First bot trigger did not result in join"

        # Second trigger — should not crash the system
        try:
            job2 = bot_trigger.send_bot(meeting, extra_metadata={"attempt": 2})
            assert job2.job_id, "Second trigger returned no job_id"
        except Exception as e:
            pytest.fail(f"Second bot trigger raised an exception: {e}")


class TestZoomTranscriptAccuracy:
    """Transcript quality tests on Zoom."""

    def test_single_speaker_accuracy(
        self,
        zoom_meeting,
        virtual_mic,
        bot_trigger,
        bot_observer,
        join_checker,
        timing_checker,
        transcript_checker,
    ):
        """
        Bot transcribes a known 30-second single-speaker script.
        WER must be below the configured fail threshold.
        """
        platform, meeting = zoom_meeting
        fixture = "single_speaker_30s"

        # 1. Trigger bot
        job = bot_trigger.send_bot(meeting)
        obs = bot_observer.wait_for_join(job, platform=platform)
        assert join_checker.check(obs).passed, "Bot must join before we can test transcription"

        # 2. Play known audio script into meeting via virtual mic
        import os
        audio_path = os.path.join(config.audio.fixtures_dir, f"{fixture}.wav")
        virtual_mic.play_sync(audio_path)

        # 3. End meeting
        meeting_end_time = time.time()
        platform.end_meeting(meeting.meeting_id)

        # 4. Wait for transcript
        bot_observer.wait_for_transcript(job, obs, meeting_end_time)

        # 5. Assert timing
        timing_result = timing_checker.check(obs)
        assert timing_result.passed, f"Transcript delivery SLA failed: {timing_result.summary()}"

        # 6. Assert accuracy
        assert obs.transcript_data, "No transcript data received"
        accuracy_result = transcript_checker.check_accuracy(obs.transcript_data, fixture)
        assert accuracy_result.passed, (
            f"Transcript accuracy failed: {accuracy_result.summary()}\n"
            f"Issues: {accuracy_result.issues}"
        )

    def test_two_speaker_accuracy(
        self,
        zoom_meeting,
        virtual_mic,
        bot_trigger,
        bot_observer,
        join_checker,
        timing_checker,
        transcript_checker,
    ):
        """
        Bot correctly transcribes a two-speaker conversation with speaker labels.
        """
        platform, meeting = zoom_meeting
        fixture = "two_speaker_2min"

        job = bot_trigger.send_bot(meeting)
        obs = bot_observer.wait_for_join(job, platform=platform)
        assert join_checker.check(obs).passed, "Bot did not join"

        import os
        audio_path = os.path.join(config.audio.fixtures_dir, f"{fixture}.wav")
        virtual_mic.play_sync(audio_path)

        meeting_end_time = time.time()
        platform.end_meeting(meeting.meeting_id)
        bot_observer.wait_for_transcript(job, obs, meeting_end_time)

        assert obs.transcript_data, "No transcript received"
        result = transcript_checker.check_accuracy(obs.transcript_data, fixture)
        assert result.passed, f"Two-speaker accuracy failed: {result.summary()}"


class TestZoomEdgeCases:
    """Zoom edge case tests."""

    @pytest.mark.edge_case
    def test_bot_joins_late(
        self,
        zoom_meeting,
        virtual_mic,
        bot_trigger,
        bot_observer,
        join_checker,
        transcript_checker,
    ):
        """
        Meeting starts 2 minutes before the bot is invited.
        Bot should join and capture the content played after it joins.
        """
        platform, meeting = zoom_meeting
        fixture = "late_join_content"

        # Simulate meeting running without bot for 2 minutes
        # (In a real test, a host browser would be running here)
        # We play silence while "waiting" to keep the meeting alive
        import os, threading
        audio_dir = config.audio.fixtures_dir

        silence_path = os.path.join(audio_dir, "silence_30s.wav")
        # Play silence in background to keep meeting active
        def play_background_silence():
            for _ in range(4):  # ~2 minutes of silence
                if os.path.exists(silence_path):
                    virtual_mic.play_sync(silence_path)

        bg_thread = threading.Thread(target=play_background_silence, daemon=True)
        bg_thread.start()

        time.sleep(30)  # Wait 30s before sending bot (shortened from 2min for CI speed)

        # Now trigger the bot
        job = bot_trigger.send_bot(meeting, extra_metadata={"scenario": "late_join"})
        obs = bot_observer.wait_for_join(job, platform=platform)
        assert join_checker.check(obs).passed, "Bot did not join (late join scenario)"

        # Play the content the bot should transcribe
        late_audio = os.path.join(audio_dir, f"{fixture}.wav")
        virtual_mic.play_sync(late_audio)

        meeting_end_time = time.time()
        platform.end_meeting(meeting.meeting_id)
        bot_observer.wait_for_transcript(job, obs, meeting_end_time)

        assert obs.transcript_data, "No transcript received for late join scenario"
        result = transcript_checker.check_accuracy(obs.transcript_data, fixture)
        assert result.passed, f"Late join transcript accuracy failed: {result.summary()}"

    @pytest.mark.edge_case
    def test_silent_meeting_no_transcript(
        self,
        zoom_meeting,
        virtual_mic,
        bot_trigger,
        bot_observer,
        join_checker,
        transcript_checker,
    ):
        """
        A meeting with only silence should not produce a transcript
        (or should produce an empty one).
        """
        platform, meeting = zoom_meeting

        job = bot_trigger.send_bot(meeting)
        obs = bot_observer.wait_for_join(job, platform=platform)
        assert join_checker.check(obs).passed, "Bot did not join"

        # Play 30 seconds of silence
        virtual_mic.play_silence(30)

        meeting_end_time = time.time()
        platform.end_meeting(meeting.meeting_id)
        bot_observer.wait_for_transcript(job, obs, meeting_end_time, timeout_seconds=120)

        # Transcript may be None (not generated) or empty — both are correct
        result = transcript_checker.check_silence(obs.transcript_data)
        assert result.passed, f"Silent meeting produced unexpected transcript: {result.issues}"

    @pytest.mark.edge_case
    def test_bot_exits_when_meeting_ends(
        self,
        zoom_meeting,
        virtual_mic,
        bot_trigger,
        bot_observer,
        join_checker,
    ):
        """
        When the host ends the meeting, the bot should cleanly exit.
        Verified by checking the bot status transitions to 'completed'.
        """
        platform, meeting = zoom_meeting

        job = bot_trigger.send_bot(meeting)
        obs = bot_observer.wait_for_join(job, platform=platform)
        assert join_checker.check(obs).passed, "Bot did not join"

        # End the meeting
        platform.end_meeting(meeting.meeting_id)
        end_time = time.time()

        # Wait for bot to reach 'completed' status
        timeout = 60
        completed = False
        while time.time() - end_time < timeout:
            try:
                status = bot_trigger.get_status(job.job_id, meeting.meeting_id)
                if status.get("status") in ("completed", "left_meeting"):
                    completed = True
                    break
            except Exception:
                pass
            time.sleep(5)

        assert completed, (
            f"Bot did not reach 'completed' status within {timeout}s of meeting end. "
            f"Status timeline: {obs.status_timeline}"
        )
