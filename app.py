from flask import Flask, request, jsonify

app = Flask(__name__)

kc_store = {}

# Root route — for health check
@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "success", "message": "Backend is live!"})


# Route for Learning Design GPT — receives a knowledge component (KC)
@app.route("/submit_kc", methods=["POST"])
def submit_kc():
    data = request.get_json()
    kc_id = data.get("kc_id")
    if not kc_id:
        return jsonify({"status": "error", "message": "kc_id is required"}), 400

    kc_store[kc_id] = data
    print(f"KC stored: {kc_id}")
    return jsonify({"status": "success", "message": f"Knowledge component {kc_id} received"}), 200

# New: Route to fetch KC metadata from backend
@app.route("/get_kc", methods=["GET"])
def get_kc():
    kc_id = request.args.get("kc_id")
    if not kc_id:
        return jsonify({"error": "kc_id parameter is required"}), 400

    kc_data = kc_store.get(kc_id)
    if not kc_data:
        return jsonify({"error": f"KC with ID {kc_id} not found"}), 404

    # Return only key metadata fields
    return jsonify({
        "kc_id": kc_data.get("kc_id"),
        "title": kc_data.get("title"),
        "target_SOLO_level": kc_data.get("target_SOLO_level")
    }), 200


# Route for Analyze Layer GPT — classifies SOLO level of a student response
@app.route("/analyze-response", methods=["POST"])
def analyze_response():
    data = request.get_json()

    kc_id = data.get("kc_id")
    student_id = data.get("student_id")
    response_text = data.get("student_response", "").lower()

    # Simple SOLO-level logic
    if "meaning" in response_text or "symbol" in response_text:
        solo_level = "Relational"
        justification = "Student connects elements to symbolic interpretation."
    elif any(word in response_text for word in ["red", "blue", "window", "light"]):
        solo_level = "Multi-structural"
        justification = "Student lists multiple relevant features."
    elif len(response_text.strip()) > 0:
        solo_level = "Uni-structural"
        justification = "Student mentions one relevant detail."
    else:
        solo_level = "Pre-structural"
        justification = "Student response is incomplete or off-topic."

    return jsonify({
        "kc_id": kc_id,
        "student_id": student_id,
        "SOLO_level": solo_level, #student's current SOLO level
        "justification": justification,
        "misconceptions": None
    })


# Route for React Layer GPT — returns a next-step task or reflection based on context
@app.route("/generate-reaction", methods=["POST"])
def generate_reaction():
    data = request.get_json()

    student_id = data.get("student_id")
    kc_id = data.get("kc_id")
    solo_level = data.get("solo_level")
    location = data.get("location")
    weather = data.get("weather")
    time_of_day = data.get("time_of_day")

    if solo_level == "Uni-structural":
        prompt = "Look again at the stained glass. What colors do you see, and what do they make you feel?"
        improved = "The window’s blue and red colors may symbolize heaven and sacrifice."
    elif solo_level == "Multi-structural":
        prompt = "How do the arches, windows, and ceiling shape your experience together?"
        improved = "The arches and high ceiling help lift the viewer's gaze upward, creating a spiritual feeling."
    elif solo_level == "Relational":
        prompt = "What symbolic purpose do these features serve together?"
        improved = "The light, arches, and windows together represent a connection between earth and heaven."
    else:
        prompt = "Compare how this cathedral uses light with another sacred space you’ve seen."
        improved = "Gothic cathedrals use verticality and light for spiritual symbolism; modern architecture uses minimalism."

    return jsonify({
        "student_id": student_id,
        "kc_id": kc_id,
        "reflective_prompt": prompt,
        "improved_response_model": improved,
        "educator_summary": f"Student is at {solo_level} level for {kc_id}. Reflective guidance provided."
    })

#if __name__ == "__main__":
#    app.run(debug=True)
