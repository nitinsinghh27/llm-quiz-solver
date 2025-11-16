import requests
import logging
import time
import re
import os
from bs4 import BeautifulSoup
from browser import BrowserHandler
from llm_client import LLMClient
from datetime import datetime

logger = logging.getLogger(__name__)

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
        max_attempts = 20  # Prevent infinite loops

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

        # Extract text content from the result div or body
        result_div = soup.find('div', {'id': 'result'})
        if result_div:
            question_text = result_div.get_text(strip=False)
        else:
            question_text = soup.get_text(strip=False)

        logger.info(f"Extracted question text:\n{question_text}")

        # Step 3: Extract submit URL and any file URLs from the question
        submit_url = self.extract_submit_url(question_text, html_content, quiz_url)
        logger.info(f"Submit URL: {submit_url}")

        # Step 4: Check if there are any files to download
        file_urls = self.extract_file_urls(html_content)
        context = None

        if file_urls:
            logger.info(f"Found {len(file_urls)} file(s) to process")
            context = self.process_files(file_urls)

        # Step 5: Use LLM to solve the question
        raw_answer = self.llm.solve_question(question_text, context)

        # Step 6: Format the answer appropriately
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

        # Look for relative URLs (e.g., "POST to /submit")
        relative_patterns = [
            r'POST[^\n]*to\s+(/[^\s]+)',
            r'Post[^\n]*to\s+(/[^\s]+)',
            r'submit[^\n]*to\s+(/[^\s]+)',
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
        """Extract file URLs (PDF, CSV, etc.) from HTML"""
        soup = BeautifulSoup(html, 'html.parser')
        file_urls = []

        # Find all links
        for link in soup.find_all('a', href=True):
            href = link['href']
            # Check if it's a data file
            if any(ext in href.lower() for ext in ['.pdf', '.csv', '.xlsx', '.json', '.txt', '.xml']):
                file_urls.append(href)

        return file_urls

    def process_files(self, file_urls):
        """
        Download and process data files

        Args:
            file_urls: List of file URLs

        Returns:
            str: Processed file content as context for LLM
        """
        context_parts = []

        with BrowserHandler() as browser:
            for url in file_urls:
                try:
                    # Determine file type
                    ext = url.split('.')[-1].lower()
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

                    # Clean up
                    if os.path.exists(filename):
                        os.remove(filename)

                except Exception as e:
                    logger.error(f"Error processing file {url}: {e}")

        return "\n\n".join(context_parts) if context_parts else None

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
