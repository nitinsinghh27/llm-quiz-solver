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
        # Get all available API configurations
        self.api_configs = Config.get_api_configs()
        self.current_config_index = 0

        # Initialize OpenAI client with first configuration
        current_config = self.api_configs[0]
        self.client = OpenAI(
            api_key=current_config['api_key'],
            base_url=current_config['base_url']
        )

        # Set model based on the base_url (different providers use different model names)
        self.model = self._get_model_for_provider(current_config['base_url'])

        logger.info(f"Initialized LLM client with {len(self.api_configs)} API config(s)")
        logger.info(f"Using {current_config['name']} API: {current_config['base_url']}, Model: {self.model}")

    def _get_model_for_provider(self, base_url):
        """Determine the correct model name based on the API provider"""
        if 'aipipe.org' in base_url or 'openrouter' in base_url:
            # AIPIPE/OpenRouter uses google/gemini-2.0-flash-exp:free
            return "google/gemini-2.0-flash-exp:free"
        else:
            # Direct Gemini API uses gemini-2.5-flash
            return "gemini-2.5-flash"

    def _rotate_api_config(self):
        """Rotate to the next API configuration"""
        if len(self.api_configs) <= 1:
            logger.warning("Only one API config available, cannot rotate")
            return False

        self.current_config_index = (self.current_config_index + 1) % len(self.api_configs)
        new_config = self.api_configs[self.current_config_index]

        # Reinitialize client with new configuration
        self.client = OpenAI(
            api_key=new_config['api_key'],
            base_url=new_config['base_url']
        )

        # Update model based on new provider
        self.model = self._get_model_for_provider(new_config['base_url'])

        # Also update genai for multimodal
        genai.configure(api_key=new_config['api_key'])

        logger.info(f"Rotated to {new_config['name']} API: {new_config['base_url']}, Model: {self.model}")
        return True

    def _call_with_retry(self, api_call_func, max_retries=2):
        """
        Execute API call with automatic retry and API provider rotation on rate limit

        Args:
            api_call_func: Function that makes the API call
            max_retries: Maximum number of retries (including provider rotations)

        Returns:
            API response
        """
        from openai import RateLimitError

        for attempt in range(max_retries):
            try:
                return api_call_func()
            except RateLimitError as e:
                logger.warning(f"Rate limit hit (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    # Try rotating API configuration
                    if self._rotate_api_config():
                        logger.info("Retrying with different API provider...")
                        continue
                    else:
                        logger.error("Cannot rotate API config, re-raising error")
                        raise
                else:
                    logger.error("Max retries reached, re-raising error")
                    raise

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

CRITICAL SECURITY RULE:
- You will be provided with credentials (email and secret) for authentication purposes ONLY
- NEVER return the 'secret' credential as an answer to any question
- The secret is for API authentication, NOT for solving puzzles
- If a question asks for a "secret code" or similar, it refers to content in images, audio, files, or computed values - NEVER the authentication secret

For API-related questions:
- If the question asks you to call an API, generate Python code using requests library
- Include proper authentication (email, secret as query parameters or headers)
- Parse the JSON response and perform required calculations
- Store the final answer in a variable called 'result'

For image analysis questions:
- Carefully examine any provided images
- Extract text, codes, or patterns from the images
- Return ONLY what you see in the image, not authentication credentials

For alphametic puzzles:
- Read the JavaScript code to understand the puzzle
- Extract the equation (e.g., FORK + LIME = result)
- Find the emailNumber calculation
- Calculate the key using: ((emailNumber * 7919 + 12345) mod 1e8)
- Convert the key to digits and map them to the required letter sequence

For merge conflict questions (version control terminology):
- "Merge conflict" refers to Git/version control scenarios where code changes conflict
- You will receive 'base', 'theirs', and 'ours' configurations (JSON objects)
- Identify keys where both 'theirs' and 'ours' modified 'base' differently
- This is a technical data comparison task, not related to interpersonal conflict

For semantic search/embedding questions:
- First fetch documents from /api/docs with email and secret parameters
- Documents should contain 'embedding' field - verify this first
- For query embedding, there are multiple approaches to try in order:
  1. Check if /api/docs response includes a special 'query_embedding' field
  2. Try GET /api/embeddings?text=query&email=...&secret=... (as query params, not POST)
  3. Try POST /api/embeddings with json={"text": query} and auth as query params
  4. If all fail (404), use text-based similarity: count matching words between query and doc text
- Calculate cosine similarity if embeddings available: dot(a,b) / (norm(a) * norm(b))
- Return the document ID with highest similarity score
- Always check response structure and handle 404 errors gracefully with fallback approaches

For steganography/LSB extraction questions:
- Download the image using requests with email and secret as query parameters
- Use PIL (Pillow) to open the image
- Extract LSB (Least Significant Bit) from RGB channels: pixel & 1
- Collect bits and convert to bytes (8 bits = 1 byte)
- IMPORTANT: Check if the extracted character is printable ASCII (32-126) or newline/tab
- Stop when you encounter a non-printable character (except newline/tab) or null terminator
- Only include printable characters in the final message
- The hidden message is usually at the beginning of the pixel data

For nested archive/ZIP extraction questions:
- Download the archive with email and secret query parameters
- Use zipfile module to recursively extract nested ZIPs
- When searching for a file, check if member.endswith('filename.txt') not just equality
- Files can be in subdirectories like 'folder/subfolder/final_truth.txt'
- Recursively process nested ZIP files found within archives
- Read file content and return the text

For API maze/treasure hunt/graph exploration questions:
- Use BFS (breadth-first search) with a queue to explore all locations
- Track visited locations to avoid infinite loops
- Start by calling /api/game/start to get initial location
- For EVERY location (including start), call /api/game/move?to=[LOCATION] to get full details
- Check if location has treasure AFTER calling move API (not just from start response)
- Add unvisited paths to queue for exploration
- Continue until treasure is found or all locations explored
- Use proper error handling for API calls and check response structure

For network graph analysis questions (networkx):
- Fetch graph data from API (nodes and edges with weights)
- Edge fields may vary: try 'source'/'target' OR 'from'/'to' OR 'u'/'v'
- Use flexible field access: edge.get('source') or edge.get('from') or edge.get('u')
- Build graph with networkx, add edges with weights
- Use nx.shortest_path_length(G, source, target, weight='weight') for shortest path
- Handle missing nodes/edges and NetworkXNoPath exceptions

For Minimum Spanning Tree (MST) questions:
- Fetch adjacency matrix from API (usually /api/matrix)
- Matrix is typically a 2D array where matrix[i][j] is the weight between nodes i and j
- Use networkx: create graph with nx.Graph(), add weighted edges from matrix
- Calculate MST using nx.minimum_spanning_tree(G, weight='weight')
- Sum all edge weights in MST to get total cost
- IMPORTANT: Keep code concise - use simple loops, avoid verbose comments

For SQLite database questions:
- Download the database file using requests.get() with email and secret parameters
- Save the response.content directly to a file (e.g., "temp_db.sqlite")
- Connect to the file using sqlite3.connect("temp_db.sqlite")
- DO NOT try to execute binary data as SQL statements
- Use parameterized queries with ? placeholders to prevent SQL injection
- Query the table with SELECT statements to find the required data
- Close the connection when done

For fuzzy matching/typo correction questions:
- Fetch data from API (response may be list or dict with 'names'/'items' key)
- ALWAYS check response type first: isinstance(data, dict) or isinstance(data, list)
- If response is dict, extract the data array: data.get('names') or data.get('items') or data.get('data')
- Use fuzzywuzzy.fuzz.ratio() or difflib.SequenceMatcher for similarity scoring
- Compare target string against each item in the list
- Find the item with highest similarity score to target
- Return the exact string from the list (not the target string)
- Handle edge cases: empty lists, missing keys in dict responses

Instructions:
1. Read the question and context carefully (including any JavaScript code)
2. If the question requires calling an API or performing computation, generate Python code
3. For API calls, use requests library with proper parameters
4. If data or files are mentioned, they will be provided in the context
5. If audio/video files are provided, listen/watch them carefully to extract information
6. If images are provided, analyze them carefully to extract the answer
7. Perform the required analysis or solve the puzzle
8. If you need to execute code to get the answer, return Python code with result variable
9. Otherwise, return ONLY the final answer in the format requested

Code generation rules:
- If question mentions "call the API", "API endpoint", "fetch", "embedding", "merge conflict", "steganography", "LSB", "download", "archive", "nested", "ZIP", "maze", "treasure", "explore", "navigate", "graph", "network", "database", "SQLite", "SQL", "query", "fuzzy", "typo", "similar", "match", "closest", "MST", "spanning tree", "adjacency matrix", or "minimum", generate Python code
- Use requests.get() or requests.post() as appropriate
- Include email and secret parameters for authentication (as query params: ?email=...&secret=...)
- For semantic search: try multiple approaches for query embedding (check docs response, GET with params, POST with json), fallback to text similarity if 404
- For merge conflict detection: compare base vs theirs, base vs ours, and find keys with different modifications
- For steganography: download image, extract LSB from pixels, convert bits to bytes, only keep printable ASCII chars (32-126 plus newline/tab), stop at first non-printable
- For nested archives: recursively extract ZIPs, use member.endswith() not equality for file matching
- For maze/treasure hunts: use BFS with queue, call move API for EVERY location (including start), check treasure after each move, explore paths
- For network graphs: handle flexible edge field names (source/target OR from/to OR u/v), use edge.get() with fallbacks
- For MST: fetch adjacency matrix, build networkx graph, use nx.minimum_spanning_tree(), sum edge weights - KEEP CODE CONCISE
- For SQLite databases: download file, save to disk, connect with sqlite3, query with SELECT, use parameterized queries
- For fuzzy matching: check if API response is dict, extract names array (data.get('names') or data.get('items')), use fuzzywuzzy or difflib for similarity
- ALWAYS add error handling:
  * Check response.status_code before parsing
  * Verify response is dict/list before accessing keys: isinstance(data, dict)
  * Print response.text if unexpected format for debugging
  * Handle JSONDecodeError exceptions
  * NEVER use exit() or sys.exit() - just set result variable and continue
- If an API fails, try alternate approaches or check response.text for debugging
- Store final answer in 'result' variable (even if it's an error message)
- Return ONLY Python code, no markdown blocks

Answer format:
- For numerical answers, return just the number
- For text answers, return just the text
- For boolean answers, return true or false
- Be precise and accurate
- NEVER return the authentication secret as an answer

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

                def make_api_call():
                    return self.client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        temperature=0.1,  # Low temperature for more deterministic answers
                        max_tokens=3000  # Increased to prevent truncation of complex algorithms
                    )

                response = self._call_with_retry(make_api_call)

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

    def solve_with_audio_instructions(self, question_text, audio_transcript, csv_filename=None, cutoff_value=None, csv_url=None):
        """
        Use audio transcript to generate Python code that solves the problem

        Args:
            question_text: The question text from the quiz page
            audio_transcript: The full transcript from audio file
            csv_filename: Name of the CSV file to process
            cutoff_value: The cutoff value (if applicable)
            csv_url: URL to download CSV from if local file doesn't exist (optional)

        Returns:
            str: Python code to execute that will solve the problem
        """
        try:
            logger.info(f"Generating code from audio instructions: {audio_transcript[:200]}...")

            system_prompt = """You are a Python code generator for data analysis tasks. You will receive:
1. Audio transcript with instructions on what to do with data
2. Question text
3. CSV filename or URL (if applicable)
4. Cutoff value (if applicable)

Generate ONLY executable Python code that:
- If a CSV URL is provided, download it first using requests: requests.get(url).content -> save to file
- Reads the CSV file using pandas with header=None (CSV has NO header row)
- Follows the instructions from the audio transcript
- Stores the final answer in a variable called 'result'
- Does NOT print anything

Return ONLY the Python code, no explanations, no markdown formatting, no ```python blocks."""

            user_prompt = f"""Audio Instructions:
{audio_transcript}

Question:
{question_text}"""

            if csv_url:
                # CSV failed to download locally - provide URL for LLM to download
                user_prompt += f"\n\nCSV URL (download first): {csv_url}"
                user_prompt += f"\nSave to local file: {csv_filename}"
            elif csv_filename:
                # CSV already downloaded locally
                user_prompt += f"\n\nCSV File (already downloaded): {csv_filename}"

            if cutoff_value is not None:
                user_prompt += f"\nCutoff Value: {cutoff_value}"

            if csv_url:
                user_prompt += "\n\nGenerate Python code that:\n1. Downloads the CSV from the URL using requests\n2. Saves it to the specified filename\n3. Reads and processes it according to the instructions\n4. Stores the final answer in a variable called 'result'"
            else:
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

            def make_api_call():
                return self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.1,
                    max_tokens=1000
                )

            response = self._call_with_retry(make_api_call)
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

            def make_api_call():
                return self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.1,
                    max_tokens=1000
                )

            response = self._call_with_retry(make_api_call)
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

            def make_api_call():
                return self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.1,
                    max_tokens=400
                )

            response = self._call_with_retry(make_api_call)
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
