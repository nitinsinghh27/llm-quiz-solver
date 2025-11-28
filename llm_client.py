from openai import OpenAI
import logging
from config import Config

logger = logging.getLogger(__name__)

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

            # Build messages array
            if media_files and len(media_files) > 0:
                # For multimodal content, use content array format
                import base64

                content_parts = [{"type": "text", "text": user_prompt}]

                # Add media files as data URIs
                for media_file in media_files:
                    try:
                        with open(media_file['path'], 'rb') as f:
                            file_data = base64.b64encode(f.read()).decode('utf-8')

                        # Determine MIME type
                        mime_types = {
                            'opus': 'audio/ogg',  # Opus is typically in ogg container
                            'mp3': 'audio/mpeg',
                            'wav': 'audio/wav',
                            'ogg': 'audio/ogg',
                            'm4a': 'audio/mp4',
                            'mp4': 'video/mp4',
                            'webm': 'video/webm'
                        }
                        ext = media_file['path'].split('.')[-1].lower()
                        mime_type = mime_types.get(ext, 'application/octet-stream')

                        # Add as input_audio for OpenAI-compatible format
                        # Note: Gemini's OpenAI API supports audio via input_audio
                        content_parts.append({
                            "type": "input_audio",
                            "input_audio": {
                                "data": file_data,
                                "format": ext
                            }
                        })
                        logger.info(f"Added {media_file['type']} file: {media_file['path']} ({mime_type})")
                    except Exception as e:
                        logger.error(f"Error encoding media file {media_file['path']}: {e}")

                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": content_parts}
                ]
            else:
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
