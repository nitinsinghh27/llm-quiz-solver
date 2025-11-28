import requests
import logging
import time
import re
import os
import hashlib
from bs4 import BeautifulSoup
from browser import BrowserHandler
from llm_client import LLMClient
from datetime import datetime

logger = logging.getLogger(__name__)

def compute_email_number(email):
    """Compute email number using SHA-1 hash (mimics JavaScript emailNumber())"""
    sha1_hash = hashlib.sha1(email.encode()).hexdigest()
    return int(sha1_hash[:4], 16)

class QuizSolver:
    """Main class for solving quiz questions"""

    def __init__(self):
        self.llm = LLMClient()
        self.start_time = None
        self.max_time = 180  # 3 minutes in seconds

    def solve_quiz_chain(self, initial_url, email, secret):
        """
        Solve a chain of quiz questions starting from the initial URL

        Args:
            initial_url: The first quiz URL
            email: Student email
            secret: Student secret

        Returns:
            dict: Final result
        """
        self.start_time = time.time()
        current_url = initial_url
        attempt = 0
        max_attempts = 5  # Limit to 5 attempts to avoid rate limiting

        logger.info(f"Starting quiz chain from: {initial_url}")

        while current_url and attempt < max_attempts:
            attempt += 1

            # Check if we're within time limit
            elapsed_time = time.time() - self.start_time
            if elapsed_time > self.max_time:
                logger.error(f"Time limit exceeded: {elapsed_time:.2f}s")
                break

            logger.info(f"Attempt {attempt}: Processing {current_url}")

            try:
                # Solve the current quiz
                result = self.solve_single_quiz(current_url, email, secret)

                if result.get('correct'):
                    logger.info(f"✓ Correct answer for {current_url}")
                    # Move to next URL if provided
                    current_url = result.get('url')
                    if not current_url:
                        logger.info("No more URLs, quiz chain completed!")
                        return result
                else:
                    logger.warning(f"✗ Incorrect answer: {result.get('reason')}")
                    # The response might still give us a next URL
                    next_url = result.get('url')
                    if next_url and next_url != current_url:
                        logger.info(f"Moving to next quiz despite error: {next_url}")
                        current_url = next_url
                    else:
                        logger.info("No new URL provided, retrying same quiz")
                        # Retry the same URL (the loop will continue)
                        time.sleep(1)  # Brief pause before retry

            except Exception as e:
                logger.error(f"Error solving quiz {current_url}: {e}", exc_info=True)
                break

        logger.info(f"Quiz chain ended after {attempt} attempts")
        return {"status": "completed", "attempts": attempt}

    def solve_single_quiz(self, quiz_url, email, secret):
        """
        Solve a single quiz question

        Args:
            quiz_url: The quiz URL
            email: Student email
            secret: Student secret

        Returns:
            dict: Response from submit endpoint
        """
        logger.info(f"Fetching quiz from: {quiz_url}")

        # Step 1: Render the page with a headless browser
        with BrowserHandler() as browser:
            html_content = browser.get_rendered_content(quiz_url)

        # Step 2: Parse the HTML to extract the question
        soup = BeautifulSoup(html_content, 'html.parser')

        # Extract cutoff value from HTML (if present in <span id="cutoff">)
        cutoff_value = None
        cutoff_span = soup.find('span', {'id': 'cutoff'})
        if cutoff_span:
            cutoff_text = cutoff_span.get_text().strip()
            if cutoff_text:
                try:
                    cutoff_value = int(cutoff_text)
                    logger.info(f"Extracted cutoff from HTML: {cutoff_value}")
                except (ValueError, AttributeError) as e:
                    logger.warning(f"Could not parse cutoff value: {e}")
            else:
                # Cutoff span is empty - it's populated by JavaScript emailNumber()
                # Compute it ourselves using the email from the URL
                from urllib.parse import urlparse, parse_qs
                parsed = urlparse(quiz_url)
                query_params = parse_qs(parsed.query)
                email = query_params.get('email', [None])[0]
                if email:
                    cutoff_value = compute_email_number(email)
                    logger.info(f"Computed cutoff from email {email}: {cutoff_value}")

        # Extract text content from the result/question div or body
        # Try multiple common div IDs used in quiz pages
        result_div = soup.find('div', {'id': 'result'}) or soup.find('div', {'id': 'question'})
        if result_div:
            question_text = result_div.get_text(strip=False)
        else:
            question_text = soup.get_text(strip=False)

        # If still empty, try to get from decoded content comments
        if not question_text.strip():
            # Look for decoded content in HTML comments
            decoded_match = re.search(r'<!-- Decoded Content -->\s*(.+?)(?=\n<!--|\Z)', html_content, re.DOTALL)
            if decoded_match:
                question_text = decoded_match.group(1).strip()

        logger.info(f"Extracted question text:\n{question_text}")

        # Step 3: Extract submit URL and any file URLs from the question
        submit_url = self.extract_submit_url(question_text, html_content, quiz_url)
        logger.info(f"Submit URL: {submit_url}")

        # Step 4: Check if there are any files to download
        file_urls = self.extract_file_urls(html_content)
        context = None
        media_files = []

        if file_urls:
            logger.info(f"Found {len(file_urls)} file(s) to process")
            processed = self.process_files(file_urls, quiz_url)
            context = processed['text']
            media_files = processed['media_files']

        # Step 5: Use LLM to solve the question OR process locally if cutoff is provided
        # If cutoff value was found in HTML and we have CSV data, process locally
        if cutoff_value is not None and context and 'CSV Data' in context:
            logger.info(f"Processing CSV locally with cutoff value: {cutoff_value}")
            try:
                # Parse the CSV from context
                import pandas as pd
                from io import StringIO
                # Extract CSV data from context
                csv_match = re.search(r'CSV Data:\n(.+?)(?=\n\n|$)', context, re.DOTALL)
                if csv_match:
                    csv_text = csv_match.group(1)
                    df = pd.read_csv(StringIO(csv_text), sep=r'\s+')  # Assuming space-separated
                    # Sum values >= cutoff (greater than or equal to)
                    filtered_values = df[df.iloc[:, 0] >= cutoff_value].iloc[:, 0]
                    result = int(filtered_values.sum())
                    formatted_answer = result
                    logger.info(f"CSV processing result: sum of {len(filtered_values)} values >= {cutoff_value} = {formatted_answer}")
                else:
                    logger.error("Could not extract CSV data from context")
                    formatted_answer = 0
            except Exception as e:
                logger.error(f"Error processing CSV with cutoff: {e}", exc_info=True)
                formatted_answer = 0

            # Clean up media files if any were downloaded
            for media_file in media_files:
                try:
                    if os.path.exists(media_file['path']):
                        os.remove(media_file['path'])
                        logger.info(f"Cleaned up media file: {media_file['path']}")
                except Exception as e:
                    logger.warning(f"Error cleaning up {media_file['path']}: {e}")

        elif media_files:
            # If we have media files but no cutoff in HTML, try to extract from audio
            logger.info("Processing audio file to extract code/cutoff value")
            # Get the code from audio
            audio_code = self.llm.solve_question(question_text, None, media_files)  # No CSV context
            logger.info(f"Extracted code from audio: {audio_code}")

            # Clean up media files after extraction
            for media_file in media_files:
                try:
                    if os.path.exists(media_file['path']):
                        os.remove(media_file['path'])
                        logger.info(f"Cleaned up media file: {media_file['path']}")
                except Exception as e:
                    logger.warning(f"Error cleaning up {media_file['path']}: {e}")

            # Now process the CSV with the extracted code
            if context and 'CSV Data' in context:
                logger.info(f"Processing CSV with cutoff value: {audio_code}")
                try:
                    cutoff = int(audio_code.strip())
                    # Parse the CSV from context
                    import pandas as pd
                    from io import StringIO
                    # Extract CSV data from context
                    csv_match = re.search(r'CSV Data:\n(.+?)(?=\n\n|$)', context, re.DOTALL)
                    if csv_match:
                        csv_text = csv_match.group(1)
                        df = pd.read_csv(StringIO(csv_text), sep=r'\s+')  # Assuming space-separated
                        # Sum values >= cutoff (greater than or equal to)
                        filtered_values = df[df.iloc[:, 0] >= cutoff].iloc[:, 0]
                        result = int(filtered_values.sum())
                        formatted_answer = result
                        logger.info(f"CSV processing result: sum of {len(filtered_values)} values >= {cutoff} = {formatted_answer}")
                    else:
                        formatted_answer = audio_code
                except Exception as e:
                    logger.error(f"Error processing CSV with audio code: {e}")
                    formatted_answer = audio_code
            else:
                formatted_answer = audio_code
        else:
            # Text-only quiz - use LLM normally
            raw_answer = self.llm.solve_question(question_text, context, media_files)
            formatted_answer = self.llm.extract_answer_format(question_text, raw_answer)

        logger.info(f"Formatted answer: {formatted_answer} (type: {type(formatted_answer).__name__})")

        # Step 7: Submit the answer
        result = self.submit_answer(submit_url, email, secret, quiz_url, formatted_answer)

        return result

    def extract_submit_url(self, text, html, base_url):
        """Extract the submit URL from the question text or HTML"""
        from urllib.parse import urljoin

        # Look for absolute URLs first
        patterns = [
            r'Post your answer to (https?://[^\s]+)',
            r'submit[^\s]* (https?://[^\s]+)',
            r'POST to (https?://[^\s]+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                url = match.group(1).rstrip('.,;:')
                return url

        # Look for relative URLs in HTML href attributes (e.g., <a href="/submit">)
        href_pattern = r'<a\s+href=["\']([^"\']+)["\'][^>]*>(/submit|submit)</a>'
        match = re.search(href_pattern, text, re.IGNORECASE)
        if match:
            relative_url = match.group(1)
            absolute_url = urljoin(base_url, relative_url)
            logger.info(f"Found relative URL in href '{relative_url}', converted to: {absolute_url}")
            return absolute_url

        # Look for relative URLs in text (e.g., "POST to /submit")
        relative_patterns = [
            r'POST[^\n]*to\s+(/[^\s<]+)',
            r'Post[^\n]*to\s+(/[^\s<]+)',
            r'submit[^\n]*to\s+(/[^\s<]+)',
        ]

        for pattern in relative_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                relative_url = match.group(1).rstrip('.,;:')
                absolute_url = urljoin(base_url, relative_url)
                logger.info(f"Found relative URL '{relative_url}', converted to: {absolute_url}")
                return absolute_url

        # Fallback: look for any absolute URL that looks like a submit endpoint
        urls = re.findall(r'https?://[^\s<>"{}|\\^`\[\]]+', text)
        for url in urls:
            if 'submit' in url.lower():
                return url.rstrip('.,;:')

        logger.warning("Could not find submit URL in question text")
        return None

    def extract_file_urls(self, html):
        """Extract file URLs (PDF, CSV, audio, video, etc.) and data source URLs from HTML"""
        soup = BeautifulSoup(html, 'html.parser')
        file_urls = []

        # Find all links (a tags)
        for link in soup.find_all('a', href=True):
            href = link['href']
            link_text = link.get_text().lower()

            # Check if it's a data file with extension
            if any(ext in href.lower() for ext in ['.pdf', '.csv', '.xlsx', '.json', '.txt', '.xml', '.mp3', '.wav', '.opus', '.ogg', '.m4a', '.mp4', '.webm']):
                file_urls.append(href)
            # Check if the question explicitly asks to scrape/fetch this URL
            elif any(keyword in link_text for keyword in ['data', 'scrape', 'fetch', 'get']):
                # Exclude submit/navigation links
                if 'submit' not in href.lower() and 'submit' not in link_text:
                    file_urls.append(href)

        # Also check for audio/video tags with src attributes
        for tag in soup.find_all(['audio', 'video']):
            if tag.get('src'):
                file_urls.append(tag['src'])

        return file_urls

    def process_files(self, file_urls, base_url=None):
        """
        Download and process data files

        Args:
            file_urls: List of file URLs
            base_url: Base URL for resolving relative URLs

        Returns:
            dict: Contains 'text' (str) for text context and 'files' (list) for audio/video file paths
        """
        context_parts = []
        media_files = []  # Store paths to audio/video files for multimodal LLM
        from urllib.parse import urljoin

        with BrowserHandler() as browser:
            for url in file_urls:
                try:
                    # Convert relative URLs to absolute
                    if base_url and not url.startswith('http'):
                        url = urljoin(base_url, url)
                        logger.info(f"Converted relative URL to: {url}")

                    # Check if URL has a known file extension
                    has_extension = any(ext in url.lower() for ext in ['.pdf', '.csv', '.xlsx', '.json', '.txt', '.xml', '.mp3', '.wav', '.opus', '.ogg', '.m4a', '.mp4', '.webm'])

                    if not has_extension:
                        # No file extension - check if it's a JavaScript-rendered page
                        # that requires email number computation
                        from urllib.parse import urlparse, parse_qs

                        parsed = urlparse(url)
                        query_params = parse_qs(parsed.query)
                        email = query_params.get('email', [None])[0]

                        # Check if this looks like demo-scrape-data pattern
                        if 'demo-scrape-data' in url and email:
                            logger.info(f"Computing secret code for demo-scrape-data with email: {email}")
                            secret_code = compute_email_number(email)
                            context_parts.append(f"Secret code from {url}: {secret_code}")
                            continue

                        # Otherwise, fetch as HTML and extract text
                        logger.info(f"Fetching HTML page: {url}")
                        html_content = browser.get_rendered_content(url)
                        soup = BeautifulSoup(html_content, 'html.parser')

                        # Extract text from decoded content or page body
                        decoded_match = re.search(r'<!-- Decoded Content -->\s*(.+?)(?=\n<!--|\Z)', html_content, re.DOTALL)
                        if decoded_match:
                            page_text = decoded_match.group(1).strip()
                        else:
                            # Get text from main content div or body
                            result_div = soup.find('div', {'id': 'question'}) or soup.find('div', {'id': 'result'})
                            if result_div:
                                page_text = result_div.get_text(strip=True)
                            else:
                                page_text = soup.get_text(strip=True)

                        context_parts.append(f"Page content from {url}:\n{page_text}")
                        continue

                    # Determine file type from extension
                    ext = url.split('.')[-1].split('?')[0].lower()  # Remove query params
                    filename = f"temp_file.{ext}"

                    # Download file
                    browser.download_file(url, filename)

                    # Process based on file type
                    if ext == 'csv':
                        import pandas as pd
                        df = pd.read_csv(filename)
                        context_parts.append(f"CSV Data:\n{df.to_string()}")

                    elif ext in ['xlsx', 'xls']:
                        import pandas as pd
                        # Read all sheets
                        excel_file = pd.ExcelFile(filename)
                        for sheet_name in excel_file.sheet_names:
                            df = pd.read_excel(filename, sheet_name=sheet_name)
                            context_parts.append(f"Excel Sheet '{sheet_name}':\n{df.to_string()}")

                    elif ext == 'json':
                        import json
                        with open(filename, 'r') as f:
                            data = json.load(f)
                        context_parts.append(f"JSON Data:\n{json.dumps(data, indent=2)}")

                    elif ext == 'txt':
                        with open(filename, 'r') as f:
                            content = f.read()
                        context_parts.append(f"Text File:\n{content}")

                    elif ext == 'pdf':
                        # Parse PDF file
                        from PyPDF2 import PdfReader
                        try:
                            reader = PdfReader(filename)
                            pdf_text = []
                            for page_num, page in enumerate(reader.pages, 1):
                                text = page.extract_text()
                                pdf_text.append(f"Page {page_num}:\n{text}")
                            context_parts.append(f"PDF Content:\n" + "\n\n".join(pdf_text))
                        except Exception as pdf_error:
                            logger.error(f"Error parsing PDF: {pdf_error}")
                            context_parts.append(f"PDF file downloaded but could not be parsed: {url}")

                    elif ext in ['mp3', 'wav', 'opus', 'ogg', 'm4a', 'mp4', 'webm']:
                        # Audio/Video file - save path for multimodal LLM processing
                        logger.info(f"Found media file: {filename}")
                        media_files.append({
                            'path': filename,
                            'type': 'audio' if ext in ['mp3', 'wav', 'opus', 'ogg', 'm4a'] else 'video',
                            'url': url
                        })
                        # Don't delete yet - LLM needs to access it
                        continue

                    # Clean up text-based files (but not media files)
                    if os.path.exists(filename) and ext not in ['mp3', 'wav', 'opus', 'ogg', 'm4a', 'mp4', 'webm']:
                        os.remove(filename)

                except Exception as e:
                    logger.error(f"Error processing file {url}: {e}")

        return {
            'text': "\n\n".join(context_parts) if context_parts else None,
            'media_files': media_files
        }

    def submit_answer(self, submit_url, email, secret, quiz_url, answer):
        """
        Submit answer to the endpoint

        Args:
            submit_url: Where to submit
            email: Student email
            secret: Student secret
            quiz_url: The quiz URL
            answer: The answer to submit

        Returns:
            dict: Response from server
        """
        if not submit_url:
            logger.error("No submit URL provided")
            return {"error": "No submit URL found"}

        payload = {
            "email": email,
            "secret": secret,
            "url": quiz_url,
            "answer": answer
        }

        try:
            logger.info(f"Submitting answer to: {submit_url}")
            logger.info(f"Payload: {payload}")

            response = requests.post(submit_url, json=payload, timeout=30)

            logger.info(f"Response status: {response.status_code}")
            logger.info(f"Response body: {response.text}")

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Submit failed with status {response.status_code}")
                return {"error": f"HTTP {response.status_code}", "correct": False}

        except Exception as e:
            logger.error(f"Error submitting answer: {e}", exc_info=True)
            return {"error": str(e), "correct": False}
