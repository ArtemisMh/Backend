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

if __name__ == "__main__":
    app.run(debug=True)
