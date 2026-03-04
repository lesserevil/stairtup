"""
Browser automation tests for verifying links work.
Uses Playwright to test navigation and link functionality.
"""

import pytest
from playwright.sync_api import sync_playwright


BASE_URL = "http://localhost:9754"


class TestLinks:
    """Test that all links on the site work correctly."""

    def test_index_page_loads(self):
        """Test that index page loads."""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"{BASE_URL}/")
            page.wait_for_load_state("networkidle")
            assert "Agent Company Swarm" in page.title()
            browser.close()

    def test_dashboard_navigation(self):
        """Test that we can navigate to dashboard."""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"{BASE_URL}/dashboard")
            page.wait_for_load_state("networkidle")
            assert "/dashboard" in page.url
            assert "CEO Dashboard" in page.title()
            browser.close()

    def test_health_endpoint(self):
        """Test that health endpoint works."""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            response = page.goto(f"{BASE_URL}/health")
            assert response.status == 200
            data = response.json()
            assert data.get("status") == "healthy"
            browser.close()

    def test_health_dependencies(self):
        """Test health/dependencies endpoint."""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            response = page.goto(f"{BASE_URL}/health/dependencies")
            assert response.status == 200
            data = response.json()
            assert "services" in data
            browser.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
