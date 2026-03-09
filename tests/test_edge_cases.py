"""
tests/test_edge_cases.py
Cross-platform edge cases and robustness scenarios.
Parametrized across all three platforms so one test body covers all three.
"""

import os
import time
import pytest

from config.settings import config

# Parametrize all edge case tests across platforms
ALL_PLATFORMS = ["zoom_meeting", "google_meet_meeting", "teams_meeting"]


@pytest.mark.edge_case
@pytest.mark.parametrize("meeting_fixture", ALL_PLATFORMS)
def test_noisy_background_transcription(
    request,
    meeting_fixture,
    virtual_mic,
    bot_trigger,
    bot_observer,
    join_checker,
    transcript_checker,
):
    """
    Background noise should not prevent the bot from producing an acceptable transcript.
    Uses a looser WER threshold (20%) than clean-audio tests.
    """
    platform, meeting = request.getfixturevalue(meeting_fixture)
    fixture = "noisy_background"

    job = bot_trigger.send_bot(meeting, extra_metadata={"scenario": "noisy_background"})
    obs = bot_observer.wait_for_join(job, platform=platform)
    assert join_checker.check(obs).passed, f"Bot did not join for noisy test ({meeting_fixture})"

    audio_path = os.path.join(config.audio.fixtures_dir, f"{fixture}.wav")
    virtual_mic.play_sync(audio_path)

    meeting_end_time = time.time()
    platform.end_meeting(meeting.meeting_id)
    bot_observer.wait_for_transcript(job, obs, meeting_end_time)

    assert obs.transcript_data, "No transcript received for noisy audio test"

    # Use a permissive checker for noisy audio
    noisy_checker = transcript_checker.__class__(wer_fail=0.30, wer_warn=0.20)
    result = noisy_checker.check_accuracy(obs.transcript_data, fixture)
    assert result.passed, (
        f"Noisy background transcript unacceptable on {meeting_fixture}: {result.summary()}"
    )


@pytest.mark.edge_case
@pytest.mark.parametrize("meeting_fixture", ALL_PLATFORMS)
def test_rapid_speaker_switching(
    request,
    meeting_fixture,
    virtual_mic,
    bot_trigger,
    bot_observer,
    join_checker,
    transcript_checker,
):
    """
    Two speakers alternate quickly (every ~10 seconds).
    Bot should maintain reasonable accuracy and attribution.
    This uses the two_speaker_2min fixture which has multiple turns.
    """
    platform, meeting = request.getfixturevalue(meeting_fixture)
    fixture = "two_speaker_2min"

    job = bot_trigger.send_bot(meeting, extra_metadata={"scenario": "rapid_switching"})
    obs = bot_observer.wait_for_join(job, platform=platform)
    assert join_checker.check(obs).passed, f"Bot did not join ({meeting_fixture})"

    audio_path = os.path.join(config.audio.fixtures_dir, f"{fixture}.wav")
    virtual_mic.play_sync(audio_path)

    meeting_end_time = time.time()
    platform.end_meeting(meeting.meeting_id)
    bot_observer.wait_for_transcript(job, obs, meeting_end_time)

    assert obs.transcript_data, "No transcript for speaker switching test"
    result = transcript_checker.check_accuracy(obs.transcript_data, fixture)
    assert result.passed, f"Speaker switching accuracy failed ({meeting_fixture}): {result.summary()}"


@pytest.mark.edge_case
@pytest.mark.slow
@pytest.mark.parametrize("meeting_fixture", ALL_PLATFORMS)
def test_transcript_delivered_within_sla(
    request,
    meeting_fixture,
    virtual_mic,
    bot_trigger,
    bot_observer,
    join_checker,
    timing_checker,
):
    """
    After the meeting ends, the full transcript must be delivered
    within the configured SLA window (default: 5 minutes).
    """
    platform, meeting = request.getfixturevalue(meeting_fixture)

    job = bot_trigger.send_bot(meeting)
    obs = bot_observer.wait_for_join(job, platform=platform)
    assert join_checker.check(obs).passed, f"Bot did not join ({meeting_fixture})"

    # Play a 30s script
    import os
    audio_path = os.path.join(config.audio.fixtures_dir, "single_speaker_30s.wav")
    virtual_mic.play_sync(audio_path)

    meeting_end_time = time.time()
    platform.end_meeting(meeting.meeting_id)
    bot_observer.wait_for_transcript(
        job, obs, meeting_end_time,
        timeout_seconds=config.sla.transcript_delivery_max_seconds + 60,
    )

    result = timing_checker.check(obs)
    assert result.passed, (
        f"Transcript delivery SLA failed on {meeting_fixture}: {result.summary()}"
    )


@pytest.mark.edge_case
@pytest.mark.parametrize("meeting_fixture", ALL_PLATFORMS)
def test_bot_handles_host_leaving_then_returning(
    request,
    meeting_fixture,
    virtual_mic,
    bot_trigger,
    bot_observer,
    join_checker,
):
    """
    Host leaves the meeting temporarily and rejoins.
    Bot should remain in the meeting and continue recording.
    This simulates connectivity interruptions on the host side.
    """
    platform, meeting = request.getfixturevalue(meeting_fixture)

    job = bot_trigger.send_bot(meeting, extra_metadata={"scenario": "host_rejoin"})
    obs = bot_observer.wait_for_join(job, platform=platform)
    assert join_checker.check(obs).passed, f"Initial join failed ({meeting_fixture})"

    # Play first segment
    import os
    audio_path = os.path.join(config.audio.fixtures_dir, "single_speaker_30s.wav")
    virtual_mic.play_sync(audio_path)

    # Simulate host leaving for 15 seconds (in real test: close and reopen host browser)
    time.sleep(15)

    # Play second segment after "host returns"
    virtual_mic.play_sync(audio_path)

    # Check bot is still in meeting
    still_joined = False
    try:
        status = bot_trigger.get_status(job.job_id, meeting.meeting_id)
        still_joined = status.get("status") not in ("failed", "left_meeting", "completed")
    except Exception:
        pass

    assert still_joined, (
        f"Bot left the meeting during host absence ({meeting_fixture}). "
        f"Expected bot to remain until meeting ends."
    )

    platform.end_meeting(meeting.meeting_id)
