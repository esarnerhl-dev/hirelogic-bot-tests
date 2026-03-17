"""
tests/conftest.py
Minimal pytest configuration for the simplified HireLogic bot join test.
No meeting creation needed — we use a recurring Zoom meeting.
"""

import pytest
import logging
from config.settings import config

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def platform():
    return "zoom"
