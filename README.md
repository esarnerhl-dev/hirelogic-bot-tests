# HireLogic Bot Automated Testing Framework

Automated end-to-end testing for the HireLogic notetaker bot across Zoom, Google Meet, and Microsoft Teams.

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│                        Test Runner (pytest)                      │
└────────────────────────────┬────────────────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        ▼                    ▼                    ▼
  ┌──────────┐        ┌──────────┐        ┌──────────┐
  │   Zoom   │        │  G Meet  │        │  Teams   │
  │ Platform │        │ Platform │        │ Platform │
  └────┬─────┘        └────┬─────┘        └────┬─────┘
       │                   │                   │
       └───────────────────┼───────────────────┘
                           │  (meeting invite link)
                           ▼
              ┌────────────────────────┐
              │  HireLogic Bot API     │  ← POST /meetings/join
              │  (trigger bot join)    │
              └────────────┬───────────┘
                           │
              ┌────────────▼───────────┐
              │  Synthetic Host        │  ← Playwright headless browser
              │  (plays audio script)  │     + virtual mic (PulseAudio)
              └────────────┬───────────┘
                           │
              ┌────────────▼───────────┐
              │  Observer              │  ← polls webhook / API
              │  (waits for results)   │
              └────────────┬───────────┘
                           │
              ┌────────────▼───────────┐
              │  Assertion Engine      │  ← WER, join latency, accuracy
              └────────────┬───────────┘
                           │
              ┌────────────▼───────────┐
              │  HTML/JSON Report      │
              └────────────────────────┘
```

## Project Structure

```
hirelogic-bot-tests/
├── config/
│   ├── settings.py          # Central config (env vars, timeouts, thresholds)
│   └── platforms.yaml       # Per-platform credentials & endpoints
├── platforms/
│   ├── base.py              # Abstract platform interface
│   ├── zoom.py              # Zoom meeting lifecycle (create/destroy)
│   ├── meet.py              # Google Meet lifecycle
│   └── teams.py             # Microsoft Teams lifecycle
├── bot/
│   ├── trigger.py           # POST to HireLogic API to send bot to meeting
│   └── observer.py          # Poll/webhook for bot status + transcript delivery
├── audio/
│   ├── virtual_mic.py       # PulseAudio virtual mic management
│   ├── player.py            # Play WAV files into virtual mic
│   └── generator.py         # TTS script → WAV fixture generator
├── assertions/
│   ├── join_check.py        # Bot joined? Latency within SLA?
│   ├── transcript_check.py  # WER, completeness, speaker labels
│   └── timing_check.py      # Transcript delivery latency
├── fixtures/
│   ├── audio/               # WAV test scripts (committed to repo)
│   │   ├── single_speaker_30s.wav
│   │   ├── two_speaker_2min.wav
│   │   ├── noisy_background.wav
│   │   └── silence_30s.wav
│   └── ground_truth/        # Expected transcripts (JSON)
│       ├── single_speaker_30s.json
│       └── two_speaker_2min.json
├── tests/
│   ├── conftest.py          # Shared pytest fixtures
│   ├── test_zoom.py
│   ├── test_meet.py
│   ├── test_teams.py
│   └── test_edge_cases.py
├── reporters/
│   └── html_report.py       # Generate rich HTML test report
├── docker/
│   ├── Dockerfile           # Headless test container with PulseAudio
│   └── docker-compose.yml
├── .github/
│   └── workflows/
│       └── bot-tests.yml    # CI/CD pipeline
├── requirements.txt
└── pytest.ini
```

## Quick Start

### 1. Prerequisites

```bash
# Linux: PulseAudio (virtual mic)
sudo apt-get install pulseaudio pulseaudio-utils

# macOS: BlackHole virtual audio
brew install blackhole-2ch

# Python deps
pip install -r requirements.txt

# Playwright browsers
playwright install chromium
```

### 2. Configure credentials

```bash
cp config/platforms.yaml.example config/platforms.yaml
# Fill in your API keys for Zoom, Google, Teams, and HireLogic
```

### 3. Generate audio fixtures (one-time)

```bash
python audio/generator.py --all
```

### 4. Run tests

```bash
# All platforms
pytest tests/ -v

# Single platform
pytest tests/test_zoom.py -v

# Edge cases only
pytest tests/test_edge_cases.py -v

# With HTML report
pytest tests/ --html=reports/results.html
```

## Test Cases

| Test | Platform | What It Checks |
|------|----------|----------------|
| `test_bot_joins_within_sla` | All | Bot appears in meeting within 30s |
| `test_transcript_accuracy_single_speaker` | All | WER < 10% on 30s known script |
| `test_transcript_accuracy_two_speakers` | All | WER < 12%, speaker labels correct |
| `test_bot_joins_late` | All | Bot joins 2min in, still transcribes remainder |
| `test_silent_meeting` | All | No transcript generated for silence |
| `test_bot_exits_on_meeting_end` | All | Bot leaves when host ends meeting |
| `test_noisy_background` | All | WER < 20% with background noise |
| `test_transcript_delivered_within_sla` | All | Full transcript arrives within 5min of meeting end |

## Metrics & Thresholds

| Metric | Green | Yellow | Red |
|--------|-------|--------|-----|
| Bot join latency | < 30s | 30–60s | > 60s |
| Word Error Rate (WER) | < 10% | 10–20% | > 20% |
| Speaker attribution accuracy | > 90% | 80–90% | < 80% |
| Transcript delivery latency | < 5min | 5–10min | > 10min |

## Environment Variables

```bash
# HireLogic
HIRELOGIC_API_URL=https://api.hirelogic.com
HIRELOGIC_API_KEY=your_key

# Zoom
ZOOM_ACCOUNT_ID=...
ZOOM_CLIENT_ID=...
ZOOM_CLIENT_SECRET=...
ZOOM_HOST_EMAIL=test-host@yourorg.com

# Google Meet
GOOGLE_SERVICE_ACCOUNT_JSON=path/to/sa.json
GOOGLE_CALENDAR_ID=test@yourorg.com

# Microsoft Teams
TEAMS_TENANT_ID=...
TEAMS_CLIENT_ID=...
TEAMS_CLIENT_SECRET=...
TEAMS_USER_ID=...  # test user who creates meetings
```
