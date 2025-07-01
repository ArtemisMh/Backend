from flask import Flask, request, jsonify
from datetime import datetime

app = Flask(__name__)
kc_db = {}
student_db = {}

@app.route("/submit_kc", methods=["POST"])
def submit_kc():
    data = request.get_json()
    print(data)
    return jsonify({"status": "success"})

@app.route('/analyze-response', methods=['POST'])
def analyze_response():
    data = request.json
    kc_id = data["kc_id"]
    student_id = data["student_id"]
    response_text = data["student_response"]

    if "meaning" in response_text.lower():
        solo_level = "Relational"
        justification = "Shows symbolic reasoning"
    elif "red" in response_text or "blue" in response_text:
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
    data = request.json
    kc_id = data["kc_id"]
    student_id = data["student_id"]
    location = data["location"]
    weather = data["weather"]

    kc = kc_db.get(kc_id, {})
    student = student_db.get(student_id, {})

    current_level = student.get("solo_level", "Uni-structural")
    target_level = kc.get("target_SOLO_level", "Relational")

    return jsonify({
        "kc_id": kc_id,
        "student_id": student_id,
        "current_SOLO_level": current_level,
        "target_SOLO_level": target_level,
        "reflective_prompt": "How do the colors and the light in the stained-glass window contribute to its symbolic meaning?",
        "scaffolded_response": "The stained-glass windows use red and blue light to create an emotional atmosphere that symbolizes heaven and divinity.",
        "educator_summary": f"{student_id} is currently at {current_level}. Prompt scaffolded toward {target_level}.",
        "contextual_task": {
            "task_title": "Symbolism in Light",
            "task_description": f"Take a photo of a stained-glass window at {location}. Describe how the light and colors create meaning.",
            "feasibility_notes": f"Weather: {weather}, Location accessible"
        }
    })

@app.route("/", methods=["GET"])
def index():
    return jsonify({"status": "success", "message": "Backend is live!"})
