import requests
import logging
import base64
import re

logger = logging.getLogger(__name__)

class BrowserHandler:
    """Handles HTTP requests to fetch and render quiz pages (without actual browser)"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        if self.session:
            self.session.close()

    def get_rendered_content(self, url, wait_time=3):
        """
        Fetch URL content and decode any base64 encoded content

        Args:
            url: The URL to visit
            wait_time: Ignored (kept for compatibility)

        Returns:
            str: The HTML content with decoded base64
        """
        try:
            logger.info(f"Fetching URL: {url}")
            response = self.session.get(url, timeout=30)
            response.raise_for_status()

            html_content = response.text
            logger.info(f"Fetched page, content length: {len(html_content)}")

            # Decode base64 content if present (common in quiz pages)
            # Look for atob() patterns and decode them
            decoded_content = self._decode_base64_in_html(html_content)

            return decoded_content

        except Exception as e:
            logger.error(f"Error fetching page {url}: {e}", exc_info=True)
            raise

    def _decode_base64_in_html(self, html):
        """Decode base64 content embedded in HTML/JavaScript"""
        try:
            # Find atob() calls with base64 content
            pattern = r'atob\([`"\']([A-Za-z0-9+/=]+)[`"\']\)'
            matches = re.findall(pattern, html)

            result_html = html
            for base64_str in matches:
                try:
                    decoded = base64.b64decode(base64_str).decode('utf-8', errors='ignore')
                    logger.info(f"Decoded base64 content: {decoded[:200]}...")
                    # Add decoded content to HTML
                    result_html += f"\n<!-- Decoded Content -->\n{decoded}\n"
                except Exception as e:
                    logger.debug(f"Could not decode base64: {e}")

            return result_html

        except Exception as e:
            logger.error(f"Error decoding base64: {e}")
            return html

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
            response = self.session.get(url, timeout=60, stream=True)
            response.raise_for_status()

            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            logger.info(f"File downloaded successfully to: {save_path}")
            return save_path

        except Exception as e:
            logger.error(f"Error downloading file from {url}: {e}", exc_info=True)
            raise
