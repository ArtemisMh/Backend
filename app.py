
from flask import Flask, request, jsonify
from datetime import datetime
from zoneinfo import ZoneInfo
import uuid
import requests
import os
import math


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
            "message": "KC not submitted: approval required."
        }), 400

    # Fallback auto-ID if GPT didn’t provide it
    if not kc_id:
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

@app.route("/list_kcs", methods=["GET"])
def list_kcs():
    return jsonify({"kcs": list(kc_store.values())}), 200
    
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

    # Return selected fields per record
    response = []
    for record in results:
        response.append({
            "timestamp": record.get("timestamp"),
            "location": record.get("location"),
            "kc_id": record.get("kc_id"),
            "SOLO_level": record.get("SOLO_level"),
            "student_response": record.get("student_response"),
            "justification": record.get("justification"),
            "misconceptions": record.get("misconceptions"),
            "target_SOLO_level": record.get("target_SOLO_level")
        })

    return jsonify({"records": response}), 200

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

# Utility to calculate Haversine distance
def haversine(lat1, lon1, lat2, lon2):
    R = 6371000 # Earth radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))

def get_weather(lat, lng):
    try:
        url = "https://api.openweathermap.org/data/2.5/weather"
        response = requests.get(url, params={
            "lat": lat,
            "lon": lng,
            "appid": OPENWEATHER_API_KEY,
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
            geo = requests.get("https://api.opencagedata.com/geocode/v1/json", params={"q": f"{lat},{lng}", "key": OPENCAGE_API_KEY}).json()
        else:
            geo = requests.get("https://api.opencagedata.com/geocode/v1/json", params={"q": location_input, "key": OPENCAGE_API_KEY}).json()
            lat = geo["results"][0]["geometry"]["lat"]
            lng = geo["results"][0]["geometry"]["lng"]

        location_str = geo["results"][0]["formatted"]
        # Extract timezone info from OpenCage annotations
        timezone_id = geo["results"][0]["annotations"]["timezone"]["name"]
        # Convert to local time using zoneinfo
        timestamp = datetime.now(ZoneInfo(timezone_id)).strftime("%Y-%m-%dT%H:%M:%S")

        record = {
            **data,
            "location": location_str,
            "coordinates": f"{lat},{lng}",
            "lat": lat,
            "lng": lng,
            "timestamp": timestamp,
            "timezone": timezone_id
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

# Route for React Layer GPT — returns a next-step task or reflection based on context
@app.route("/generate-reaction", methods=["POST"])
def generate_reaction():
    """
    Generates a concrete learning task (virtual/indoor/outdoor) based on:
      1) Distance to nearest relevant site (first gate: 1 km threshold),
      2) Weather & temperature (only if within 1 km),
      3) Site accessibility (open/closed) and fee (free/paid) (only if within 1 km).

    Returns a single JSON payload with:
      - kc_id, student_id
      - location snapshot (from latest stored history)
      - nearest site metadata (name/address/url/distance/open/fee)
      - weather (if checked)
      - chosen task {type, title, description, link (if virtual), feasibility_notes}

    Notes:
      - If distance > 1000 m: we SKIP weather/access checks and immediately propose a virtual task.
      - Place Details open_now/price_level are best-effort; missing data becomes "unknown".
    """
    data = request.get_json() or {}
    kc_id = data.get("kc_id")
    student_id = data.get("student_id")

    if not kc_id or not student_id:
        return jsonify({"error": "kc_id and student_id are required"}), 400

    # 1) Get most recent stored location/timezone from history (authoritative)
    lat1 = lon1 = None
    last_rec = None
    for rec in reversed(student_history):
        if rec.get("student_id") == student_id and rec.get("kc_id") == kc_id:
            lat1 = rec.get("lat")
            lon1 = rec.get("lng")
            last_rec = rec
            break
    if lat1 is None or lon1 is None or last_rec is None:
        return jsonify({"error": "Student coordinates not found in history for the given kc_id and student_id."}), 400

    location_block = {
        "formatted": last_rec.get("location"),
        "coordinates": f"{lat1},{lon1}",
        "lat": lat1,
        "lng": lon1,
        "timestamp": last_rec.get("timestamp"),
        "timezone": last_rec.get("timezone"),
    }

    # 2) Build KC-driven keyword for relevant site search
    kc = kc_store.get(kc_id, {})
    kc_title = (kc.get("title") or "").strip()
    kc_desc = (kc.get("description") or "").strip()
    keywords = kc_title if kc_title else (kc_desc if kc_desc else "cultural heritage")

    # 3) Find nearest relevant site via Google Places Nearby Search
    google_key = os.getenv("GOOGLE_API_KEY")
    site_lat = site_lon = None
    site_name = "Unavailable"
    site_address = "Unavailable"
    site_url = None
    open_status = "unknown"  # "open" | "closed" | "unknown"
    fee_status = "unknown"   # "free" | "unknown"

    try:
        nearby_url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
        params = {
            "location": f"{lat1},{lon1}",
            "radius": 1500,          # 1.5 km search cone
            "keyword": keywords,     # relevance via KC
            "key": google_key
        }
        r = requests.get(nearby_url, params=params, timeout=12)
        r.raise_for_status()
        results = (r.json() or {}).get("results", [])
        if results:
            nearest = results[0]
            site_lat = nearest["geometry"]["location"]["lat"]
            site_lon = nearest["geometry"]["location"]["lng"]
            site_name = nearest.get("name", "Unknown")
            site_address = nearest.get("vicinity", "Unknown")
            place_id = nearest.get("place_id")
            site_url = f"https://www.google.com/maps/place/?q=place_id:{place_id}" if place_id else None

            # Optional enrichment: opening hours + price level
            if place_id:
                details_url = "https://maps.googleapis.com/maps/api/place/details/json"
                d_params = {"place_id": place_id, "fields": "opening_hours,price_level", "key": google_key}
                d = requests.get(details_url, params=d_params, timeout=12)
                if d.ok:
                    dj = d.json() or {}
                    res = dj.get("result", {})
                    if isinstance(res.get("opening_hours", {}).get("open_now"), bool):
                        open_status = "open" if res["opening_hours"]["open_now"] else "closed"
                    if "price_level" in res:
                        fee_status = "free" if res["price_level"] == 0 else "unknown"
    except Exception:
        # leave defaults as "unknown" and no coordinates to force virtual if needed
        site_lat = site_lon = None

    # 4) Distance gate (FIRST)
    distance_m = haversine(lat1, lon1, site_lat, site_lon) if (site_lat and site_lon) else 999999
    is_within_1km = distance_m <= 1000

    # Helper to craft a KC-relevant virtual link even without Places
    def kc_virtual_link():
        # Safest, always-available fallback: Wikipedia search with KC title/desc
        query = kc_title or kc_desc or "heritage"
        return f"https://en.wikipedia.org/w/index.php?search={requests.utils.quote(query)}"

    # 5) If distance > 1 km → Virtual task (skip weather/access checks)
    if not is_within_1km:
        virtual_link = site_url or kc_virtual_link()
        task = {
            "task_type": "Virtual",
            "task_title": "Exploración virtual del patrimonio",
            "task_description": (
                "Visita el sitio web y busca un dato que conecte con el tema del KC. "
                "Escribe dos oraciones: (1) ¿Qué aprendiste nuevo? (2) ¿Cómo se relaciona con lo ya visto en clase?"
            ),
            "link": virtual_link,
            "feasibility_notes": (
                f"Distance is {int(distance_m)} m (> 1000 m). "
                "Per the rule, contextual checks are skipped and a virtual activity is assigned."
            )
        }
        return jsonify({
            "kc_id": kc_id,
            "student_id": student_id,
            "location": location_block,
            "nearest_site": {
                "name": site_name,
                "address": site_address,
                "url": site_url,
                "distance_m": int(distance_m),
                "open_status": "unknown",
                "fee_status": "unknown"
            },
            "weather": None,  # not checked when > 1 km
            "task": task
        }), 200

    # 6) If distance ≤ 1 km → NOW check weather & temperature, then decide indoor/outdoor/virtual
    try:
        condition, temp_f = get_weather(lat1, lon1)  # e.g., "sunny"|"cloudy"|"rainy"|"stormy"|"unknown", 72.3
    except Exception:
        condition, temp_f = "unknown", None

    # Boolean flags for clarity
    bad_weather_or_hot = (condition in {"rainy", "stormy"}) or (temp_f is not None and temp_f > 96)
    good_weather_and_not_hot = (condition in {"sunny", "clear", "cloudy"}) and (temp_f is not None and temp_f <= 96)
    site_is_open = (open_status == "open")
    site_is_free = (fee_status == "free")

    # ---- DECISION MATRIX (within 1 km) ----
    # A) Bad weather/hot AND site open & free  -> Indoor contextual task at site
    if bad_weather_or_hot and site_is_open and site_is_free:
        task = {
            "task_type": "Indoor",
            "task_title": f"Exploración interior en {site_name}",
            "task_description": (
                f"Entra a {site_name} ({site_address}) y observa un elemento simbólico (por ejemplo, un relieve o un vitral). "
                "Escribe tres oraciones: qué ves, qué crees que significa y cómo se conecta con el tema del KC."
            ),
            "feasibility_notes": (
                f"Within 1 km ({int(distance_m)} m). Weather is '{condition}' with "
                f"{'unknown' if temp_f is None else f'{temp_f}°F'} → indoor is safer. "
                "Site is open and free."
            )
        }

    # B) Good weather & not hot AND (site NOT open OR NOT free) -> Outdoor contextual task nearby
    elif good_weather_and_not_hot and (not site_is_open or not site_is_free):
        task = {
            "task_type": "Outdoor",
            "task_title": f"Observación exterior de {site_name}",
            "task_description": (
                f"Desde el exterior de {site_name}, dibuja o fotografía un rasgo visible (arco, torre, fachada). "
                "Explica en dos oraciones cómo ese rasgo se relaciona con el tema del KC."
            ),
            "feasibility_notes": (
                f"Within 1 km ({int(distance_m)} m). Weather is '{condition}' and "
                f"{'unknown' if temp_f is None else f'{temp_f}°F'} (≤ 96°F). "
                "El interior no es accesible (cerrado o con costo), así que se propone una actividad exterior."
            )
        }

    # C) Good weather & not hot AND site open & free -> Outdoor contextual task at site (natural best-case)
    elif good_weather_and_not_hot and site_is_open and site_is_free:
        task = {
            "task_type": "Outdoor",
            "task_title": f"Recorrido guiado al aire libre en {site_name}",
            "task_description": (
                f"Camina alrededor de {site_name} y localiza dos detalles arquitectónicos. "
                "Describe cómo cada detalle ayuda a entender el tema del KC y compara sus funciones."
            ),
            "feasibility_notes": (
                f"Within 1 km ({int(distance_m)} m). Weather is '{condition}' and "
                f"{'unknown' if temp_f is None else f'{temp_f}°F'} (≤ 96°F). "
                "El sitio está abierto y es gratuito; actividad exterior recomendada."
            )
        }

    # D) Anything else (unknowns, mixed signals) -> Virtual (safe fallback)
    else:
        virtual_link = site_url or kc_virtual_link()
        task = {
            "task_type": "Virtual",
            "task_title": "Exploración virtual del patrimonio (resguardo)",
            "task_description": (
                "Visita el sitio web y localiza un elemento arquitectónico clave. "
                "Responde: ¿qué función cumple y cómo se conecta con el tema del KC?"
            ),
            "link": virtual_link,
            "feasibility_notes": (
                f"Within 1 km ({int(distance_m)} m), pero las condiciones no permiten seguridad o acceso suficiente "
                f"(weather='{condition}', temp={temp_f}, open='{open_status}', fee='{fee_status}'). "
                "Se recomienda actividad virtual."
            )
        }

    return jsonify({
        "kc_id": kc_id,
        "student_id": student_id,
        "location": location_block,
        "nearest_site": {
            "name": site_name,
            "address": site_address,
            "url": site_url,
            "distance_m": int(distance_m),
            "open_status": open_status,
            "fee_status": fee_status
        },
        "weather": {
            "condition": condition,
            "temperature_f": temp_f
        },
        "task": task
    }), 200


#if __name__ == "__main__":
#    app.run(debug=True)
