"""
assertions/join_check.py + timing_check.py
Assertions for bot join success and SLA timing compliance.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from bot.observer import ObservationResult
from config.settings import config

logger = logging.getLogger(__name__)


@dataclass
class JoinAssertionResult:
    passed: bool
    joined: bool
    join_latency_seconds: Optional[float]
    latency_status: str = "N/A"   # "pass" | "warn" | "fail"
    issues: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lat = f"{self.join_latency_seconds:.1f}s" if self.join_latency_seconds else "N/A"
        return f"joined={self.joined} latency={lat} ({self.latency_status})"


@dataclass
class TimingAssertionResult:
    passed: bool
    transcript_latency_seconds: Optional[float]
    latency_status: str = "N/A"
    issues: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lat = f"{self.transcript_latency_seconds:.1f}s" if self.transcript_latency_seconds else "N/A"
        return f"transcript_latency={lat} ({self.latency_status})"


class JoinChecker:
    """Asserts that the bot joined the meeting and did so within SLA."""

    def __init__(self):
        self.sla = config.sla

    def check(self, obs: ObservationResult) -> JoinAssertionResult:
        issues = []

        if not obs.joined:
            return JoinAssertionResult(
                passed=False,
                joined=False,
                join_latency_seconds=None,
                latency_status="fail",
                issues=["Bot never joined the meeting"],
            )

        latency = obs.join_latency_seconds
        max_s = self.sla.bot_join_max_seconds
        warn_s = max_s * 0.75  # Warn at 75% of SLA

        if latency is None:
            status = "N/A"
        elif latency > max_s:
            status = "fail"
            issues.append(f"Join latency {latency:.1f}s exceeds SLA of {max_s}s")
        elif latency > warn_s:
            status = "warn"
            issues.append(f"Join latency {latency:.1f}s approaching SLA ({max_s}s)")
        else:
            status = "pass"

        passed = status not in ("fail",) and obs.joined
        result = JoinAssertionResult(
            passed=passed,
            joined=True,
            join_latency_seconds=latency,
            latency_status=status,
            issues=issues,
        )
        logger.info(f"[JoinCheck] {result.summary()}")
        return result


class TimingChecker:
    """Asserts transcript delivery latency is within SLA."""

    def __init__(self):
        self.sla = config.sla

    def check(self, obs: ObservationResult) -> TimingAssertionResult:
        issues = []

        if not obs.transcript_received:
            return TimingAssertionResult(
                passed=False,
                transcript_latency_seconds=None,
                latency_status="fail",
                issues=["Transcript never delivered"],
            )

        latency = obs.transcript_latency_seconds
        max_s = self.sla.transcript_delivery_max_seconds
        warn_s = max_s * 0.70

        if latency is None:
            status = "N/A"
        elif latency > max_s:
            status = "fail"
            issues.append(f"Transcript latency {latency:.1f}s exceeds SLA of {max_s}s")
        elif latency > warn_s:
            status = "warn"
        else:
            status = "pass"

        passed = status != "fail"
        result = TimingAssertionResult(
            passed=passed,
            transcript_latency_seconds=latency,
            latency_status=status,
            issues=issues,
        )
        logger.info(f"[TimingCheck] {result.summary()}")
        return result
