from flask import Flask, request, jsonify
from datetime import datetime

app = Flask(__name__)

# Simulated in-memory storage
kc_db = {}
student_db = {}

@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "success", "message": "Backend is live!"})

@app.route("/submit_kc", methods=["POST"])
def submit_kc():
    data = request.get_json()

    if not data or "kc_id" not in data:
        return jsonify({"status": "error", "message": "Invalid KC submission"}), 400

    kc_db[data["kc_id"]] = data
    return jsonify({
        "status": "success",
        "received": data,
        "note": "Knowledge Component stored successfully."
    })

@app.route("/analyze-response", methods=["POST"])
def analyze_response():
    data = request.get_json()
    kc_id = data.get("kc_id")
    student_id = data.get("student_id")
    response_text = data.get("student_response", "")

    # Basic logic to assign SOLO level (example logic)
    if "meaning" in response_text.lower():
        solo_level = "Relational"
        justification = "Shows symbolic reasoning"
    elif "red" in response_text.lower() or "blue" in response_text.lower():
        solo_level = "Multi-structural"
        justification = "Mentions multiple elements"
    else:
        solo_level = "Uni-structural"
        justification = "Single aspect only"

    student_db[student_id] = {
        "kc_id": kc_id,
        "solo_level": solo_level,
        "timestamp": datetime.now().isoformat()
    }

    return jsonify({
        "kc_id": kc_id,
        "student_id": student_id,
        "SOLO_level": solo_level,
        "justification": justification,
        "misconceptions": "None"
    })

@app.route('/generate-reaction', methods=['POST'])
def generate_reaction():
    data = request.get_json()

    student_id = data.get("student_id")
    kc_id = data.get("kc_id")
    solo_level = data.get("solo_level")
    location = data.get("location")
    weather = data.get("weather")
    time_of_day = data.get("time_of_day")

    # Example logic (you can make this smarter later)
    if solo_level == "Uni-structural":
        prompt = "Look again at the stained glass. What colors do you see, and what do they make you feel?"
        improved = "The colors in the window create a peaceful feeling that might represent heaven."
    elif solo_level == "Multi-structural":
        prompt = "How do all these features work together to create a spiritual experience?"
        improved = "The tall windows and colored light work together to create a feeling of transcendence."
    else:
        prompt = "Compare the use of light in this cathedral with another place you've visited."
        improved = "This cathedral uses light to elevate visitors emotionally, while modern churches use simplicity."

    return jsonify({
        "student_id": student_id,
        "kc_id": kc_id,
        "reflective_prompt": prompt,
        "improved_response_model": improved,
        "educator_summary": f"Student is at {solo_level} level for {kc_id}. Prompt and model answer provided."
    })

if __name__ == "__main__":
    app.run(debug=True)
