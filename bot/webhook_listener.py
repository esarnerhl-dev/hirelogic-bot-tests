"""
bot/webhook_listener.py

Starts a local Flask server + localtunnel to receive Zoom webhook events.
Registers the tunnel URL as the Zoom webhook endpoint, then waits for a
`meeting.participant_joined` event matching the HireLogic bot.

Usage:
    listener = ZoomWebhookListener(
        zoom_account_id=...,
        zoom_client_id=...,
        zoom_client_secret=...,
        webhook_secret=...,
        meeting_id=...,
    )
    with listener:
        # send invite, wait for meeting start, etc.
        result = listener.wait_for_bot(timeout=300, start_time=time.time())
"""

import hashlib
import hmac
import json
import logging
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Optional

import requests
from flask import Flask, request, jsonify

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class BotJoinResult:
    detected: bool
    participant_name: Optional[str] = None
    seconds_after_start: Optional[float] = None


# ---------------------------------------------------------------------------
# Listener
# ---------------------------------------------------------------------------

class ZoomWebhookListener:
    """
    Manages a local Flask webhook server + localtunnel for the duration of a test.

    Recommended usage as a context manager so cleanup always runs:

        with ZoomWebhookListener(...) as listener:
            ...
            result = listener.wait_for_bot(timeout=300, start_time=t)
    """

    BOT_KEYWORDS = ["hirelogic", "notetaker", "recorder", "otter", "fireflies"]

    def __init__(
        self,
        zoom_account_id: str,
        zoom_client_id: str,
        zoom_client_secret: str,
        webhook_secret: str,
        meeting_id: str,
        port: int = 5055,
        bot_email: Optional[str] = None,
    ):
        self.zoom_account_id = zoom_account_id
        self.zoom_client_id = zoom_client_id
        self.zoom_client_secret = zoom_client_secret
        self.webhook_secret = webhook_secret
        self.meeting_id = str(meeting_id)
        self.port = port
        self.bot_email = (bot_email or "").lower()

        self._app = Flask(__name__)
        self._server_thread: Optional[threading.Thread] = None
        self._tunnel_proc: Optional[subprocess.Popen] = None
        self._tunnel_url: Optional[str] = None
        self._zoom_app_id: Optional[str] = None  # Zoom webhook app ID for cleanup

        # Signalling
        self._bot_joined = threading.Event()
        self._join_result: Optional[BotJoinResult] = None

        self._register_routes()
        self._start_flask()
        self._start_tunnel()
        self._register_zoom_webhook()

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.cleanup()

    # ------------------------------------------------------------------
    # Flask setup
    # ------------------------------------------------------------------

    def _register_routes(self):
        app = self._app

        @app.route("/zoom/webhook", methods=["POST"])
        def zoom_webhook():
            # --- Signature verification ---
            body_bytes = request.get_data()
            ts = request.headers.get("x-zm-request-timestamp", "")
            sig_header = request.headers.get("x-zm-signature", "")

            if not self._verify_signature(body_bytes, ts, sig_header):
                logger.warning("[Webhook] Signature verification failed — ignoring request")
                return jsonify({"error": "invalid signature"}), 401

            payload = request.get_json(silent=True) or {}
            event = payload.get("event", "")
            logger.info(f"[Webhook] Received event: {event}")

            # --- Zoom URL validation challenge (one-time) ---
            if event == "endpoint.url_validation":
                plain = payload.get("payload", {}).get("plainToken", "")
                hashed = hmac.new(
                    self.webhook_secret.encode(),
                    plain.encode(),
                    hashlib.sha256,
                ).hexdigest()
                return jsonify({"plainToken": plain, "encryptedToken": hashed})

            # --- Participant joined ---
            if event == "meeting.participant_joined":
                self._handle_participant_joined(payload)

            return jsonify({"status": "ok"})

    def _verify_signature(self, body: bytes, timestamp: str, signature: str) -> bool:
        """Verify Zoom webhook signature per Zoom's docs."""
        if not self.webhook_secret:
            logger.warning("[Webhook] No webhook secret configured — skipping verification")
            return True
        try:
            message = f"v0:{timestamp}:{body.decode('utf-8')}"
            expected = "v0=" + hmac.new(
                self.webhook_secret.encode(),
                message.encode(),
                hashlib.sha256,
            ).hexdigest()
            return hmac.compare_digest(expected, signature)
        except Exception as e:
            logger.warning(f"[Webhook] Signature check error: {e}")
            return False

    def _handle_participant_joined(self, payload: dict):
        """Check if the joining participant is the HireLogic bot."""
        try:
            obj = payload.get("payload", {}).get("object", {})
            event_meeting_id = str(obj.get("id", ""))
            participant = obj.get("participant", {})
            name: str = participant.get("user_name", "") or participant.get("name", "")
            email: str = (participant.get("email", "") or "").lower()

            logger.info(
                f"[Webhook] Participant joined meeting {event_meeting_id}: "
                f"name='{name}' email='{email}'"
            )

            # Filter to our meeting
            if event_meeting_id != self.meeting_id:
                logger.info(
                    f"[Webhook] Ignoring — event meeting {event_meeting_id} "
                    f"!= target {self.meeting_id}"
                )
                return

            if self._is_bot(name, email):
                logger.info(f"[Webhook] ✅ Bot detected: '{name}' / '{email}'")
                self._join_result = BotJoinResult(
                    detected=True,
                    participant_name=name or email,
                    seconds_after_start=None,  # filled in by wait_for_bot
                )
                self._bot_joined.set()
            else:
                logger.info(f"[Webhook] Not the bot — skipping '{name}'")

        except Exception as e:
            logger.error(f"[Webhook] Error parsing participant_joined: {e}")

    def _is_bot(self, name: str, email: str) -> bool:
        """Return True if name or email looks like the HireLogic notetaker."""
        name_lower = name.lower()
        email_lower = email.lower()

        # Exact email match if we have one configured
        if self.bot_email and self.bot_email in email_lower:
            return True

        # Keyword match on display name or email
        return any(kw in name_lower or kw in email_lower for kw in self.BOT_KEYWORDS)

    # ------------------------------------------------------------------
    # Flask server (background thread)
    # ------------------------------------------------------------------

    def _start_flask(self):
        """Start Flask in a daemon thread."""
        import werkzeug

        log = logging.getLogger("werkzeug")
        log.setLevel(logging.ERROR)  # suppress Flask request noise in test output

        def run():
            self._app.run(host="0.0.0.0", port=self.port, debug=False, use_reloader=False)

        self._server_thread = threading.Thread(target=run, daemon=True)
        self._server_thread.start()
        time.sleep(1)  # give Flask a moment to bind
        logger.info(f"[Webhook] Flask server listening on port {self.port}")

    # ------------------------------------------------------------------
    # Tunnel (localtunnel)
    # ------------------------------------------------------------------

    def _start_tunnel(self, retries: int = 3):
        """
        Start localtunnel and parse the public URL from stdout.
        Falls back to ngrok if `lt` is not available.
        """
        for attempt in range(1, retries + 1):
            try:
                logger.info(f"[Webhook] Starting localtunnel (attempt {attempt})...")
                proc = subprocess.Popen(
                    ["lt", "--port", str(self.port)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                # Read the URL from the first line of stdout
                url = None
                deadline = time.time() + 15
                while time.time() < deadline:
                    line = proc.stdout.readline()
                    if not line:
                        time.sleep(0.2)
                        continue
                    line = line.strip()
                    logger.debug(f"[Tunnel] stdout: {line}")
                    # localtunnel prints: "your url is: https://xyz.loca.lt"
                    # Extract the https:// URL wherever it appears in the line
                    if "https://" in line:
                        url = "https://" + line.split("https://")[-1].strip()
                        break

                if url:
                    self._tunnel_proc = proc
                    self._tunnel_url = url
                    logger.info(f"[Webhook] Tunnel active: {url}")
                    return
                else:
                    proc.kill()
                    logger.warning(f"[Webhook] Tunnel attempt {attempt} — no URL parsed")

            except FileNotFoundError:
                raise RuntimeError(
                    "localtunnel (`lt`) not found. "
                    "Install it with: npm install -g localtunnel"
                )
            except Exception as e:
                logger.warning(f"[Webhook] Tunnel attempt {attempt} failed: {e}")
                time.sleep(2)

        raise RuntimeError("Could not start localtunnel after multiple attempts")

    @property
    def public_url(self) -> str:
        if not self._tunnel_url:
            raise RuntimeError("Tunnel not started")
        return self._tunnel_url

    @property
    def webhook_url(self) -> str:
        return f"{self.public_url}/zoom/webhook"

    # ------------------------------------------------------------------
    # Zoom webhook registration
    # ------------------------------------------------------------------

    def _get_zoom_token(self) -> str:
        resp = requests.post(
            "https://zoom.us/oauth/token",
            params={
                "grant_type": "account_credentials",
                "account_id": self.zoom_account_id,
            },
            auth=(self.zoom_client_id, self.zoom_client_secret),
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]

    def _register_zoom_webhook(self):
        """
        Register the tunnel URL as a Zoom webhook endpoint.

        Zoom's REST API lets you manage webhook subscriptions on an app.
        We update the notification endpoint URL on the existing app subscription.

        Requires your Zoom app to have the `meeting:read:participant` scope
        and webhook events enabled.

        If you don't want to manage webhook apps via API, you can instead
        hard-code the webhook URL in the Zoom dashboard and expose the tunnel
        on a fixed subdomain (e.g. using ngrok with a static domain).
        """
        try:
            token = self._get_zoom_token()
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }

            # List existing webhook subscriptions
            resp = requests.get(
                "https://api.zoom.us/v2/webhooks",
                headers=headers,
                timeout=15,
            )
            resp.raise_for_status()
            webhooks = resp.json().get("webhook_subscriptions", [])
            logger.info(f"[Webhook] Found {len(webhooks)} existing Zoom webhook(s)")

            target_event = "meeting.participant_joined"
            webhook_id = None

            for wh in webhooks:
                events = [e.get("event") for e in wh.get("events", [])]
                if target_event in events:
                    webhook_id = wh.get("id")
                    logger.info(f"[Webhook] Found existing subscription id={webhook_id}")
                    break

            if webhook_id:
                # Update existing subscription's notification URL
                resp = requests.patch(
                    f"https://api.zoom.us/v2/webhooks/{webhook_id}",
                    headers=headers,
                    json={"notification_url": self.webhook_url},
                    timeout=15,
                )
                resp.raise_for_status()
                logger.info(f"[Webhook] Updated Zoom webhook → {self.webhook_url}")
            else:
                # Create a new subscription
                resp = requests.post(
                    "https://api.zoom.us/v2/webhooks",
                    headers=headers,
                    json={
                        "url": self.webhook_url,
                        "auth_user": "zoom_webhook",
                        "auth_password": self.webhook_secret,
                        "events": [{"event": target_event}],
                    },
                    timeout=15,
                )
                resp.raise_for_status()
                self._zoom_app_id = resp.json().get("id")
                logger.info(
                    f"[Webhook] Created new Zoom webhook id={self._zoom_app_id} → {self.webhook_url}"
                )

        except Exception as e:
            # Non-fatal: log and continue. The test will time out rather than crash
            # if the webhook never fires, which gives you a clear failure signal.
            logger.error(
                f"[Webhook] Could not register Zoom webhook: {e}. "
                "Webhook events may not arrive."
            )

    # ------------------------------------------------------------------
    # Wait for bot
    # ------------------------------------------------------------------

    def wait_for_bot(self, timeout: float, start_time: float) -> BotJoinResult:
        """
        Block until the bot joins or timeout elapses.

        Args:
            timeout:    Max seconds to wait.
            start_time: Unix timestamp of meeting start (for SLA calculation).

        Returns:
            BotJoinResult with detected=True/False and timing info.
        """
        logger.info(f"[Webhook] Waiting up to {timeout:.0f}s for bot webhook event...")
        detected = self._bot_joined.wait(timeout=timeout)

        if detected and self._join_result:
            self._join_result.seconds_after_start = time.time() - start_time
            return self._join_result

        return BotJoinResult(detected=False)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup(self):
        """Tear down tunnel and optionally restore the Zoom webhook URL."""
        if self._tunnel_proc:
            try:
                self._tunnel_proc.terminate()
                self._tunnel_proc.wait(timeout=5)
                logger.info("[Webhook] Tunnel stopped")
            except Exception as e:
                logger.warning(f"[Webhook] Error stopping tunnel: {e}")
            self._tunnel_proc = None

        # Note: we intentionally leave the Zoom webhook subscription in place
        # (pointing to the now-dead tunnel URL) rather than deleting it, so that
        # the next test run can update it rather than accumulating new subscriptions.
        # If you want to delete it, uncomment the block below.
        #
        # if self._zoom_app_id:
        #     try:
        #         token = self._get_zoom_token()
        #         requests.delete(
        #             f"https://api.zoom.us/v2/webhooks/{self._zoom_app_id}",
        #             headers={"Authorization": f"Bearer {token}"},
        #             timeout=10,
        #         )
        #         logger.info(f"[Webhook] Deleted Zoom webhook {self._zoom_app_id}")
        #     except Exception as e:
        #         logger.warning(f"[Webhook] Error deleting webhook: {e}")
