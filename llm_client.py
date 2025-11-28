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

            # Build the prompt
            system_prompt = """You are a data analysis expert helping to solve quiz questions.
The questions involve data sourcing, preparation, analysis, and visualization.

Instructions:
1. Read the question carefully
2. If data or files are mentioned, they will be provided in the context
3. If audio/video files are provided, listen/watch them carefully to extract information
4. Perform the required analysis
5. Return ONLY the final answer in the format requested
6. For numerical answers, return just the number
7. For text answers, return just the text
8. For boolean answers, return true or false
9. Be precise and accurate

Do not include explanations unless specifically asked. Just provide the answer."""

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
                model = genai.GenerativeModel(model_name="gemini-1.5-flash")

                # Create content parts: text prompt + uploaded files
                prompt_parts = [f"{system_prompt}\n\n{user_prompt}"]
                prompt_parts.extend(uploaded_files)

                # Generate response
                response = model.generate_content(
                    prompt_parts,
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.1,
                        max_output_tokens=2000,
                    )
                )

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
