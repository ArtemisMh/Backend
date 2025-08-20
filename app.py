
from flask import Flask, request, jsonify
from datetime import datetime
from zoneinfo import ZoneInfo
import uuid
import requests
import os


app = Flask(__name__)

# Secure keys from environment variables
OPENCAGE_API_KEY = os.getenv("OPENCAGE_API_KEY")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
#GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")  # Only for timezone lookup

kc_store = {}
student_history = []

# Root route — for health check
@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "success", "message": "Backend is live!"})

# Route for Learning Design GPT — receives a knowledge component (KC)
# Checks for "approved": true in the incoming JSON. Rejects the request with status 400 if approval is missing. Auto-generates a kc_id if not provided (as fallback). Stores the KC into kc_store only after validation.
@app.route("/submit_kc", methods=["POST"])
def submit_kc():
    data = request.get_json()
    kc_id = data.get("kc_id")

    # Require teacher approval before storing
    if not data.get("approved", False):
        return jsonify({
            "status": "error",
            "message": "KC not submitted: approval required. Please set 'approved': true in the payload."
        }), 400

    # Fallback auto-ID if GPT didn’t provide it
    if not kc_id:
        import uuid
        kc_id = f"KC_{str(uuid.uuid4())[:8]}"
        data["kc_id"] = kc_id

    kc_store[kc_id] = data
    print(f"KC stored: {kc_id}")
    return jsonify({
        "status": "success",
        "message": f"Knowledge component {kc_id} received",
        "kc": data
    }), 200


# New: Route to fetch KC metadata from backend (shared across Analyze/React)
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


@app.route("/get-student-history", methods=["GET"])
def get_student_history():
    student_id = request.args.get("student_id")
    kc_id = request.args.get("kc_id")

    if not student_id:
        return jsonify({"error": "student_id is required"}), 400

    # Filter stored records
    results = [r for r in student_history if r["student_id"] == student_id]

    if kc_id:
        results = [r for r in results if r["kc_id"] == kc_id]

    return jsonify({"records": results}), 200

# Route for Analyze Layer GPT — classifies SOLO level of a student response
@app.route("/analyze-response", methods=["POST"])
def analyze_response():
    data = request.get_json()
    kc_id = data.get("kc_id")
    student_id = data.get("student_id")
    educational_grade_text = data.get("educational_grade", "").lower()
    response_text = data.get("student_response", "").lower()

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
        "educational_grade":educational_grade_text,
        "SOLO_level": solo_level,
        "justification": justification,
        "misconceptions": None
    })

def get_weather(lat, lng):
    try:
        url = "https://api.openweathermap.org/data/2.5/weather"
        response = requests.get(url, params={
            "lat": lat,
            "lon": lng,
            "appid": OPENWEATHER_API_KEY,
            #"units": "metric",
            "units": "imperial"  # Fahrenheit
        })
        data = response.json()
        main = data["weather"][0]["main"].lower()
        temp = data["main"]["temp"]
        if "rain" in main:
            condition = "rainy"
        elif "clear" in main:
            condition = "sunny"
        elif "cloud" in main:
            condition = "cloudy"
        else:
            condition = main
        return condition, temp
    except:
        return "unknown", None

# Route for React Layer GPT — returns a next-step task or reflection based on context
@app.route("/generate-reaction", methods=["POST"])
def generate_reaction():
    data = request.get_json()

    kc_id = data.get("kc_id")
    student_id = data.get("student_id")
    solo_level = data.get("SOLO_level")
    location = data.get("location")
    weather = data.get("weather")
    temperature = data.get("temperature")
    entry_access = data.get("entry_access")
    fee_status = data.get("fee_status")

    # Simulate distance and site metadata
    # In a real deployment, this should be replaced by a proximity check using coordinates and external APIs

    try:
        lat, lng = [float(x.strip()) for x in location.split(",")]
    except:
        return jsonify({"error": "Invalid coordinates format. Use 'lat, lng'."}), 400

    # Simulate distance (in meters) and site info
    distance_m = 850 # Example: student is 850 meters from site
    site_open = (entry_access == "open")
    site_free = (fee_status == "free")


    if (weather in ["rainy", "stormy"] or temperature > 96) and distance_m < 1000 and site_open and site_free:
    #task_type = "Indoor Exploration"
    task_title = "Indoor Exploration at Nearby Site"
    task_description = "Visit the entrance hall or interior of the nearby monument and analyze one symbolic element while sheltered from weather."
    reasoning = "Bad weather or high temperature. Student is within 1KM of a free, open monument. Indoor task is safer and feasible."


    elif weather == "good" and temperature <= 96 and distance_m < 1000 and (not site_open or not site_free):
    #task_type = "Outdoor Exploration"
    task_title = "Outdoor Observation at Nearby Site"
    task_description = "Sketch or photograph an external feature of the nearby historical site and describe how it supports the KC topic."
    reasoning = "Weather is good. Student is close to the site, but it is not accessible indoors, so an outdoor task is recommended."


    elif (weather in ["rainy", "stormy"] or temperature > 96) and distance_m >= 1000 and (not site_open or not site_free):
    #task_type = "Virtual Exploration"
    task_title = "Online Archive Analysis"
    task_description = "Watch a virtual tour or video about the KC topic, then write a short reflection comparing it with what you’ve previously learned."
    reasoning = "Student is far from the site and conditions prevent on-site visits. Digital exploration is the most viable option."


    else:
    #task_type = "Fallback Virtual"
    task_title = "Explore a Heritage Website"
    task_description = "Browse an official cultural heritage website related to the KC and summarize one new insight you gained."
    reasoning = "Conditions or data are incomplete. Defaulting to a safe, general digital learning task."


    return jsonify({
    "student_id": student_id,
    "kc_id": kc_id,
    "reflective_prompt": None,
    "improved_response_model": None,
    "educator_summary": None,
    "contextual_task": {
    "task_title": task_title,
    "task_description": task_description,
    "feasibility_notes": f"Weather: {weather}, Temperature: {temperature}°F, Distance: {distance_m} meters, Entry: {entry_access}, Fee: {fee_status}",
    "reasoning": reasoning
    }
    })
    # weather, temp = get_weather(lat, lng)
    # very_hot = temp is not None and temp > 96

    # prompt = None
    # improved = None

    # if weather == "rainy" or very_hot:
    #     task_title = "Indoor Exploration"
    #     task_description = "Due to rainy weather or high temperature, explore a virtual 3D tour of a cathedral and reflect on how light and form are represented digitally."
    #     notes = f"Weather: {weather}. Temperature: {temp}°F. Outdoor activity avoided."
    # else:
    #     task_title = "On-Site Reflection"
    #     task_description = "Observe the facade or entry of a nearby cathedral or historic building and photograph one detail that expresses spiritual symbolism."
    #     notes = f"Weather is {weather}. Conditions suitable for outdoor observation."

    # return jsonify({
    #     "student_id": student_id,
    #     "kc_id": kc_id,
    #     #"reflective_prompt": prompt,
    #     #"improved_response_model": improved,
    #     "weather": weather,
    #     "temperature": temp,
    #     #"educator_summary": f"SOLO level is {solo_level}. Reaction adapted to current weather.",
    #     "contextual_task": {
    #         "task_title": task_title,
    #         "task_description": task_description,
    #         "feasibility_notes": notes
    #     }
    # })
    
# In-memory storage for historical assessment data (follow-up to analyze)
@app.route("/store-history", methods=["POST"])
def store_history():
    data = request.get_json()

    required_fields = [
        "kc_id", "student_id", "educational_grade", "student_response", "SOLO_level",
        "target_SOLO_level", "justification", "misconceptions", "location"
    ]
    missing = [field for field in required_fields if field not in data]
    if missing:
        return jsonify({
            "status": "error",
            "message": f"Missing required fields: {', '.join(missing)}"
        }), 400

    location_input = data["location"].strip().replace("\"", "").replace("'", "")
    is_coord = False

    try:
        lat, lng = [float(x.strip()) for x in location_input.split(",")]
        is_coord = True
    except:
        is_coord = False

    try:
        if is_coord:
            geo = requests.get("https://api.opencagedata.com/geocode/v1/json", params={
                "q": f"{lat},{lng}",
                "key": OPENCAGE_API_KEY
            }).json()
            if not geo["results"]:
                raise Exception("Unable to reverse geocode coordinates.")
            location_str = geo["results"][0]["formatted"]
        else:
            geo = requests.get("https://api.opencagedata.com/geocode/v1/json", params={
                "q": location_input,
                "key": OPENCAGE_API_KEY
            }).json()
            if not geo["results"]:
                raise Exception("Unable to geocode location string.")
            location_str = geo["results"][0]["formatted"]
            lat = geo["results"][0]["geometry"]["lat"]
            lng = geo["results"][0]["geometry"]["lng"]

        # Extract timezone info from OpenCage annotations
        timezone_id = geo["results"][0]["annotations"]["timezone"]["name"]

        # Convert to local time using zoneinfo
        local_time = datetime.now(ZoneInfo(timezone_id))
        timestamp_local = local_time.strftime("%Y-%m-%dT%H:%M:%S")
        timezone_label = timezone_id

        record = {
            **data,
            "location": location_str,
            "timestamp": timestamp_local,
            "timezone": timezone_label
        }

        student_history.append(record)
        return jsonify({
            "status": "success",
            "message": "Student assessment history stored.",
            "record": record
        }), 200

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Could not process location or time: {str(e)}"
        }), 500

#if __name__ == "__main__":
#    app.run(debug=True)
