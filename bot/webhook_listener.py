"""
bot/webhook_listener.py

Listens for Zoom webhook events via smee.io relay to detect when the
HireLogic bot joins a meeting.

Setup (one-time):
1. Go to https://smee.io and create a new channel
2. Copy the URL (e.g. https://smee.io/abc123xyz)
3. Set that URL as the webhook endpoint in your Zoom app (Marketplace > Your App > Event Subscriptions)
4. Add the smee URL as ZOOM_WEBHOOK_PROXY_URL in GitHub secrets

At runtime, this listener:
1. Starts a local Flask server
2. Runs smee client to forward events from smee.io to the local server
3. Waits for meeting.participant_joined event matching the HireLogic bot
"""

import hashlib
import hmac
import logging
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Optional

import requests
from flask import Flask, jsonify, request

logger = logging.getLogger(__name__)

BOT_NAME_FRAGMENTS = ["hirelogic", "notetaker", "meeting assistant"]


@dataclass
class WebhookResult:
    detected: bool
    participant_name: Optional[str] = None
    joined_at: Optional[float] = None
    seconds_after_start: Optional[flo
