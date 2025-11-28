import logging
import google.generativeai as genai
from config import Config

logger = logging.getLogger(__name__)

# Configure Gemini for audio transcription
genai.configure(api_key=Config.AIPIPE_API_KEY)

class AudioTranscriber:
    """Handles audio transcription using Google Gemini API"""

    def __init__(self):
        self.model = genai.GenerativeModel(model_name='gemini-2.5-flash')

    def transcribe_audio(self, audio_file_path):
        """
        Transcribe an audio file using Google Gemini API

        Args:
            audio_file_path: Path to the audio file (supports .wav, .opus, .mp3, etc.)

        Returns:
            str: The transcribed text
        """
        try:
            logger.info(f"Transcribing audio file: {audio_file_path}")

            # Upload audio file to Gemini
            logger.info("Uploading audio to Gemini...")
            uploaded_file = genai.upload_file(audio_file_path)
            logger.info(f"Uploaded: {uploaded_file.name}")

            # Request full transcript with higher token limit
            response = self.model.generate_content(
                [
                    'Please transcribe this audio file completely. Provide the full transcript of everything spoken.',
                    uploaded_file
                ],
                generation_config=genai.types.GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=2000,  # Increased for full transcript
                ),
                safety_settings={
                    genai.types.HarmCategory.HARM_CATEGORY_HARASSMENT: genai.types.HarmBlockThreshold.BLOCK_NONE,
                    genai.types.HarmCategory.HARM_CATEGORY_HATE_SPEECH: genai.types.HarmBlockThreshold.BLOCK_NONE,
                    genai.types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: genai.types.HarmBlockThreshold.BLOCK_NONE,
                    genai.types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: genai.types.HarmBlockThreshold.BLOCK_NONE,
                }
            )

            # Extract transcript
            transcript = response.text.strip()
            logger.info(f"Transcription complete: {transcript}")

            # Clean up uploaded file
            try:
                genai.delete_file(uploaded_file.name)
                logger.info(f"Deleted uploaded file: {uploaded_file.name}")
            except Exception as e:
                logger.warning(f"Could not delete uploaded file: {e}")

            return transcript

        except Exception as e:
            logger.error(f"Error transcribing audio: {e}", exc_info=True)
            return ""
