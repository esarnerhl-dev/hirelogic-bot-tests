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
    seconds_after_start: Optional[float] = None


class ZoomWebhookListener:
    def __init__(self, webhook_secret: str, smee_url: str, port: int = 5055):
        self.webhook_secret = webhook_secret
        self.smee_url = smee_url
        self.port = port

        self.app = Flask(__name__)
        self._result: Optional[WebhookResult] = None
        self._lock = threading.Event()
        self._smee_proc: Optional[subprocess.Popen] = None

        self._setup_routes()

    def _setup_routes(self):
        @self.app.route("/zoom/webhook", methods=["POST"])
        def webhook():
            body = request.get_data()
            sig = request.headers.get("x-zm-signature", "")
            ts = request.headers.get("x-zm-request-timestamp", "")

            expected = "v0=" + hmac.new(
                self.webhook_secret.encode(),
                f"v0:{ts}:{body.decode()}".encode(),
                hashlib.sha256
            ).hexdigest()

            if sig and not hmac.compare_digest(sig, expected):
                logger.warning("[Webhook] Invalid signature")
                return jsonify({"error": "invalid signature"}), 401

            data = request.json or {}
            event = data.get("event", "")
            logger.info(f"[Webhook] Event received: {event}")

            # Zoom URL validation challenge
            if event == "endpoint.url_validation":
                plain = data["payload"]["plainToken"]
                hashed = hmac.new(
                    self.webhook_secret.encode(),
                    plain.encode(),
                    hashlib.sha256
                ).hexdigest()
                logger.info("[Webhook] Responding to URL validation challenge")
                return jsonify({"plainToken": plain, "encryptedToken": hashed})

            # Participant joined
            if event == "meeting.participant_joined":
                obj = data.get("payload", {}).get("object", {})
                participant = obj.get("participant", {})
                name = (participant.get("user_name", "")
                        or participant.get("display_name", ""))
                mid = str(obj.get("id", ""))

                logger.info(f"[Webhook] Participant joined meeting {mid}: '{name}'")

                if any(frag in name.lower() for frag in BOT_NAME_FRAGMENTS):
                    logger.info(f"[Webhook] ✅ HireLogic bot detected: '{name}'")
                    self._result = WebhookResult(
                        detected=True,
                        participant_name=name,
                        joined_at=time.time(),
                    )
                    self._lock.set()

            return jsonify({"status": "ok"})

    def _start_server(self):
        t = threading.Thread(
            target=lambda: self.app.run(
                host="0.0.0.0", port=self.port, use_reloader=False
            ),
            daemon=True,
        )
        t.start()
        time.sleep(1)
        logger.info(f"[Webhook] Flask server listening on port {self.port}")

    def _start_smee(self):
        logger.info(f"[Webhook] Starting smee client → {self.smee_url}")
        self._smee_proc = subprocess.Popen(
            ["npx", "--yes", "smee-client",
             "--url", self.smee_url,
             "--target", f"http://localhost:{self.port}/zoom/webhook"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        # Wait until smee confirms it's connected
        for _ in range(30):
            line = self._smee_proc.stdout.readline()
            logger.debug(f"[smee] {line.strip()}")
            if "Forwarding" in line or "connected" in line.lower():
                logger.info(f"[Webhook] smee client connected: {line.strip()}")
                return
            time.sleep(0.5)
        logger.warning("[Webhook] smee client may not have connected — proceeding anyway")

    def wait_for_bot(self, timeout: int = 300,
                     start_time: Optional[float] = None) -> WebhookResult:
        try:
            self._start_server()
            self._start_smee()

            logger.info(
                f"[Webhook] Listening for bot join via {self.smee_url} "
                f"(timeout={timeout}s)..."
            )

            detected = self._lock.wait(timeout=timeout)

            if detected and self._result:
                if start_time:
                    self._result.seconds_after_start = (
                        self._result.joined_at - start_time
                    )
                return self._result
            else:
                logger.warning("[Webhook] Timeout — bot did not join within window")
                return WebhookResult(detected=False)

        except Exception as e:
            logger.error(f"[Webhook] Error: {e}")
            return WebhookResult(detected=False)
        finally:
            if self._smee_proc:
                self._smee_proc.terminate()
                logger.info("[Webhook] smee client stopped")
