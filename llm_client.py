from openai import OpenAI
import logging
from config import Config

logger = logging.getLogger(__name__)

class LLMClient:
    """Handles interaction with LLM API (AIPIPE or OpenAI) for solving quiz questions"""

    def __init__(self):
        # Initialize OpenAI client with AIPIPE endpoint
        self.client = OpenAI(
            api_key=Config.AIPIPE_API_KEY,
            base_url=Config.AIPIPE_BASE_URL
        )
        self.model = "gpt-4o"  # Using GPT-4o for better reasoning

    def solve_question(self, question_text, context=None):
        """
        Use LLM to solve a quiz question

        Args:
            question_text: The question text from the quiz page
            context: Optional additional context (e.g., data file contents)

        Returns:
            str: The LLM's answer
        """
        try:
            logger.info(f"Sending question to LLM: {question_text[:200]}...")

            # Build the prompt
            system_prompt = """You are a data analysis expert helping to solve quiz questions.
The questions involve data sourcing, preparation, analysis, and visualization.

Instructions:
1. Read the question carefully
2. If data or files are mentioned, they will be provided in the context
3. Perform the required analysis
4. Return ONLY the final answer in the format requested
5. For numerical answers, return just the number
6. For text answers, return just the text
7. For boolean answers, return true or false
8. Be precise and accurate

Do not include explanations unless specifically asked. Just provide the answer."""

            user_prompt = f"Question:\n{question_text}"

            if context:
                user_prompt += f"\n\nContext/Data:\n{context}"

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

            answer = response.choices[0].message.content.strip()
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
