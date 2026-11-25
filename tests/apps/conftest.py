"""Shared fixtures for Apps tests."""

from contextlib import contextmanager

import pytest


@pytest.fixture
def dashboard_campaign(tmp_path):
    from tests.fixtures.dashboard_experiments import build

    build(tmp_path)
    return tmp_path


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
