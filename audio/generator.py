"""
audio/generator.py
Generates WAV audio fixtures with known content for transcript accuracy testing.
Uses gTTS (Google TTS) to produce natural-sounding speech from text scripts.

Run once to generate fixtures:
    python audio/generator.py --all
    python audio/generator.py --script single_speaker_30s
"""

import argparse
import json
import logging
import os

logger = logging.getLogger(__name__)

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "../fixtures/audio")
GROUND_TRUTH_DIR = os.path.join(os.path.dirname(__file__), "../fixtures/ground_truth")

# ---------------------------------------------------------------------------
# Test scripts — these define WHAT is spoken and WHAT we expect back
# ---------------------------------------------------------------------------

SCRIPTS = {
    "single_speaker_30s": {
        "description": "Single speaker, ~30 seconds of clear speech",
        "segments": [
            {
                "speaker": "Speaker 1",
                "text": (
                    "Hello and welcome to this test meeting. "
                    "My name is Alex and I'll be walking through a few key topics today. "
                    "First, let's discuss the quarterly results. "
                    "Revenue was up fifteen percent compared to last quarter. "
                    "Customer satisfaction scores also improved significantly. "
                    "That concludes our brief overview for this session."
                ),
                "pause_after": 0.5,
            }
        ],
    },

    "two_speaker_2min": {
        "description": "Two speakers alternating, ~2 minutes",
        "segments": [
            {
                "speaker": "Speaker 1",
                "text": (
                    "Good morning everyone. Let's get started with today's interview. "
                    "Can you tell me a little bit about your background and experience?"
                ),
                "pause_after": 1.0,
            },
            {
                "speaker": "Speaker 2",
                "text": (
                    "Of course. I have five years of experience in software engineering, "
                    "primarily focused on backend systems and cloud infrastructure. "
                    "In my most recent role I led a team of four engineers."
                ),
                "pause_after": 1.0,
            },
            {
                "speaker": "Speaker 1",
                "text": (
                    "That's great. Can you describe a challenging technical problem "
                    "you've solved recently and walk me through your approach?"
                ),
                "pause_after": 1.0,
            },
            {
                "speaker": "Speaker 2",
                "text": (
                    "Sure. Last year we had a significant database performance issue. "
                    "Query times were exceeding ten seconds for our main dashboard. "
                    "I diagnosed the problem by analyzing slow query logs and found "
                    "we were missing indexes on three critical columns. "
                    "After adding the indexes and rewriting two queries, "
                    "response time dropped to under two hundred milliseconds."
                ),
                "pause_after": 1.0,
            },
            {
                "speaker": "Speaker 1",
                "text": (
                    "Excellent. How did you communicate that solution to your team and stakeholders?"
                ),
                "pause_after": 1.0,
            },
            {
                "speaker": "Speaker 2",
                "text": (
                    "I wrote a brief incident report summarizing the root cause, "
                    "the fix, and the preventive measures we put in place. "
                    "I presented it in our weekly engineering sync "
                    "and shared it with the product team so they understood the impact."
                ),
                "pause_after": 0.5,
            },
        ],
    },

    "noisy_background": {
        "description": "Speech with background noise — tests robustness",
        "segments": [
            {
                "speaker": "Speaker 1",
                "text": (
                    "This is a test with some background noise present. "
                    "The transcription should still be reasonably accurate "
                    "even when there is ambient sound in the recording. "
                    "We expect a slightly higher word error rate for this scenario."
                ),
                "pause_after": 0.5,
            }
        ],
        "add_noise": True,
        "noise_level_db": -20,
    },

    "silence_30s": {
        "description": "30 seconds of silence — bot should produce no transcript",
        "segments": [],
        "silence_only": True,
        "duration_seconds": 30,
    },

    "late_join_content": {
        "description": "Content meant to be transcribed after a 2-minute delay",
        "segments": [
            {
                "speaker": "Speaker 1",
                "text": (
                    "Welcome back everyone. The bot has now joined the meeting. "
                    "We can confirm that transcription has resumed at this point. "
                    "This segment is the ground truth for the late join test scenario. "
                    "The bot should capture everything from this moment forward."
                ),
                "pause_after": 0.5,
            }
        ],
    },
}


def generate_fixture(script_name: str, script: dict) -> None:
    """Generate a WAV file and ground truth JSON for a given script."""
    try:
        from gtts import gTTS
        from pydub import AudioSegment
        from pydub.generators import WhiteNoise
        import io
    except ImportError:
        logger.error("Missing deps: pip install gtts pydub")
        raise

    os.makedirs(FIXTURES_DIR, exist_ok=True)
    os.makedirs(GROUND_TRUTH_DIR, exist_ok=True)

    wav_path = os.path.join(FIXTURES_DIR, f"{script_name}.wav")
    gt_path = os.path.join(GROUND_TRUTH_DIR, f"{script_name}.json")

    # --- Handle silence-only fixtures ---
    if script.get("silence_only"):
        duration_ms = script.get("duration_seconds", 30) * 1000
        silence = AudioSegment.silent(duration=duration_ms)
        silence.export(wav_path, format="wav")
        ground_truth = {"segments": [], "full_text": "", "word_count": 0}
        with open(gt_path, "w") as f:
            json.dump(ground_truth, f, indent=2)
        logger.info(f"Generated silence fixture: {wav_path}")
        return

    # --- Generate speech for each segment ---
    combined = AudioSegment.empty()
    gt_segments = []
    current_time = 0.0

    for seg in script["segments"]:
        tts = gTTS(text=seg["text"], lang="en", slow=False)
        mp3_buffer = io.BytesIO()
        tts.write_to_fp(mp3_buffer)
        mp3_buffer.seek(0)

        audio_seg = AudioSegment.from_mp3(mp3_buffer)
        duration_s = len(audio_seg) / 1000.0

        gt_segments.append({
            "speaker": seg["speaker"],
            "text": seg["text"].strip(),
            "start_time": round(current_time, 2),
            "end_time": round(current_time + duration_s, 2),
        })

        combined += audio_seg

        pause_ms = int(seg.get("pause_after", 0.5) * 1000)
        if pause_ms > 0:
            combined += AudioSegment.silent(duration=pause_ms)

        current_time += duration_s + seg.get("pause_after", 0.5)

    # --- Optionally add background noise ---
    if script.get("add_noise"):
        noise_db = script.get("noise_level_db", -20)
        noise = WhiteNoise().to_audio_segment(duration=len(combined)).apply_gain(noise_db)
        combined = combined.overlay(noise)

    combined.export(wav_path, format="wav")

    # --- Write ground truth ---
    full_text = " ".join(s["text"] for s in gt_segments)
    ground_truth = {
        "description": script["description"],
        "segments": gt_segments,
        "full_text": full_text,
        "word_count": len(full_text.split()),
        "duration_seconds": round(len(combined) / 1000.0, 2),
    }
    with open(gt_path, "w") as f:
        json.dump(ground_truth, f, indent=2)

    logger.info(f"Generated: {wav_path} ({ground_truth['duration_seconds']}s, {ground_truth['word_count']} words)")


def generate_all() -> None:
    for name, script in SCRIPTS.items():
        logger.info(f"Generating fixture: {name}")
        generate_fixture(name, script)
    logger.info("All fixtures generated.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Generate HireLogic test audio fixtures")
    parser.add_argument("--all", action="store_true", help="Generate all fixtures")
    parser.add_argument("--script", type=str, help="Generate a specific script by name")
    parser.add_argument("--list", action="store_true", help="List available scripts")
    args = parser.parse_args()

    if args.list:
        for name, s in SCRIPTS.items():
            print(f"  {name}: {s['description']}")
    elif args.all:
        generate_all()
    elif args.script:
        if args.script not in SCRIPTS:
            print(f"Unknown script '{args.script}'. Use --list to see options.")
        else:
            generate_fixture(args.script, SCRIPTS[args.script])
    else:
        parser.print_help()
