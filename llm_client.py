from openai import OpenAI
import logging
from config import Config
import google.generativeai as genai

logger = logging.getLogger(__name__)

# Configure Gemini for multimodal support
genai.configure(api_key=Config.AIPIPE_API_KEY)

class LLMClient:
    """Handles interaction with LLM API (AIPIPE or OpenAI) for solving quiz questions"""

    def __init__(self):
        # Initialize OpenAI client with Gemini endpoint
        self.client = OpenAI(
            api_key=Config.AIPIPE_API_KEY,
            base_url=Config.AIPIPE_BASE_URL
        )
        self.model = "gemini-2.5-flash"  # Using Gemini 2.5 Flash (stable)

    def solve_question(self, question_text, context=None, media_files=None):
        """
        Use LLM to solve a quiz question

        Args:
            question_text: The question text from the quiz page
            context: Optional additional context (e.g., data file contents)
            media_files: Optional list of media file dicts with 'path', 'type', 'url'

        Returns:
            str: The LLM's answer
        """
        try:
            logger.info(f"Sending question to LLM: {question_text[:200]}...")
            if media_files:
                logger.info(f"Including {len(media_files)} media file(s)")

            # Build the prompt - simplified for media files to avoid token limits
            if media_files and len(media_files) > 0:
                # Request full transcript for audio files
                system_prompt = """Transcribe this audio file completely and accurately. Provide the full transcript of everything spoken."""
                user_prompt = "Please provide a complete transcript of the audio."
            else:
                system_prompt = """You are a data analysis and puzzle-solving expert helping to solve quiz questions.
The questions involve data sourcing, preparation, analysis, visualization, logic puzzles, and API calls.

For API-related questions:
- If the question asks you to call an API, generate Python code using requests library
- Include proper authentication (email, secret as query parameters or headers)
- Parse the JSON response and perform required calculations
- Store the final answer in a variable called 'result'

For alphametic puzzles:
- Read the JavaScript code to understand the puzzle
- Extract the equation (e.g., FORK + LIME = result)
- Find the emailNumber calculation
- Calculate the key using: ((emailNumber * 7919 + 12345) mod 1e8)
- Convert the key to digits and map them to the required letter sequence

Instructions:
1. Read the question and context carefully (including any JavaScript code)
2. If the question requires calling an API or performing computation, generate Python code
3. For API calls, use requests library with proper parameters
4. If data or files are mentioned, they will be provided in the context
5. If audio/video files are provided, listen/watch them carefully to extract information
6. Perform the required analysis or solve the puzzle
7. If you need to execute code to get the answer, return Python code with result variable
8. Otherwise, return ONLY the final answer in the format requested

Code generation rules:
- If question mentions "call the API" or "API endpoint", generate Python code
- Use requests.get() or requests.post() as appropriate
- Include email and secret parameters
- Store final answer in 'result' variable
- Return ONLY Python code, no markdown blocks

Answer format:
- For numerical answers, return just the number
- For text answers, return just the text
- For boolean answers, return true or false
- Be precise and accurate

Do not include explanations unless specifically asked."""

                user_prompt = f"Question:\n{question_text}"

                if context:
                    user_prompt += f"\n\nContext/Data:\n{context}"

            # Use Gemini native API for multimodal content (better audio support)
            if media_files and len(media_files) > 0:
                logger.info("Using Gemini native API for multimodal content")

                # Upload files to Gemini
                uploaded_files = []
                for media_file in media_files:
                    try:
                        logger.info(f"Uploading {media_file['path']} to Gemini...")
                        uploaded_file = genai.upload_file(media_file['path'])
                        uploaded_files.append(uploaded_file)
                        logger.info(f"Uploaded: {uploaded_file.name}")
                    except Exception as e:
                        logger.error(f"Error uploading {media_file['path']}: {e}")

                # Build prompt with uploaded files
                # Use gemini-2.5-flash for multimodal (audio/video) support
                model = genai.GenerativeModel(model_name="gemini-2.5-flash")

                # Create content parts: text prompt + uploaded files
                prompt_parts = [f"{system_prompt}\n\n{user_prompt}"]
                prompt_parts.extend(uploaded_files)

                # Generate response with safety settings
                response = model.generate_content(
                    prompt_parts,
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.1,
                        max_output_tokens=2000,  # Increased to handle full transcripts
                    ),
                    safety_settings={
                        genai.types.HarmCategory.HARM_CATEGORY_HARASSMENT: genai.types.HarmBlockThreshold.BLOCK_NONE,
                        genai.types.HarmCategory.HARM_CATEGORY_HATE_SPEECH: genai.types.HarmBlockThreshold.BLOCK_NONE,
                        genai.types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: genai.types.HarmBlockThreshold.BLOCK_NONE,
                        genai.types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: genai.types.HarmBlockThreshold.BLOCK_NONE,
                    }
                )

                # Check if response was blocked or empty
                if not response.candidates or not response.candidates[0].content.parts:
                    finish_reason = response.candidates[0].finish_reason if response.candidates else 'No candidates'
                    logger.error(f"Gemini response was blocked or empty. Finish reason: {finish_reason}")
                    logger.error(f"Full response: {response}")
                    # Try to extract any feedback or prompt feedback
                    if hasattr(response, 'prompt_feedback'):
                        logger.error(f"Prompt feedback: {response.prompt_feedback}")

                    # If finish_reason is MAX_TOKENS, it means we hit the limit but there might be partial content
                    # However, without content.parts, we can't extract anything
                    return ""

                answer = response.text.strip()
                logger.info(f"LLM response: {answer}")

                # Clean up uploaded files
                for uploaded_file in uploaded_files:
                    try:
                        genai.delete_file(uploaded_file.name)
                        logger.info(f"Deleted uploaded file: {uploaded_file.name}")
                    except:
                        pass

                return answer

            else:
                # Use OpenAI-compatible API for text-only queries
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]

                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.1,  # Low temperature for more deterministic answers
                    max_tokens=2000
                )

                # Handle None response (safety filters, refusals, etc.)
                content = response.choices[0].message.content
                if content is None:
                    logger.warning("LLM returned None content (possibly safety filter)")
                    # Try to get refusal reason if available
                    if hasattr(response.choices[0].message, 'refusal') and response.choices[0].message.refusal:
                        logger.warning(f"Refusal reason: {response.choices[0].message.refusal}")
                    return ""

                answer = content.strip()
                logger.info(f"LLM response: {answer}")

                return answer

        except Exception as e:
            logger.error(f"Error calling LLM API: {e}", exc_info=True)
            raise

    def solve_with_audio_instructions(self, question_text, audio_transcript, csv_filename=None, cutoff_value=None):
        """
        Use audio transcript to generate Python code that solves the problem

        Args:
            question_text: The question text from the quiz page
            audio_transcript: The full transcript from audio file
            csv_filename: Name of the CSV file to process
            cutoff_value: The cutoff value (if applicable)

        Returns:
            str: Python code to execute that will solve the problem
        """
        try:
            logger.info(f"Generating code from audio instructions: {audio_transcript[:200]}...")

            system_prompt = """You are a Python code generator for data analysis tasks. You will receive:
1. Audio transcript with instructions on what to do with data
2. Question text
3. CSV filename (if applicable)
4. Cutoff value (if applicable)

Generate ONLY executable Python code that:
- Reads the CSV file using pandas with header=None (CSV has NO header row)
- Follows the instructions from the audio transcript
- Stores the final answer in a variable called 'result'
- Does NOT print anything

Return ONLY the Python code, no explanations, no markdown formatting, no ```python blocks."""

            user_prompt = f"""Audio Instructions:
{audio_transcript}

Question:
{question_text}"""

            if csv_filename:
                user_prompt += f"\n\nCSV File: {csv_filename}"

            if cutoff_value is not None:
                user_prompt += f"\nCutoff Value: {cutoff_value}"

            user_prompt += "\n\nGenerate Python code that solves this problem. The code should read the CSV file and store the final answer in a variable called 'result'."

            # Use OpenAI-compatible API for text-only queries
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]

            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.1,
                max_tokens=2000
            )

            content = response.choices[0].message.content
            if content is None:
                logger.warning("LLM returned None content (possibly safety filter)")
                if hasattr(response.choices[0].message, 'refusal') and response.choices[0].message.refusal:
                    logger.warning(f"Refusal reason: {response.choices[0].message.refusal}")
                return ""

            code = content.strip()
            # Remove markdown code blocks if present
            if code.startswith('```python'):
                code = code[len('```python'):].strip()
            if code.startswith('```'):
                code = code[3:].strip()
            if code.endswith('```'):
                code = code[:-3].strip()

            logger.info(f"Generated code:\n{code}")
            return code

        except Exception as e:
            logger.error(f"Error generating code from audio instructions: {e}", exc_info=True)
            raise

    def extract_answer_format(self, question_text, raw_answer):
        """
        Parse the raw LLM answer into the correct format based on the question

        Args:
            question_text: The original question
            raw_answer: The raw answer from the LLM

        Returns:
            Formatted answer (int, float, str, bool, or dict)
        """
        try:
            # Try to detect if answer should be a number
            if any(keyword in question_text.lower() for keyword in ['sum', 'count', 'total', 'average', 'mean', 'how many']):
                try:
                    # Try integer first
                    if '.' not in raw_answer:
                        return int(raw_answer.strip())
                    else:
                        return float(raw_answer.strip())
                except ValueError:
                    pass

            # Try to detect if answer should be a boolean
            if raw_answer.lower() in ['true', 'yes']:
                return True
            if raw_answer.lower() in ['false', 'no']:
                return False

            # Try to parse as JSON if it looks like JSON
            if raw_answer.strip().startswith('{') or raw_answer.strip().startswith('['):
                import json
                try:
                    return json.loads(raw_answer)
                except json.JSONDecodeError:
                    pass

            # Default: return as string
            return raw_answer.strip()

        except Exception as e:
            logger.warning(f"Error formatting answer, returning raw: {e}")
            return raw_answer

    def convert_embedded_js_to_python(self, js_code, question_text):
        """
        Convert embedded JavaScript code to Python for simple function execution

        Args:
            js_code: JavaScript code to convert
            question_text: The quiz question

        Returns:
            str: Python code that can be executed
        """
        try:
            logger.info("Converting embedded JavaScript to Python")

            system_prompt = """You are a Python code generator. Convert JavaScript code to Python.

Rules:
1. Convert JavaScript functions to Python functions
2. Handle basic arithmetic and string operations
3. Execute the function and store result in 'result' variable
4. Return ONLY executable Python code, no explanations, no markdown blocks"""

            user_prompt = f"""Convert this JavaScript to Python and execute it:

```javascript
{js_code}
```

Question: {question_text}

Generate Python code that:
1. Converts the JavaScript function(s) to Python
2. Calls the function(s) to get the answer
3. Stores the final answer in a variable called 'result'

Return ONLY the Python code."""

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]

            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.1,
                max_tokens=1000
            )

            content = response.choices[0].message.content
            if content is None:
                logger.warning("LLM returned None for embedded JS conversion")
                return None

            code = content.strip()
            # Remove markdown code blocks if present
            if code.startswith('```python'):
                code = code[len('```python'):].strip()
            if code.startswith('```'):
                code = code[3:].strip()
            if code.endswith('```'):
                code = code[:-3].strip()

            logger.info(f"Generated Python code:\n{code}")
            return code

        except Exception as e:
            logger.error(f"Error converting embedded JS to Python: {e}", exc_info=True)
            return None

    def convert_js_to_python(self, js_code, question_text, email, email_number, demo2_key):
        """
        Convert JavaScript code to Python and return executable Python code

        Args:
            js_code: JavaScript code to convert
            question_text: The quiz question
            email: Student email
            email_number: Computed emailNumber
            demo2_key: Computed demo2 key

        Returns:
            str: Python code that can be executed
        """
        try:
            logger.info("Generating Python code from JavaScript")

            system_prompt = """You are a Python code generator. Convert JavaScript code to Python and solve the problem.

Rules:
1. Convert JavaScript crypto functions to Python hashlib
2. Handle string concatenation and SHA256 hashing
3. Extract constants from utils.js (like demo2Blob)
4. Store the final answer in a variable called 'result'
5. Return ONLY executable Python code, no explanations"""

            user_prompt = f"""Convert this JavaScript to Python and solve:

{js_code}

Question: {question_text}

Pre-computed values you can use:
```python
email = "{email}"
email_number = {email_number}
demo2_key = "{demo2_key}"
```

Generate Python code that:
1. Extracts any constants from the JavaScript (like demo2Blob)
2. Performs the required computation (like SHA256 hashing)
3. Stores the final answer in a variable called 'result'

Return ONLY the Python code, no markdown blocks."""

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]

            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.1,
                max_tokens=1000
            )

            content = response.choices[0].message.content
            if content is None:
                logger.warning("LLM returned None for JS-to-Python conversion")
                return None

            code = content.strip()
            # Remove markdown code blocks if present
            if code.startswith('```python'):
                code = code[len('```python'):].strip()
            if code.startswith('```'):
                code = code[3:].strip()
            if code.endswith('```'):
                code = code[:-3].strip()

            logger.info(f"Generated Python code:\n{code}")
            return code

        except Exception as e:
            logger.error(f"Error converting JS to Python: {e}", exc_info=True)
            return None

    def diagnose_and_fix_url(self, quiz_url, email, question_text, html_snippet, issues):
        """
        Ask LLM to diagnose page loading issues and suggest URL fix

        Args:
            quiz_url: The original quiz URL
            email: Student email
            question_text: Extracted question text
            html_snippet: First part of HTML content
            issues: List of detected issues

        Returns:
            dict: {'fixed_url': str or None, 'diagnosis': str}
        """
        try:
            logger.info(f"Diagnosing page issues: {issues}")

            system_prompt = """You are a web debugging expert. Analyze page loading issues and suggest URL fixes.
Common issues:
- Pages requiring ?email= parameter in URL
- JavaScript rendering issues
- Missing query parameters"""

            user_prompt = f"""A quiz page failed to load properly.

Original URL: {quiz_url}
Student Email: {email}
Detected Issues: {', '.join(issues)}

Question Text Extracted:
{question_text[:500]}

HTML Snippet:
{html_snippet}

TASK: Determine if the URL needs to be modified (e.g., adding ?email= or &email= parameter).

Respond in JSON format:
{{"fixed_url": "corrected URL with email parameter if needed", "diagnosis": "brief explanation"}}

If the URL already has ?email= or seems correct, return the original URL unchanged."""

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]

            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.1,
                max_tokens=400
            )

            content = response.choices[0].message.content
            if content:
                import json
                import re
                # Extract JSON from response (handle markdown code blocks)
                json_match = re.search(r'\{[^{}]*"fixed_url"[^{}]*\}', content, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group(0))
                    logger.info(f"LLM diagnosis: {result.get('diagnosis')}")
                    logger.info(f"LLM suggested URL: {result.get('fixed_url')}")
                    return result

            # Fallback: if LLM fails, try adding email parameter ourselves
            if '?email=' not in quiz_url.lower() and '&email=' not in quiz_url.lower():
                separator = '&' if '?' in quiz_url else '?'
                fixed_url = f"{quiz_url}{separator}email={email}"
                return {"fixed_url": fixed_url, "diagnosis": "Added missing email parameter"}

            return {"fixed_url": quiz_url, "diagnosis": "URL seems correct"}

        except Exception as e:
            logger.error(f"Error in URL diagnosis: {e}", exc_info=True)
            # Fallback: try adding email if not present
            if '?email=' not in quiz_url.lower():
                separator = '&' if '?' in quiz_url else '?'
                return {"fixed_url": f"{quiz_url}{separator}email={email}", "diagnosis": "Error - added email as fallback"}
            return {"fixed_url": quiz_url, "diagnosis": f"Error: {str(e)}"}
