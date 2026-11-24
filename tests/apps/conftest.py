"""Browser setup shared by Apps UI tests."""

from contextlib import contextmanager

import pytest


@contextmanager
def _chromium(**launch_options):
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as driver:
        instance = driver.chromium.launch(**launch_options)
        try:
            yield instance
        finally:
            instance.close()


@pytest.fixture
def browser():
    with _chromium() as instance:
        yield instance


@pytest.fixture(scope="module")
def cpu_browser():
    with _chromium(args=["--disable-gpu"]) as instance:
        yield instance
