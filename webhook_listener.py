"""
bot/webhook_listener.py

Listens for Zoom webhook events to detect when the HireLogic bot joins a meeting.

Architecture:
1. Starts a local Flask HTTP server
2. Uses localtunnel to expose it publicly  
3. Waits for meeting.participant_joined event matching the bot name
4. Cleans up after detection or timeout
"""

import hashlib
import hmac
import json
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
  def __init__(self, zoom_account_id: str, zoom_client_id: str,
             zoom_client_secret: str, webhook_secret: str,
             meeting_id: str, bot_email: str = "", port: int = 4040):
        self.zoom_account_id = zoom_account_id
        self.zoom_client_id = zoom_client_id
        self.zoom_client_secret = zoom_client_secret
        self.webhook_secret = webhook_secret
        self.meeting_id = str(meeting_id)
        self.port = port
        self.bot_email = bot_email

        self.app = Flask(__name__)
        self._result: Optional[WebhookResult] = None
        self._lock = threading.Event()
        self._tunnel_url: Optional[str] = None
        self._tunnel_proc: Optional[subprocess.Popen] = None

        self._setup_routes()

    def _setup_routes(self):
        @self.app.route("/webhook", methods=["POST"])
        def webhook():
            body = request.get_data()
            sig = request.headers.get("x-zm-signature", "")
            ts = request.headers.get("x-zm-request-timestamp", "")

            expected = "v0=" + hmac.new(
                self.webhook_secret.encode(),
                f"v0:{ts}:{body.decode()}".encode(),
                hashlib.sha256
            ).hexdigest()

            if not hmac.compare_digest(sig, expected):
                logger.warning("[Webhook] Invalid signature — rejecting")
                return jsonify({"error": "invalid signature"}), 401

            data = request.json
            event = data.get("event", "")
            logger.info(f"[Webhook] Event: {event}")

            # Zoom URL validation challenge
            if event == "endpoint.url_validation":
                plain = data["payload"]["plainToken"]
                hashed = hmac.new(
                    self.webhook_secret.encode(),
                    plain.encode(),
                    hashlib.sha256
                ).hexdigest()
                return jsonify({"plainToken": plain, "encryptedToken": hashed})

            # Participant joined
            if event == "meeting.participant_joined":
                obj = data.get("payload", {}).get("object", {})
                participant = obj.get("participant", {})
                name = participant.get("user_name", "") or participant.get("display_name", "")
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

    def _get_token(self) -> str:
        resp = requests.post(
            "https://zoom.us/oauth/token",
            params={"grant_type": "account_credentials", "account_id": self.zoom_account_id},
            auth=(self.zoom_client_id, self.zoom_client_secret),
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]

    def _start_server(self):
        t = threading.Thread(
            target=lambda: self.app.run(host="0.0.0.0", port=self.port, use_reloader=False),
            daemon=True,
        )
        t.start()
        time.sleep(1)
        logger.info(f"[Webhook] Flask server listening on port {self.port}")

    def _start_tunnel(self) -> str:
        logger.info("[Webhook] Starting localtunnel...")
        self._tunnel_proc = subprocess.Popen(
            ["npx", "--yes", "localtunnel", "--port", str(self.port)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        for _ in range(60):
            line = self._tunnel_proc.stdout.readline()
            logger.debug(f"[Webhook] localtunnel: {line.strip()}")
            for word in line.split():
                if word.startswith("https://") and "loca.lt" in word:
                    url = word.strip()
                    logger.info(f"[Webhook] Tunnel URL: {url}")
                    return url
            time.sleep(0.5)
        raise RuntimeError("Could not get localtunnel URL after 30s")

    def _update_zoom_webhook(self, endpoint_url: str):
        """Update the event subscription URL in Zoom."""
        token = self._get_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        webhook_url = f"{endpoint_url}/webhook"

        # Try to find and update existing event subscription
        resp = requests.get("https://api.zoom.us/v2/webhooks", headers=headers, timeout=15)
        logger.info(f"[Webhook] GET /webhooks: {resp.status_code} {resp.text[:200]}")

        if resp.ok:
            for wh in resp.json().get("webhooks", []):
                wid = wh.get("webhook_id", "")
                patch = requests.patch(
                    f"https://api.zoom.us/v2/webhooks/{wid}",
                    headers=headers,
                    json={"url": webhook_url},
                    timeout=15,
                )
                logger.info(f"[Webhook] PATCH webhook {wid}: {patch.status_code} {patch.text[:200]}")
                return

        logger.warning("[Webhook] No existing webhook found to update — make sure event subscription is configured in Zoom marketplace")

    def wait_for_bot(self, timeout: int = 300, start_time: Optional[float] = None) -> WebhookResult:
        try:
            self._start_server()
            tunnel_url = self._start_tunnel()
            self._update_zoom_webhook(tunnel_url)

            logger.info(f"[Webhook] Ready — waiting up to {timeout}s for bot join event...")
            detected = self._lock.wait(timeout=timeout)

            if detected and self._result:
                if start_time:
                    self._result.seconds_after_start = self._result.joined_at - start_time
                return self._result
            else:
                logger.warning("[Webhook] Timeout — bot did not join within window")
                return WebhookResult(detected=False)

        except Exception as e:
            logger.error(f"[Webhook] Error in wait_for_bot: {e}")
            return WebhookResult(detected=False)
        finally:
            if self._tunnel_proc:
                self._tunnel_proc.terminate()
                logger.info("[Webhook] Tunnel stopped")
