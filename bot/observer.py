"""
bot/observer.py
Polls the HireLogic API to observe bot join status and transcript delivery.
Provides blocking wait helpers with configurable timeouts.
"""

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

from bot.trigger import BotJobResult, BotTrigger
from config.settings import config
from platforms.base import BasePlatform

logger = logging.getLogger(__name__)


class BotStatus(str, Enum):
    PENDING = "pending"
    JOINING = "joining"
    IN_MEETING = "in_meeting"
    RECORDING = "recording"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"       # Our synthetic status when we give up waiting


@dataclass
class ObservationResult:
    """Full observation result collected during a test."""
    job_id: str
    platform: str

    # Join observation
    joined: bool = False
    join_latency_seconds: Optional[float] = None  # Seconds from trigger to confirmed join

    # Transcript observation
    transcript_received: bool = False
    transcript_latency_seconds: Optional[float] = None  # Seconds from meeting end to transcript
    transcript_data: Optional[dict] = None

    # Timeline of status changes
    status_timeline: list[tuple[float, str]] = None  # [(timestamp, status), ...]

    def __post_init__(self):
        if self.status_timeline is None:
            self.status_timeline = []


class BotObserver:
    """
    Watches the HireLogic API for bot join confirmation and transcript delivery.

    Usage:
        trigger = BotTrigger()
        observer = BotObserver(trigger)
        job = trigger.send_bot(meeting)

        # Wait for bot to appear in meeting
        result = observer.wait_for_join(job, platform)

        # ... run test scenario (play audio, etc.) ...

        # Wait for transcript after meeting ends
        observer.wait_for_transcript(job, result)
    """

    def __init__(self, trigger: Optional[BotTrigger] = None):
        self.trigger = trigger or BotTrigger()
        self.poll_interval = config.poll_interval

    def wait_for_join(
        self,
        job: BotJobResult,
        platform: Optional[BasePlatform] = None,
        timeout_seconds: Optional[int] = None,
    ) -> ObservationResult:
        """
        Block until the bot has joined the meeting or timeout is reached.

        Uses two signals in parallel:
          1. HireLogic API status changes to 'in_meeting' or 'recording'
          2. (Optional) Platform participant list includes bot name

        Returns ObservationResult with joined=True/False and join_latency.
        """
        if timeout_seconds is None:
            timeout_seconds = config.sla.bot_join_max_seconds * 2  # Extra headroom

        result = ObservationResult(job_id=job.job_id, platform=job.platform)
        start_time = time.time()
        trigger_time = start_time

        logger.info(
            f"[Observer] Waiting for bot join | job={job.job_id} | "
            f"platform={job.platform} | timeout={timeout_seconds}s"
        )

        joined_statuses = {BotStatus.IN_MEETING, BotStatus.RECORDING, BotStatus.COMPLETED}

        while True:
            elapsed = time.time() - start_time

            if elapsed > timeout_seconds:
                logger.warning(f"[Observer] Timed out waiting for join after {elapsed:.1f}s")
                result.status_timeline.append((time.time(), BotStatus.TIMEOUT))
                break

            # --- Signal 1: HireLogic API status ---
            try:
                status_resp = self.trigger.get_status(job.job_id, job.meeting_id)
                raw_status = status_resp.get("status", "")
                status = BotStatus(raw_status) if raw_status in BotStatus._value2member_map_ else None

                if status:
                    result.status_timeline.append((time.time(), status.value))
                    logger.debug(f"[Observer] Status={status.value} at t+{elapsed:.1f}s")

                if status in joined_statuses:
                    result.joined = True
                    result.join_latency_seconds = time.time() - trigger_time
                    logger.info(
                        f"[Observer] Bot joined! latency={result.join_latency_seconds:.1f}s "
                        f"status={status.value}"
                    )
                    break

                if status == BotStatus.FAILED:
                    logger.error(f"[Observer] Bot reported FAILED status: {status_resp}")
                    break

            except Exception as e:
                logger.warning(f"[Observer] Status poll error: {e}")

            # --- Signal 2: Platform participant list (best-effort) ---
            if platform and not result.joined:
                try:
                    if platform.bot_is_in_meeting(job.meeting_id):
                        result.joined = True
                        result.join_latency_seconds = time.time() - trigger_time
                        logger.info(
                            f"[Observer] Bot confirmed via participant list at "
                            f"t+{result.join_latency_seconds:.1f}s"
                        )
                        break
                except Exception as e:
                    logger.debug(f"[Observer] Participant check error: {e}")

            time.sleep(self.poll_interval)

        return result

    def wait_for_transcript(
        self,
        job: BotJobResult,
        result: ObservationResult,
        meeting_end_time: Optional[float] = None,
        timeout_seconds: Optional[int] = None,
    ) -> ObservationResult:
        """
        Block until the transcript is delivered or timeout is reached.
        Updates result in-place and returns it.
        """
        if timeout_seconds is None:
            timeout_seconds = config.sla.transcript_delivery_max_seconds

        end_time = meeting_end_time or time.time()
        deadline = end_time + timeout_seconds
        poll_start = time.time()

        logger.info(
            f"[Observer] Waiting for transcript | job={job.job_id} | timeout={timeout_seconds}s"
        )

        while time.time() < deadline:
            elapsed = time.time() - poll_start

            try:
                transcript = self.trigger.get_transcript(job.job_id, job.meeting_id)
                if transcript:
                    result.transcript_received = True
                    result.transcript_latency_seconds = time.time() - end_time
                    result.transcript_data = transcript
                    logger.info(
                        f"[Observer] Transcript received! "
                        f"latency={result.transcript_latency_seconds:.1f}s "
                        f"words={transcript.get('word_count', '?')}"
                    )
                    return result

            except Exception as e:
                logger.warning(f"[Observer] Transcript poll error at t+{elapsed:.1f}s: {e}")

            time.sleep(self.poll_interval * 2)  # Poll less aggressively for transcript

        logger.warning(f"[Observer] Timed out waiting for transcript after {timeout_seconds}s")
        return result

    def wait_for_completion(
        self,
        job: BotJobResult,
        platform: Optional[BasePlatform] = None,
        timeout_seconds: int = 600,
    ) -> ObservationResult:
        """
        Convenience: wait for join AND transcript in one call.
        Useful for simple tests where we play audio and wait for everything.
        """
        join_result = self.wait_for_join(job, platform)
        meeting_end_time = time.time()  # Caller should end the meeting before calling this
        self.wait_for_transcript(job, join_result, meeting_end_time, timeout_seconds)
        return join_result
