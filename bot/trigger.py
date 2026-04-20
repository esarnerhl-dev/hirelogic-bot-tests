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
                page.wait_for_load_state("domcontentloaded", timeout=15000)
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
                page.wait_for_load_state("domcontentloaded", timeout=15000)
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
                page.wait_for_load_state("domcontentloaded", timeout=30000)
                time.sleep(3)
                logger.info(f"[BotTrigger] Logged in successfully, on page: {page.url}")

                # Dismiss popups before interacting (timezone dialog, reminders)
                try:
                    not_now = page.locator('button:has-text("Not now")')
                    if not_now.is_visible(timeout=2000):
                        not_now.click()
                        logger.info("[BotTrigger] Dismissed timezone dialog")
                        time.sleep(1)
                except Exception:
                    pass
                try:
                    dismiss_all = page.locator('button:has-text("Dismiss all")')
                    if dismiss_all.is_visible(timeout=2000):
                        dismiss_all.click()
                        logger.info("[BotTrigger] Dismissed reminders")
                        time.sleep(1)
                except Exception:
                    pass

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
                page.wait_for_load_state("domcontentloaded", timeout=15000)
                time.sleep(2)
                page.screenshot(path="/tmp/debug_05_after_new_event.png")
                logger.info(f"[BotTrigger] URL after new event click: {page.url}")

                # Step 2: Fill in the new event form
                logger.info("[BotTrigger] Filling in calendar event form...")
                time.sleep(3)
                page.screenshot(path="/tmp/debug_06_form.png")

                # Dump all input fields visible on the page for debugging
                inputs = page.eval_on_selector_all(
                    "input, textarea, [contenteditable]",
                    """els => els.map(e => ({
                        tag: e.tagName,
                        type: e.type || '',
                        placeholder: e.placeholder || '',
                        ariaLabel: e.getAttribute('aria-label') || '',
                        id: e.id || '',
                        className: e.className || '',
                        visible: e.offsetParent !== null
                    }))"""
                )
                for i, inp in enumerate(inputs):
                    logger.info(f"[BotTrigger] Input {i}: {inp}")

                # Try filling the first visible input that looks like a title field
                title_filled = False
                for i, inp in enumerate(inputs):
                    if inp.get('visible') and any(x in (inp.get('placeholder','') + inp.get('ariaLabel','')).lower()
                                                   for x in ['title', 'subject', 'add']):
                        try:
                            sel = f"input:nth-of-type({i+1})"
                            if inp.get('id'):
                                sel = f"#{inp['id']}"
                            elif inp.get('placeholder'):
                                sel = f'[placeholder="{inp["placeholder"]}"]'
                            elif inp.get('ariaLabel'):
                                sel = f'[aria-label="{inp["ariaLabel"]}"]'
                            page.fill(sel, "HireLogic Bot Test")
                            logger.info(f"[BotTrigger] Filled title with: {sel}")
                            title_filled = True
                            break
                        except Exception as e:
                            logger.warning(f"[BotTrigger] Failed to fill with {sel}: {e}")

                if not title_filled:
                    # Last resort: click the first input and type
                    try:
                        visible_inputs = page.locator("input:visible").all()
                        if visible_inputs:
                            visible_inputs[0].click()
                            page.keyboard.type("HireLogic Bot Test")
                            logger.info("[BotTrigger] Filled title via first visible input")
                            title_filled = True
                    except Exception as e:
                        logger.warning(f"[BotTrigger] Last resort failed: {e}")

                page.screenshot(path="/tmp/debug_07_after_title.png")
                logger.info(f"[BotTrigger] Title filled: {title_filled}")

                # Add the bot as an attendee using force=True
                page.click('[aria-label="Invite required attendees"]', force=True, timeout=10000)
                time.sleep(0.5)
                page.keyboard.type(self.bot_email)
                time.sleep(1)
                page.keyboard.press("Enter")
                time.sleep(2)
                logger.info(f"[BotTrigger] Added attendee: {self.bot_email}")

                # Set location using force=True
                page.click('#location-suggestions-picker-input', force=True, timeout=10000)
                time.sleep(0.5)
                page.keyboard.type(self.zoom_url)
                time.sleep(1)
                page.keyboard.press("Escape")
                logger.info(f"[BotTrigger] Set location to Zoom URL")

                # Click "More options" to open the full event form with date/time fields
                try:
                    more_options = page.locator('button:has-text("More options")')
                    if more_options.is_visible(timeout=3000):
                        more_options.click()
                        page.wait_for_load_state("domcontentloaded", timeout=15000)
                        time.sleep(2)
                        logger.info("[BotTrigger] Opened full event form via More options")
                except Exception as e:
                    logger.warning(f"[BotTrigger] Could not open More options: {e}")

                # Set start time - compute 5 minutes from now in UTC
                from datetime import datetime, timedelta, timezone
                start_time = datetime.now(timezone.utc) + timedelta(minutes=5)
                start_date_str = start_time.strftime("%-m/%-d/%Y")
                start_time_str = start_time.strftime("%-I:%M %p")
                logger.info(f"[BotTrigger] Setting start time to {start_date_str} {start_time_str}")

                # Log all visible inputs to find date/time field names
                try:
                    all_inputs = page.evaluate("""
                        () => Array.from(document.querySelectorAll('input'))
                            .filter(i => i.offsetParent !== null)
                            .map(i => ({label: i.getAttribute('aria-label'), type: i.type, placeholder: i.placeholder}))
                    """)
                    logger.info(f"[BotTrigger] All visible inputs: {all_inputs}")
                except Exception:
                    pass

                try:
                    for date_sel in ['input[aria-label="Start date"]', 'input[aria-label="start date"]']:
                        if page.locator(date_sel).count() > 0:
                            page.locator(date_sel).first.click(force=True, timeout=3000)
                            time.sleep(0.3)
                            page.keyboard.press("Control+a")
                            page.keyboard.type(start_date_str)
                            page.keyboard.press("Tab")
                            time.sleep(0.3)
                            logger.info(f"[BotTrigger] Set date: {start_date_str} using {date_sel}")
                            break
                    else:
                        logger.warning("[BotTrigger] Start date field not found")

                    for time_sel in ['input[aria-label="Start time"]', 'input[aria-label="start time"]']:
                        if page.locator(time_sel).count() > 0:
                            page.locator(time_sel).first.click(force=True, timeout=3000)
                            time.sleep(0.3)
                            page.keyboard.press("Control+a")
                            page.keyboard.type(start_time_str)
                            page.keyboard.press("Enter")
                            time.sleep(0.5)
                            logger.info(f"[BotTrigger] Set time: {start_time_str} using {time_sel}")
                            break
                    else:
                        logger.warning("[BotTrigger] Start time field not found")
                except Exception as e:
                    logger.warning(f"[BotTrigger] Could not set start time: {e}")

                page.screenshot(path="/tmp/debug_08_before_save.png")
                time.sleep(1)

                # Save the event — click Send and verify the form closes
                url_before = page.url
                save_selectors = [
                    '[aria-label="Send"]',
                    'button:has-text("Send")',
                    '[aria-label="Save"]',
                    'button:has-text("Save")',
                ]
                sent = False
                for sel in save_selectors:
                    try:
                        if page.locator(sel).is_visible(timeout=3000):
                            page.click(sel)
                            logger.info(f"[BotTrigger] Clicked save/send: {sel}")
                            sent = True
                            break
                    except Exception:
                        continue

                # Handle any "send anyway" confirmation dialog (e.g. past time warning)
                time.sleep(2)
                for confirm_sel in ['button:has-text("Send anyway")', 'button:has-text("OK")', 'button:has-text("Yes")']:
                    try:
                        if page.locator(confirm_sel).is_visible(timeout=2000):
                            page.click(confirm_sel)
                            logger.info(f"[BotTrigger] Confirmed dialog: {confirm_sel}")
                            break
                    except Exception:
                        continue

                page.wait_for_load_state("domcontentloaded", timeout=15000)
                page.screenshot(path="/tmp/debug_09_after_save.png")
                logger.info(f"[BotTrigger] URL after save: {page.url} (was: {url_before})")

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

    def _get_zoom_token(self) -> str:
        """Get a Zoom OAuth token."""
        import requests
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
        return resp.json()["access_token"]

    def get_participants(self, meeting_id: str) -> list[str]:
        """
        Fetch the participant list for the meeting.
        Uses /users/{host}/meetings?type=live to find the active meeting instance,
        then /meetings/{id}/participants to get attendees.
        """
        import requests
        zoom_cfg = config.zoom
        try:
            token = self._get_zoom_token()
            headers = {"Authorization": f"Bearer {token}"}

            # List live meetings for the host to confirm the meeting is running
            resp_list = requests.get(
                f"{zoom_cfg.api_base}/users/{zoom_cfg.host_email}/meetings",
                headers=headers,
                params={"type": "live"},
                timeout=15,
            )
            if resp_list.ok:
                live = resp_list.json().get("meetings", [])
                logger.info(f"[BotTrigger] Host live meetings: {[(m.get('id'), m.get('topic')) for m in live]}")

            # Try getting participants directly
            resp = requests.get(
                f"{zoom_cfg.api_base}/meetings/{meeting_id}/participants",
                headers=headers,
                timeout=15,
            )
            logger.info(f"[BotTrigger] Participants response: {resp.status_code} {resp.text[:300]}")
            if resp.ok:
                names = [p.get("name", "") or p.get("user_name", "") 
                         for p in resp.json().get("participants", [])]
                logger.info(f"[BotTrigger] Participants: {names}")
                return names

            return []

        except Exception as e:
            logger.warning(f"[BotTrigger] Could not fetch participants: {e}")
            return []
