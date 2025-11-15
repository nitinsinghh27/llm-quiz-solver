from playwright.sync_api import sync_playwright
import logging
import time

logger = logging.getLogger(__name__)

class BrowserHandler:
    """Handles headless browser operations for rendering JavaScript-based quiz pages"""

    def __init__(self):
        self.playwright = None
        self.browser = None

    def __enter__(self):
        """Context manager entry"""
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=True)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()

    def get_rendered_content(self, url, wait_time=3):
        """
        Visit a URL with a headless browser and return the rendered HTML content

        Args:
            url: The URL to visit
            wait_time: Time to wait for JavaScript execution (seconds)

        Returns:
            str: The rendered HTML content
        """
        try:
            logger.info(f"Opening browser for URL: {url}")
            page = self.browser.new_page()

            # Set a reasonable timeout
            page.set_default_timeout(30000)  # 30 seconds

            # Navigate to the URL
            page.goto(url, wait_until='networkidle')

            # Wait for JavaScript to execute
            time.sleep(wait_time)

            # Get the rendered content
            content = page.content()

            # Also get the text content of specific elements if they exist
            try:
                # Try to get content from common result divs
                result_div = page.query_selector('#result')
                if result_div:
                    text_content = result_div.inner_text()
                    logger.info(f"Found #result div with content: {text_content[:200]}...")
            except Exception as e:
                logger.debug(f"Could not extract #result div: {e}")

            page.close()
            logger.info(f"Successfully rendered page, content length: {len(content)}")

            return content

        except Exception as e:
            logger.error(f"Error rendering page {url}: {e}", exc_info=True)
            raise

    def download_file(self, url, save_path):
        """
        Download a file from a URL

        Args:
            url: The URL of the file to download
            save_path: Where to save the file

        Returns:
            str: Path to the downloaded file
        """
        try:
            logger.info(f"Downloading file from: {url}")
            page = self.browser.new_page()

            # Start waiting for download
            with page.expect_download() as download_info:
                page.goto(url)

            download = download_info.value
            download.save_as(save_path)

            page.close()
            logger.info(f"File downloaded successfully to: {save_path}")

            return save_path

        except Exception as e:
            logger.error(f"Error downloading file from {url}: {e}", exc_info=True)
            raise
