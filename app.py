from flask import Flask, request, jsonify
import logging
from config import Config
from quiz_solver import QuizSolver

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Validate configuration on startup
try:
    Config.validate()
    logger.info("Configuration validated successfully")
except ValueError as e:
    logger.error(f"Configuration error: {e}")
    logger.error("Please create a .env file with required values (see .env.example)")

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({"status": "ok"}), 200

@app.route('/quiz', methods=['POST'])
def handle_quiz():
    """Main endpoint to receive and process quiz tasks"""
    try:
        # Parse JSON payload
        data = request.get_json()

        if not data:
            logger.warning("Received invalid JSON")
            return jsonify({"error": "Invalid JSON"}), 400

        # Validate required fields
        if 'email' not in data or 'secret' not in data or 'url' not in data:
            logger.warning("Missing required fields in request")
            return jsonify({"error": "Missing required fields: email, secret, url"}), 400

        # Verify secret
        if data['secret'] != Config.SECRET:
            logger.warning(f"Invalid secret received from {data.get('email')}")
            return jsonify({"error": "Invalid secret"}), 403

        # Verify email matches
        if data['email'] != Config.EMAIL:
            logger.warning(f"Email mismatch: {data['email']} != {Config.EMAIL}")
            return jsonify({"error": "Invalid email"}), 403

        logger.info(f"Received valid quiz request for URL: {data['url']}")

        # Process the quiz asynchronously
        quiz_url = data['url']
        solver = QuizSolver()

        # Start solving the quiz (this will handle the chain of quizzes)
        result = solver.solve_quiz_chain(quiz_url, data['email'], data['secret'])

        return jsonify({
            "status": "processing",
            "message": "Quiz solving initiated",
            "initial_url": quiz_url
        }), 200

    except Exception as e:
        logger.error(f"Error handling quiz request: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    port = Config.PORT
    logger.info(f"Starting Flask server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=True)
