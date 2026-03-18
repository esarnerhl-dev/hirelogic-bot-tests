"""
bot/trigger.py
Triggers the HireLogic notetaker bot by:
1. Logging into a personal Outlook.com account via browser automation
2. Creating a calendar event with the recurring Zoom URL in the location field
3. Inviting the HireLogic bot email as an attendee

No API keys or admin consent required — works just like a human would.
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional

from config.settings import config

logger = logging.getLogger(__name__)


@dataclass
class BotJobResult:
    """Tracks a bot session for a single meeting."""
    platform: str
    meeting_id: str
    join_url: str
    bot_email: str
    invited_at: float
    calendar_event_id: Optional[str] = None
    status: str = "invited"


class BotTrigger:
    """
    Triggers the HireLogic notetaker bot by creating an Outlook calendar
    event via browser automation (Playwright).
    """

    def __init__(self):
        self.bot_email = config.hirelogic.bot_email
        self.outlook_email = config.outlook.email
        self.outlook_password = config.outlook.password
        self.zoom_url = config.zoom.recurring_meeting_url

    def send_bot(self, meeting=None, **kwargs) -> BotJobResult:
        """
        Log into Outlook.com and create a calendar event inviting the bot.
        The Zoom recurring URL is placed in the location field.
        """
        from playwright.sync_api import sync_playwright

        invited_at = time.time()
        event_id = None

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()

            try:
                # Step 1: Log into Outlook.com
                logger.info("[BotTrigger] Logging into Outlook.com...")
                page.goto("https://login.live.com/")
                page.wait_for_load_state("networkidle", timeout=30000)

                # Enter email
                logger.info(f"[BotTrigger] Entering email...")
                page.wait_for_selector('input[type="email"]', timeout=30000)
                page.fill('input[type="email"]', self.outlook_email)
                page.screenshot(path="/tmp/debug_01_email.png")
                logger.info(f"[BotTrigger] Page URL after email: {page.url}")

                # Try clicking Next button with multiple selectors
                next_selectors = ['#idSIButton9', 'input[type="submit"]', 'button[type="submit"]', '#nextButton']
                for sel in next_selectors:
                    try:
                        if page.locator(sel).is_visible(timeout=3000):
                            page.click(sel)
                            logger.info(f"[BotTrigger] Clicked next with: {sel}")
                            break
                    except Exception:
                        continue
                page.wait_for_load_state("networkidle", timeout=15000)
                time.sleep(2)
                page.screenshot(path="/tmp/debug_02_after_email.png")
                logger.info(f"[BotTrigger] Page URL after next: {page.url}")

                # Enter password
                logger.info("[BotTrigger] Entering password...")
                page.wait_for_selector('input[type="password"]', timeout=15000)
                page.fill('input[type="password"]', self.outlook_password)
                page.screenshot(path="/tmp/debug_03_password.png")

                for sel in next_selectors:
                    try:
                        if page.locator(sel).is_visible(timeout=3000):
                            page.click(sel)
                            logger.info(f"[BotTrigger] Clicked signin with: {sel}")
                            break
                    except Exception:
                        continue
                page.wait_for_load_state("networkidle", timeout=15000)
                time.sleep(2)
                page.screenshot(path="/tmp/debug_04_after_password.png")
                logger.info(f"[BotTrigger] Page URL after signin: {page.url}")

                # Handle any interstitial pages (privacy notice, stay signed in, etc.)
                for _ in range(3):
                    try:
                        # "A quick note about your Microsoft account" OK button
                        if page.locator('button:has-text("OK")').is_visible(timeout=3000):
                            page.click('button:has-text("OK")')
                            logger.info("[BotTrigger] Dismissed Microsoft privacy notice")
                            page.wait_for_load_state("networkidle", timeout=10000)
                            time.sleep(1)
                            continue
                        # "Stay signed in?" prompt
                        for sel in next_selectors:
                            if page.locator(sel).is_visible(timeout=2000):
                                page.click(sel)
                                logger.info(f"[BotTrigger] Clicked stay signed in: {sel}")
                                page.wait_for_load_state("networkidle", timeout=10000)
                                time.sleep(1)
                                break
                    except Exception:
                        break

                # Now navigate to calendar
                logger.info("[BotTrigger] Navigating to calendar...")
                page.goto("https://outlook.live.com/calendar/0/view/workweek")
                page.wait_for_load_state("networkidle", timeout=30000)
                time.sleep(3)
                logger.info(f"[BotTrigger] Logged in successfully, on page: {page.url}")

                # Click New event button
                logger.info("[BotTrigger] Clicking New event button...")
                new_event_selectors = [
                    '[aria-label="New event"]',
                    '[aria-label="New Event"]',
                    'button:has-text("New event")',
                    'button:has-text("New Event")',
                    '[data-testid="newEventButton"]',
                ]
                for sel in new_event_selectors:
                    try:
                        if page.locator(sel).is_visible(timeout=4000):
                            page.click(sel)
                            logger.info(f"[BotTrigger] Clicked new event: {sel}")
                            break
                    except Exception:
                        continue
                page.wait_for_load_state("networkidle", timeout=15000)
                time.sleep(2)
                page.screenshot(path="/tmp/debug_05_after_new_event.png")
                logger.info(f"[BotTrigger] URL after new event click: {page.url}")

                # Step 2: Fill in the new event form
                logger.info("[BotTrigger] Filling in calendar event form...")
                page.screenshot(path="/tmp/debug_06_form.png")

                # Wait for title field — try multiple selectors
                title_selectors = [
                    '[placeholder="Add a title"]',
                    '[aria-label="Add a title"]',
                    'input[aria-label="Add a title"]',
                    '.ms-TextField-field',
                    'input.title',
                ]
                title_filled = False
                for sel in title_selectors:
                    try:
                        page.wait_for_selector(sel, timeout=5000)
                        page.fill(sel, "HireLogic Bot Test")
                        logger.info(f"[BotTrigger] Filled title with selector: {sel}")
                        title_filled = True
                        break
                    except Exception:
                        continue
                if not title_filled:
                    page.screenshot(path="/tmp/debug_07_title_fail.png")
                    raise Exception("Could not find title field on event form")

                # Add the bot as an attendee
                page.fill('[placeholder="Invite attendees"]', self.bot_email)
                page.keyboard.press("Enter")
                time.sleep(1)

                # Set location to Zoom URL
                try:
                    page.click('[aria-label="Search for a location"]', timeout=5000)
                    page.fill('[aria-label="Search for a location"]', self.zoom_url)
                except Exception:
                    try:
                        page.click('text=Add a location', timeout=5000)
                        page.fill('[placeholder="Search for a location"]', self.zoom_url)
                    except Exception:
                        logger.warning("[BotTrigger] Could not set location field")

                time.sleep(1)

                # Save the event
                page.click('[aria-label="Send"]', timeout=10000)
                page.wait_for_load_state("networkidle", timeout=15000)

                event_id = f"outlook-{int(invited_at)}"
                logger.info(f"[BotTrigger] Calendar event created, bot invited: {self.bot_email}")

            except Exception as e:
                logger.error(f"[BotTrigger] Error creating calendar event: {e}")
                raise
            finally:
                browser.close()

        return BotJobResult(
            platform="zoom",
            meeting_id=config.zoom.recurring_meeting_id,
            join_url=self.zoom_url,
            bot_email=self.bot_email,
            invited_at=invited_at,
            calendar_event_id=event_id,
            status="invited",
        )

    def get_participants(self, meeting_id: str) -> list[str]:
        """Fetch the live participant list for the recurring Zoom meeting."""
        import requests
        try:
            zoom_cfg = config.zoom
            resp = requests.post(
                "https://zoom.us/oauth/token",
                params={
                    "grant_type": "account_credentials",
                    "account_id": zoom_cfg.account_id,
                },
                auth=(zoom_cfg.client_id, zoom_cfg.client_secret),
                timeout=15,
            )
            resp.raise_for_status()
            token = resp.json()["access_token"]

            resp = requests.get(
                f"{zoom_cfg.api_base}/meetings/{meeting_id}/participants",
                headers={"Authorization": f"Bearer {token}"},
                timeout=15,
            )
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            return [p.get("name", "") for p in resp.json().get("participants", [])]
        except Exception as e:
            logger.warning(f"[BotTrigger] Could not fetch participants: {e}")
            return []
