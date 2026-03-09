"""
assertions/transcript_check.py
Validates transcript accuracy against known ground-truth scripts.

Metrics:
  - Word Error Rate (WER): standard ASR evaluation metric
  - Speaker attribution accuracy: correct speaker labels
  - Coverage: are all expected segments present?
  - Content completeness: word coverage %
"""

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

GROUND_TRUTH_DIR = os.path.join(os.path.dirname(__file__), "../fixtures/ground_truth")


def _normalize(text: str) -> str:
    """Lowercase, remove punctuation, collapse whitespace."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _word_error_rate(reference: str, hypothesis: str) -> float:
    """
    Compute Word Error Rate using dynamic programming.
    WER = (S + D + I) / N
    where S=substitutions, D=deletions, I=insertions, N=reference word count.
    """
    ref_words = _normalize(reference).split()
    hyp_words = _normalize(hypothesis).split()

    if not ref_words:
        return 0.0 if not hyp_words else 1.0

    n = len(ref_words)
    m = len(hyp_words)

    # DP matrix
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if ref_words[i - 1] == hyp_words[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(dp[i - 1][j - 1], dp[i - 1][j], dp[i][j - 1])

    return dp[n][m] / n


@dataclass
class TranscriptAssertionResult:
    passed: bool
    wer: Optional[float] = None
    wer_status: str = "N/A"                  # "pass" | "warn" | "fail"
    speaker_accuracy: Optional[float] = None
    speaker_status: str = "N/A"
    word_coverage: Optional[float] = None    # % of reference words found
    issues: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)

    def summary(self) -> str:
        lines = [
            f"WER: {self.wer:.1%} ({self.wer_status})" if self.wer is not None else "WER: N/A",
            f"Speaker accuracy: {self.speaker_accuracy:.1%} ({self.speaker_status})"
            if self.speaker_accuracy is not None else "Speaker: N/A",
            f"Word coverage: {self.word_coverage:.1%}" if self.word_coverage is not None else "",
        ]
        if self.issues:
            lines.append("Issues: " + "; ".join(self.issues))
        return " | ".join(l for l in lines if l)


class TranscriptChecker:
    """
    Compares HireLogic transcript output against ground-truth fixtures.
    """

    def __init__(
        self,
        wer_fail: float = 0.20,
        wer_warn: float = 0.10,
        speaker_fail: float = 0.80,
        speaker_warn: float = 0.90,
    ):
        from config.settings import config
        self.wer_fail = wer_fail or config.sla.wer_fail_threshold
        self.wer_warn = wer_warn or config.sla.wer_warn_threshold
        self.speaker_fail = speaker_fail or config.sla.speaker_accuracy_fail
        self.speaker_warn = speaker_warn or config.sla.speaker_accuracy_warn

    def load_ground_truth(self, fixture_name: str) -> dict:
        """Load a ground truth JSON fixture by name (without .json extension)."""
        path = os.path.join(GROUND_TRUTH_DIR, f"{fixture_name}.json")
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"Ground truth fixture not found: {path}\n"
                "Run: python audio/generator.py --all"
            )
        with open(path) as f:
            return json.load(f)

    def check_accuracy(
        self,
        transcript_data: dict,
        fixture_name: str,
        ground_truth: Optional[dict] = None,
    ) -> TranscriptAssertionResult:
        """
        Full accuracy check: WER + speaker attribution.

        transcript_data: The response from HireLogic's transcript API.
        fixture_name: Name of the ground truth fixture to compare against.
        ground_truth: Pre-loaded ground truth (optional, loads from file if None).
        """
        if ground_truth is None:
            ground_truth = self.load_ground_truth(fixture_name)

        issues = []
        result = TranscriptAssertionResult(passed=True)

        # --- Extract full text from transcript ---
        hypothesis = self._extract_full_text(transcript_data)
        reference = ground_truth.get("full_text", "")

        if not reference:
            # Silence fixture — check that nothing was transcribed
            if hypothesis.strip():
                issues.append(f"Expected silence but got transcript: '{hypothesis[:100]}...'")
                result.passed = False
            result.issues = issues
            return result

        if not hypothesis:
            issues.append("Transcript is empty")
            result.passed = False
            result.issues = issues
            return result

        # --- WER ---
        wer = _word_error_rate(reference, hypothesis)
        result.wer = wer

        if wer >= self.wer_fail:
            result.wer_status = "fail"
            result.passed = False
            issues.append(f"WER {wer:.1%} exceeds fail threshold {self.wer_fail:.1%}")
        elif wer >= self.wer_warn:
            result.wer_status = "warn"
            issues.append(f"WER {wer:.1%} exceeds warn threshold {self.wer_warn:.1%}")
        else:
            result.wer_status = "pass"

        # --- Word coverage ---
        ref_words = set(_normalize(reference).split())
        hyp_words = set(_normalize(hypothesis).split())
        result.word_coverage = len(ref_words & hyp_words) / len(ref_words) if ref_words else 1.0

        # --- Speaker attribution (if transcript has segments) ---
        transcript_segments = transcript_data.get("transcript", [])
        gt_segments = ground_truth.get("segments", [])

        if gt_segments and transcript_segments:
            speaker_acc = self._check_speaker_accuracy(transcript_segments, gt_segments)
            result.speaker_accuracy = speaker_acc

            if speaker_acc < self.speaker_fail:
                result.speaker_status = "fail"
                result.passed = False
                issues.append(f"Speaker accuracy {speaker_acc:.1%} below fail threshold")
            elif speaker_acc < self.speaker_warn:
                result.speaker_status = "warn"
                issues.append(f"Speaker accuracy {speaker_acc:.1%} below warn threshold")
            else:
                result.speaker_status = "pass"

        result.issues = issues
        result.details = {
            "reference_length": len(reference.split()),
            "hypothesis_length": len(hypothesis.split()),
            "reference_preview": reference[:200],
            "hypothesis_preview": hypothesis[:200],
        }

        logger.info(f"[TranscriptCheck] {fixture_name}: {result.summary()}")
        return result

    def check_silence(self, transcript_data: Optional[dict]) -> TranscriptAssertionResult:
        """
        Verify that a silent meeting produces no transcript.
        """
        result = TranscriptAssertionResult(passed=True)

        if transcript_data is None:
            result.passed = True
            return result

        text = self._extract_full_text(transcript_data)
        if text.strip():
            result.passed = False
            result.issues = [f"Expected no transcript for silent meeting, got: '{text[:100]}'"]

        return result

    def _extract_full_text(self, transcript_data: dict) -> str:
        """Extract concatenated text from transcript response."""
        # Try full_text field first
        if "full_text" in transcript_data:
            return transcript_data["full_text"]
        # Fallback: concatenate segment texts
        segments = transcript_data.get("transcript", [])
        return " ".join(s.get("text", "") for s in segments)

    def _check_speaker_accuracy(
        self,
        transcript_segments: list[dict],
        gt_segments: list[dict],
    ) -> float:
        """
        Match transcript segments to ground truth by time overlap and
        compute the fraction with correct speaker attribution.

        Since speaker labels may differ (GT: "Speaker 1" vs bot: "Alex"),
        we use a consistent mapping: the most common bot label for each GT speaker.
        """
        if not gt_segments:
            return 1.0

        # Build a map: for each GT segment, find the bot segment with most time overlap
        correct = 0
        total = len(gt_segments)
        speaker_map: dict[str, str] = {}  # gt_speaker → most common bot_speaker

        for gt_seg in gt_segments:
            gt_start = gt_seg.get("start_time", 0)
            gt_end = gt_seg.get("end_time", gt_start + 1)
            gt_speaker = gt_seg.get("speaker", "")

            # Find overlapping bot segments
            overlapping = []
            for t_seg in transcript_segments:
                t_start = t_seg.get("start_time", 0)
                t_end = t_seg.get("end_time", t_start + 1)
                overlap = max(0, min(gt_end, t_end) - max(gt_start, t_start))
                if overlap > 0:
                    overlapping.append((overlap, t_seg.get("speaker", "")))

            if not overlapping:
                continue

            # Find the dominant bot speaker for this GT segment
            overlapping.sort(reverse=True)
            bot_speaker = overlapping[0][1]

            # Build a consistent speaker mapping on first encounter
            if gt_speaker not in speaker_map:
                speaker_map[gt_speaker] = bot_speaker

            # Check if the assigned speaker matches the established mapping
            if speaker_map.get(gt_speaker) == bot_speaker:
                correct += 1

        return correct / total if total > 0 else 1.0
