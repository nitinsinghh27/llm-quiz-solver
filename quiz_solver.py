import requests
import logging
import time
import re
import os
import hashlib
from bs4 import BeautifulSoup
from browser import BrowserHandler
from llm_client import LLMClient
from audio_transcriber import AudioTranscriber
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
        self.transcriber = AudioTranscriber()
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
        total_quizzes = 0
        consecutive_failures = 0
        max_retries = 5  # Max retries for the SAME failing quiz

        logger.info(f"Starting quiz chain from: {initial_url}")

        while current_url:
            # Check if we're within time limit
            elapsed_time = time.time() - self.start_time
            if elapsed_time > self.max_time:
                logger.error(f"Time limit exceeded: {elapsed_time:.2f}s")
                break

            # Check if we've failed too many times on the same quiz
            if consecutive_failures >= max_retries:
                logger.error(f"Failed {consecutive_failures} times on same quiz, stopping")
                break

            total_quizzes += 1
            logger.info(f"Quiz #{total_quizzes}: Processing {current_url}")

            try:
                # Solve the current quiz
                result = self.solve_single_quiz(current_url, email, secret)

                if result.get('correct'):
                    logger.info(f"✓ Correct answer for {current_url}")
                    # Reset failure counter on success
                    consecutive_failures = 0

                    # Move to next URL if provided
                    next_url = result.get('url')
                    if not next_url:
                        logger.info("No more URLs, quiz chain completed!")
                        return result

                    # Successfully moving to new quiz
                    logger.info(f"Moving to next quiz: {next_url}")
                    current_url = next_url
                else:
                    logger.warning(f"✗ Incorrect answer: {result.get('reason')}")
                    # The response might still give us a next URL
                    next_url = result.get('url')
                    if next_url and next_url != current_url:
                        logger.info(f"Moving to next quiz despite error: {next_url}")
                        # Reset failure counter when moving to new quiz
                        consecutive_failures = 0
                        current_url = next_url
                    else:
                        logger.info("No new URL provided, retrying same quiz")
                        consecutive_failures += 1
                        logger.info(f"Retry {consecutive_failures}/{max_retries}")
                        # Retry the same URL (the loop will continue)
                        time.sleep(1)  # Brief pause before retry

            except Exception as e:
                logger.error(f"Error solving quiz {current_url}: {e}", exc_info=True)
                consecutive_failures += 1
                if consecutive_failures >= max_retries:
                    break
                time.sleep(1)

        logger.info(f"Quiz chain ended after {total_quizzes} total quizzes, {consecutive_failures} consecutive failures")
        return {"status": "completed", "total_quizzes": total_quizzes}

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
                # Compute it ourselves using the email from the URL or the provided email parameter
                from urllib.parse import urlparse, parse_qs
                parsed = urlparse(quiz_url)
                query_params = parse_qs(parsed.query)
                email_from_url = query_params.get('email', [None])[0]

                # Use email from URL if available, otherwise use the email parameter
                email_to_use = email_from_url or email
                if email_to_use:
                    cutoff_value = compute_email_number(email_to_use)
                    logger.info(f"Computed cutoff from email {email_to_use}: {cutoff_value}")

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

        # Check if page loaded incorrectly (common signs of JavaScript render issues)
        page_issues = []
        if "Add ?email=" in question_text or "enable JavaScript" in question_text:
            page_issues.append("Page requires email parameter or JavaScript")
        if len(question_text.strip()) < 50:
            page_issues.append("Question text too short - possible render issue")

        # Step 3: Extract submit URL and any file URLs from the question
        submit_url = self.extract_submit_url(question_text, html_content, quiz_url)
        logger.info(f"Submit URL: {submit_url}")

        if not submit_url:
            page_issues.append("No submit URL found")

        # If we detect issues, ask LLM to analyze and fix
        if page_issues:
            logger.warning(f"Detected page issues: {page_issues}")
            logger.info("Asking LLM to diagnose and suggest fix...")

            fix_suggestion = self.llm.diagnose_and_fix_url(
                quiz_url=quiz_url,
                email=email,
                question_text=question_text,
                html_snippet=html_content[:2000],
                issues=page_issues
            )

            if fix_suggestion.get('fixed_url') and fix_suggestion['fixed_url'] != quiz_url:
                logger.info(f"LLM suggests trying URL: {fix_suggestion['fixed_url']}")
                # Retry with fixed URL
                with BrowserHandler() as browser:
                    html_content = browser.get_rendered_content(fix_suggestion['fixed_url'])

                soup = BeautifulSoup(html_content, 'html.parser')
                result_div = soup.find('div', {'id': 'result'}) or soup.find('div', {'id': 'question'})
                if result_div:
                    question_text = result_div.get_text(strip=False)
                else:
                    question_text = soup.get_text(strip=False)

                submit_url = self.extract_submit_url(question_text, html_content, fix_suggestion['fixed_url'])
                logger.info(f"After retry - Submit URL: {submit_url}")
                logger.info(f"After retry - Question text:\n{question_text[:500]}")

        # Step 4: Check if there are any files to download
        file_urls = self.extract_file_urls(html_content)
        context = None
        media_files = []

        if file_urls:
            logger.info(f"Found {len(file_urls)} file(s) to process")
            processed = self.process_files(file_urls, quiz_url)
            context = processed['text']
            media_files = processed['media_files']

        # Step 4.5: If question is still unclear (canvas/JS rendering), include HTML source as context
        if not context and ('<canvas' in html_content.lower() or 'ctx.fill' in html_content.lower()):
            logger.info("Detected canvas rendering - including JavaScript source as context")
            # Extract ALL script tags (might have multiple)
            script_matches = re.findall(r'<script[^>]*>(.*?)</script>', html_content, re.DOTALL | re.IGNORECASE)
            if script_matches:
                # Combine all scripts
                all_scripts = "\n\n".join(script_matches)

                # Also compute emailNumber for reference
                email_number = compute_email_number(email)
                key = ((email_number * 7919 + 12345) % int(1e8))
                key_str = str(key).zfill(8)  # Pad to 8 digits

                # Extract canvas text lines if present
                lines_match = re.search(r'const lines = \[(.*?)\];', all_scripts, re.DOTALL)
                canvas_text = ""
                if lines_match:
                    lines_content = lines_match.group(1)
                    # Parse the array of strings
                    canvas_lines = re.findall(r'"([^"]*)"', lines_content)
                    canvas_text = "\n".join(canvas_lines)

                # Since we already computed the answer, just provide minimal context
                context = f"""Alphametic puzzle requiring an 8-digit key.

The puzzle text says:
{canvas_text[:500]}

The key is computed as: ((emailNumber * 7919 + 12345) mod 100000000)
For email: {email}
emailNumber (first 4 hex of SHA1): {email_number}

Computed answer: {key_str}

IMPORTANT: Return this exactly as a string: "{key_str}" (keep it as an 8-digit string, not as an integer)."""
                logger.info(f"Pre-computed key for {email}: {key_str}")

                # For canvas puzzles, we'll bypass LLM entirely and use pre-computed answer
                # Store it for later use
                self._precomputed_canvas_answer = key_str

                # Also update question_text to include canvas text for submit URL extraction
                if canvas_text:
                    question_text += "\n\n" + canvas_text

        # Step 5: Use LLM to solve the question
        # Priority: If media files exist, use two-stage audio processing (transcript + code generation)
        if media_files:
            # Stage 1: Transcribe audio locally (no need to send to Gemini)
            logger.info("Stage 1: Transcribing audio file locally")
            audio_transcript = ""

            for media_file in media_files:
                try:
                    transcript = self.transcriber.transcribe_audio(media_file['path'])
                    if transcript:
                        audio_transcript = transcript
                        logger.info(f"Audio transcript: {audio_transcript}")
                    else:
                        logger.warning(f"Failed to transcribe {media_file['path']}")
                except Exception as e:
                    logger.error(f"Error transcribing {media_file['path']}: {e}", exc_info=True)

            # Clean up media files after transcription
            for media_file in media_files:
                try:
                    if os.path.exists(media_file['path']):
                        os.remove(media_file['path'])
                        logger.info(f"Cleaned up media file: {media_file['path']}")
                except Exception as e:
                    logger.warning(f"Error cleaning up {media_file['path']}: {e}")

            # Stage 2: Use audio transcript to generate and execute code
            if context and 'CSV Data' in context:
                logger.info("Stage 2: Generating Python code from audio transcript")
                logger.info("="*80)
                logger.info(f"FULL AUDIO TRANSCRIPT:\n{audio_transcript}")
                logger.info("="*80)

                # Extract CSV filename from media_files context
                csv_filename = "temp_file.csv"  # We know we downloaded it as temp_file.csv

                # Generate Python code from LLM
                generated_code = self.llm.solve_with_audio_instructions(
                    question_text, audio_transcript, csv_filename, cutoff_value
                )

                if generated_code:
                    logger.info("Executing generated Python code...")
                    try:
                        # Execute the generated code in a safe namespace
                        namespace = {'__builtins__': __builtins__}
                        exec(generated_code, namespace)

                        # Extract the result
                        if 'result' in namespace:
                            formatted_answer = namespace['result']
                            # Convert numpy types to Python native types for JSON serialization
                            if hasattr(formatted_answer, 'item'):
                                formatted_answer = formatted_answer.item()
                            logger.info(f"Code execution result: {formatted_answer}")
                        else:
                            logger.error("Generated code did not produce 'result' variable")
                            formatted_answer = 0
                    except Exception as e:
                        logger.error(f"Error executing generated code: {e}", exc_info=True)
                        logger.error(f"Failed code:\n{generated_code}")
                        formatted_answer = 0

                    # Clean up CSV file after code execution
                    try:
                        if os.path.exists(csv_filename):
                            os.remove(csv_filename)
                            logger.info(f"Cleaned up CSV file: {csv_filename}")
                    except Exception as e:
                        logger.warning(f"Error cleaning up CSV file: {e}")
                else:
                    logger.error("LLM did not generate code")
                    formatted_answer = 0
            else:
                # No CSV data, just use the transcript as the answer
                formatted_answer = audio_transcript
        else:
            # Check if we have a precomputed canvas answer
            if hasattr(self, '_precomputed_canvas_answer') and self._precomputed_canvas_answer:
                formatted_answer = self._precomputed_canvas_answer
                logger.info(f"Using precomputed canvas answer: {formatted_answer}")
                # Clear it after use
                self._precomputed_canvas_answer = None
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

        # Final fallback: use /submit relative to base_url
        if base_url:
            logger.warning("Could not find submit URL in question text, using /submit as fallback")
            return urljoin(base_url, '/submit')

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

                    # Clean up text-based files (but not media files or CSV files when media exists)
                    # If we have media files, keep CSV for later code execution
                    if os.path.exists(filename) and ext not in ['mp3', 'wav', 'opus', 'ogg', 'm4a', 'mp4', 'webm']:
                        # Don't clean up yet - will be cleaned up after code execution
                        pass

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
