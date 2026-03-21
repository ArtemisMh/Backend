from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
from zoneinfo import ZoneInfo
import logging
import uuid
import requests
import os
import math


app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})  # adjust/restrict origins as needed

# Configure logging
logging.basicConfig(level=logging.DEBUG)
app.logger.setLevel(logging.DEBUG)
app.logger.propagate = True

# -------------------------- Environment keys --------------------------- #
OPENCAGE_API_KEY = os.getenv("OPENCAGE_API_KEY")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY") # Only for timezone lookup

# --------------------------- In-memory stores -------------------------- #
kc_store = {}
activity_store = {}
student_history = []

# ---------------------- Root route — health check ---------------------- #
@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "success", "message": "Backend is live!"})

# ---------------------- Learning Design Agent ------------------------- #
@app.route("/submit_kc", methods=["POST"])
def submit_kc():
    data = request.get_json() or {}
    kc_id = data.get("kc_id")

    app.logger.info(f"/submit_kc payload received: {data}")

    # Require teacher approval before storing
    if not data.get("approved", False):
        app.logger.warning("KC not submitted: approval required.")
        return jsonify({
            "status": "error",
            "message": "KC not submitted: approval required."
        }), 400

    # Require explicit KC ID; do not auto-generate
    if not kc_id:
        app.logger.warning("KC not submitted: kc_id is required.")
        return jsonify({
            "status": "error",
            "message": "kc_id is required."
        }), 400
    
    stored_kc = {
        "kc_id": kc_id,
        "title": data.get("title"),
        "kc_description": data.get("kc_description"),
        "target_SOLO_level": data.get("target_SOLO_level"),
        "related_learning_activity_id": data.get("related_learning_activity_id"),
        "SOLO_level_mastery_examples": data.get("SOLO_level_mastery_examples"),
        "media_context": data.get("media_context"),
    }

    kc_store[kc_id] = stored_kc
    app.logger.info(f"KC stored successfully: {kc_id}")
    app.logger.info(f"Stored KC object: {stored_kc}")

    return jsonify({
        "status": "success",
        "message": f"Knowledge component {kc_id} received",
        "kc": stored_kc
    }), 200


@app.route("/list_kcs", methods=["GET"])
def list_kcs():
    return jsonify({"kcs": list(kc_store.values())}), 200


@app.route("/submit_activity", methods=["POST"])
def submit_activity():
    data = request.get_json() or {}
    learning_activity_id = data.get("learning_activity_id")

    app.logger.info(f"/submit_activity payload received: {data}")

    # Require explicit learning activity ID; do not auto-generate
    if not learning_activity_id:
        app.logger.warning("Learning activity not submitted: learning_activity_id is required.")
        return jsonify({
            "status": "error",
            "message": "learning_activity_id is required."
        }), 400

    stored_activity = {
        "learning_activity_id": learning_activity_id,
        "learning_activity_title": data.get("learning_activity_title"),
        "related_kc_ids": data.get("related_kc_ids", []),
    }

    activity_store[learning_activity_id] = stored_activity
    app.logger.info(f"Learning activity stored: {learning_activity_id}")
    app.logger.info(f"Stored activity object: {stored_activity}")

    return jsonify({
        "status": "success",
        "message": f"Learning activity {learning_activity_id} received",
        "activity": stored_activity
    }), 200


@app.route("/list_activities", methods=["GET"])
def list_activities():
    return jsonify({
        "activities": list(activity_store.values())
    }), 200


# fetch KC metadata from backend (shared across Analyze/React)
@app.route("/get_kc", methods=["GET"])
def get_kc():
    kc_id = request.args.get("kc_id")
    if not kc_id:
        return jsonify({"error": "kc_id parameter is required"}), 400

    kc_data = kc_store.get(kc_id)
    if not kc_data:
        return jsonify({"error": f"KC with ID {kc_id} not found"}), 404

    return jsonify({
        "kc_id": kc_data.get("kc_id"),
        "title": kc_data.get("title"),
        "kc_description": kc_data.get("kc_description"),
        "target_SOLO_level": kc_data.get("target_SOLO_level"),
        "related_learning_activity_id": kc_data.get("related_learning_activity_id"),
        "SOLO_level_mastery_examples": kc_data.get("SOLO_level_mastery_examples"),
        "media_context": kc_data.get("media_context"),
    }), 200

# ---------------------- Learning Activity Metadata (GET) ---------------------- #
@app.route("/get_activity", methods=["GET"])
def get_activity():
    learning_activity_id = request.args.get("learning_activity_id")
    if not learning_activity_id:
        return jsonify({"error": "learning_activity_id parameter is required"}), 400

    activity_data = activity_store.get(learning_activity_id)
    if not activity_data:
        return jsonify({"error": f"Learning activity with ID {learning_activity_id} not found"}), 404

    return jsonify({
        "learning_activity_id": activity_data.get("learning_activity_id"),
        "learning_activity_title": activity_data.get("learning_activity_title"),
        "related_kc_ids": activity_data.get("related_kc_ids", [])
    }), 200

# ---------------------- Student History (GET) ------------------------- #
@app.route("/get-student-history", methods=["GET"])
def get_student_history():
    student_id = request.args.get("student_id")
    kc_id = request.args.get("kc_id")
    latest = (request.args.get("latest", "") or "").lower() == "true"

    if not student_id:
        return jsonify({"error": "student_id is required"}), 400

    results = [r for r in student_history if r.get("student_id") == student_id]
    if kc_id:
        results = [r for r in results if r.get("kc_id") == kc_id]

    results_sorted = sorted(results, key=lambda r: r.get("timestamp") or "", reverse=True)
    if latest and results_sorted:
        results_sorted = [results_sorted[0]]

    response = []
    for record in results_sorted:
        response.append({
            "timestamp": record.get("timestamp"),
            "timezone": record.get("timezone"),
            "location": record.get("location"),
            "lat": record.get("lat"),
            "lng": record.get("lng"),
            "kc_id": record.get("kc_id"),
            "student_id": record.get("student_id"),
            "learning_activity_id": record.get("learning_activity_id"),
            "learning_activity_title": record.get("learning_activity_title"),
            "SOLO_level": record.get("SOLO_level"),
            "student_response": record.get("student_response"),
            "student_response_type": record.get("student_response_type"),
            "student_response_reference": record.get("student_response_reference"),
            "student_response_transcription": record.get("student_response_transcription"),
            "justification": record.get("justification"),
            "misconceptions": record.get("misconceptions"),
            "target_SOLO_level": record.get("target_SOLO_level"),
            "location_required": record.get("location_required"),
        })

    return jsonify({"records": response}), 200

# ---------------------- Analyze Layer Agent --------------------------- #
@app.route("/analyze-response", methods=["POST"])
def analyze_response():
    data = request.get_json() or {}

    kc_id = data.get("kc_id")
    student_id = data.get("student_id") 
    learning_activity_id = data.get("learning_activity_id")
    learning_activity_title = data.get("learning_activity_title")

    student_response = (data.get("student_response") or "").strip()
    student_response_type = (data.get("student_response_type") or "text").strip().lower()
    student_response_reference = data.get("student_response_reference")
    student_response_transcription = (data.get("student_response_transcription") or "").strip()

    if not kc_id or not student_id:
        return jsonify({"error": "kc_id and student_id are required"}), 400

    if student_response_type not in {"text", "image", "pdf", "drawing", "notes"}:
        return jsonify({
            "error": "student_response_type must be one of: text, image, pdf, drawing, notes"
        }), 400

    # Use text if available; otherwise fall back to transcription
    response_text = (student_response or student_response_transcription).lower().strip()

    # The LLM should do the real classification using /get_kc and /get_activity.
    # Placeholder logic only
    if not response_text:
        solo_level = "Pre-structural"
        justification = "No readable or transcribed student response was provided."
        misconceptions = "Response is blank, unreadable, or insufficient to assess."
    elif any(phrase in response_text for phrase in [
        "i don't know", "i dont know", "no sé", "no se", "i don't remember", "no recuerdo"
    ]):
        solo_level = "Pre-structural"
        justification = "The response explicitly indicates lack of knowledge or recall."
        misconceptions = "No evidence of relevant understanding is shown."
    elif "meaning" in response_text or "symbol" in response_text:
        solo_level = "Relational"
        justification = "The student connects elements to symbolic interpretation."
        misconceptions = None
    elif any(word in response_text for word in ["red", "blue", "window", "light"]):
        solo_level = "Multi-structural"
        justification = "The student mentions several relevant aspects, but without integrating them."
        misconceptions = "Relationships between the identified aspects are not explained."
    elif len(response_text) > 0:
        solo_level = "Uni-structural"
        justification = "The student mentions at least one relevant aspect, but the response remains limited."
        misconceptions = "The response does not yet show multiple connected ideas."
    else:
        solo_level = "Pre-structural"
        justification = "The response is incomplete or off-topic."
        misconceptions = "No clear relevant reasoning is demonstrated."

    return jsonify({
        "kc_id": kc_id,
        "student_id": student_id,
        "learning_activity_id": learning_activity_id,
        "learning_activity_title": learning_activity_title,
        "student_response_type": student_response_type,
        "student_response_reference": student_response_reference,
        "student_response_transcription": student_response_transcription if student_response_transcription else None,
        "SOLO_level": solo_level,
        "justification": justification,
        "misconceptions": misconceptions,
        "approved": False
    }), 200

# ---------------------- Utilities ------------------------------------ #
def haversine(lat1, lon1, lat2, lon2):
    """Great-circle distance in meters using the Haversine formula."""
    R = 6371000  # Earth radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon1 - lon2)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


def get_weather(lat, lng):
    """Return (condition, temp_f) or ('unknown', None) if unavailable."""
    if not OPENWEATHER_API_KEY:
        return "unknown", None
    try:
        url = "https://api.openweathermap.org/data/2.5/weather"
        response = requests.get(url, params={
            "lat": lat,
            "lon": lng,
            "appid": OPENWEATHER_API_KEY,
            "units": "imperial"
        }, timeout=12)
        response.raise_for_status()
        data = response.json()
        main = (data.get("weather", [{}])[0].get("main") or "").lower()
        temp = data.get("main", {}).get("temp")
        if "rain" in main:
            condition = "rainy"
        elif "clear" in main:
            condition = "sunny"
        elif "cloud" in main:
            condition = "cloudy"
        elif "storm" in main or "thunder" in main:
            condition = "stormy"
        else:
            condition = main or "unknown"
        return condition, temp
    except Exception:
        return "unknown", None

# ---------------------- Location Normalization Helpers ---------------- #
def _parse_latlng_from_string(s: str):
    """Accepts '40.4168,-3.7038' and returns (lat, lng) or (None, None)."""
    try:
        parts = [p.strip() for p in s.split(",")]
        if len(parts) != 2:
            return None, None
        return float(parts[0]), float(parts[1])
    except Exception:
        return None, None

def _ensure_coordinates_and_location(payload: dict):
    """
    Normalizes incoming location fields and returns:
      (lat: float|None, lng: float|None, formatted_location: str|None, tz_name: str|None)
    Priority:
      1) Numeric lat/lng.
      2) If 'location' is 'lat,lng' string → parse.
      3) If 'location' is free-text → geocode via OpenCage (also get timezone).
    """
    lat = payload.get("lat")
    lng = payload.get("lng")
    loc = payload.get("location")

    # 1) Already numeric?
    try:
        if lat is not None and lng is not None:
            flat = float(lat)
            flng = float(lng)
            return flat, flng, (loc if isinstance(loc, str) else None), None
    except Exception:
        pass

    # 2) "lat,lng" string?
    if isinstance(loc, str) and "," in loc:
        plat, plng = _parse_latlng_from_string(loc)
        if plat is not None and plng is not None:
            return plat, plng, loc, None

    # 3) Geocode free-text
    if isinstance(loc, str) and loc.strip():
        try:
            oc_key = OPENCAGE_API_KEY
            if not oc_key:
                return None, None, loc, None
            url = "https://api.opencagedata.com/geocode/v1/json"
            params = {"q": loc, "key": oc_key, "no_annotations": 0, "limit": 1, "language": "es"}
            r = requests.get(url, params=params, timeout=12)
            if r.ok:
                js = r.json() or {}
                results = js.get("results", [])
                if results:
                    best = results[0]
                    g = best.get("geometry", {})
                    plat = float(g.get("lat"))
                    plng = float(g.get("lng"))
                    formatted = best.get("formatted", loc)
                    tz_name = None
                    ann = best.get("annotations", {})
                    if "timezone" in ann and "name" in ann["timezone"]:
                        tz_name = ann["timezone"]["name"]
                    return plat, plng, formatted, tz_name
        except Exception:
            return None, None, loc, None

    return None, None, (loc if isinstance(loc, str) else None), None


def _now_in_timezone(tz_name: str | None):
    """
    Returns (timestamp_iso, tz_name_final). Falls back to UTC if tz_name is missing/invalid.
    """
    try:
        tz = ZoneInfo(tz_name) if tz_name else ZoneInfo("UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    dt = datetime.now(tz)
    return dt.strftime("%Y-%m-%dT%H:%M:%S%z"), str(tz)


def _location_required_from_media_context(media_context: str | None) -> bool:
    """
    Returns False for media contexts that are clearly non-location-dependent,
    such as drawing or note-taking.
    """
    if not media_context:
        return True

    mc = media_context.lower()

    non_location_keywords = [
        "drawing",
        "draw",
        "sketch",
        "taking note",
        "taking notes",
        "note-taking",
        "notes",
        "annotation",
        "annotating",
        "worksheet",
        "apuntes",
        "tomar notas",
        "anotación",
        "anotaciones",
        "dibujo",
        "dibujar",
        "boceto",
    ]

    return not any(keyword in mc for keyword in non_location_keywords)

# ---------------------- Places/Task Helpers ------------------------- #

def _build_site_keywords(kc_title: str, kc_desc: str):
    base = []
    if kc_title:
        base.append(kc_title)
    if kc_desc and kc_desc.lower() not in kc_title.lower():
        base.append(kc_desc)
    base.append("learning material OR educational resource OR topic")
    return " ".join([b for b in base if b]).strip() or "learning material"

def _nearby_rankby_distance(lat: float, lng: float, keyword: str, api_key: str):
    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    params = {
        "location": f"{lat},{lng}",
        "rankby": "distance",
        "keyword": keyword,
        "key": api_key
    }
    r = requests.get(url, params=params, timeout=12)
    r.raise_for_status()
    return (r.json() or {}).get("results", [])

def _google_nearest_place(lat: float, lng: float, keywords: str, api_key: str, exclude_city: str | None = None):
    """
    Returns the closest relevant place using rank-by-distance.
    If exclude_city is provided, prefer the nearest result whose 'vicinity' does not contain that city.
    """
    if not api_key:
        return None

    results = []
    try:
        results = _nearby_rankby_distance(lat, lng, keywords, api_key)
    except Exception:
        results = []

    if not results:
        try:
            results = _nearby_rankby_distance(
                lat, lng, "library OR school OR learning center OR educational resource", api_key
            )
        except Exception:
            results = []

    if not results:
        return None

    picked = None
    if exclude_city:
        city_lower = exclude_city.lower()
        for p in results:
            vic = (p.get("vicinity") or "").lower()
            if city_lower not in vic:
                picked = p
                break
    if picked is None:
        picked = results[0]

    geom = picked.get("geometry", {}).get("location", {})
    return {
        "place_id": picked.get("place_id"),
        "name": picked.get("name", "Unknown"),
        "address": picked.get("vicinity", "Unknown"),
        "lat": geom.get("lat"),
        "lng": geom.get("lng")
    }

def _google_place_details(place_id: str, api_key: str):
    if not (place_id and api_key):
        return {}
    try:
        url = "https://maps.googleapis.com/maps/api/place/details/json"
        fields = "opening_hours,price_level,website,url"
        r = requests.get(url, params={"place_id": place_id, "fields": fields, "key": api_key}, timeout=12)
        if not r.ok:
            return {}
        res = (r.json() or {}).get("result", {})
        return {
            "open_now": res.get("opening_hours", {}).get("open_now"),
            "price_level": res.get("price_level"),
            "website": res.get("website"),
            "maps_url": res.get("url"),
        }
    except Exception:
        return {}

def _best_heritage_link(resource_name: str, details: dict, kc_title: str, last_location_label: str):
    """
    Prefer official website; else Wikipedia search by site name (+ location label);
    finally KC title search.
    """
    if details.get("website"):
        return details["website"]
    if resource_name and last_location_label:
        q = f"{resource_name} {last_location_label}"
        return f"https://en.wikipedia.org/w/index.php?search={requests.utils.quote(q)}"
    if resource_name:
        return f"https://en.wikipedia.org/w/index.php?search={requests.utils.quote(resource_name)}"
    q = kc_title or "educational topic"
    return f"https://en.wikipedia.org/w/index.php?search={requests.utils.quote(q)}"

def _solo_transition_prompt(current_level: str, target_level: str, kc_title: str, language: str = "es"):
    current = (current_level or "").lower()
    target = (target_level or "").lower()
    title = kc_title or "el tema"

    if language.startswith("es"):
        if current.startswith("pre"):
            return f"Explora el recurso y anota una idea clave sobre {title}. ¿Qué ves que te llama la atención?"
        if current.startswith("uni") and "multi" in target:
            return f"Lee el sitio y menciona al menos tres datos sobre {title}. ¿Qué sección respalda cada dato?"
        if current.startswith("multi") and "relational" in target:
            return f"Relaciona dos ideas del sitio sobre {title}. ¿Cómo se conectan entre sí?"
        if current.startswith("relat") and "extended" in target:
            return f"Elabora una explicación general sobre {title}. ¿Qué nueva idea puedes proponer?"
        return f"Usa el sitio para avanzar hacia {target_level}: escribe 3–4 oraciones sobre {title}."
    else:
        if current.startswith("pre"):
            return f"Explore the resource and note one key idea about {title}. What stands out to you?"
        if current.startswith("uni") and "multi" in target:
            return f"Read the resource and list at least three facts about {title}. Which section supports each fact?"
        if current.startswith("multi") and "relational" in target:
            return f"Connect two ideas from the resource about {title}. How do they relate?"
        if current.startswith("relat") and "extended" in target:
            return f"Synthesize a big-picture explanation about {title}. What new idea can you propose?"
        return f"Use the resource to progress toward {target_level}: write 3–4 sentences about {title}."


# ---------------------- Store History (POST) -------------------------- #
@app.route("/store-history", methods=["POST"])
def store_history():
    """
    Stores a SOLO assessment result and optionally normalizes location.

    Behavior:
      - Supports multimodal student submissions: text, image, pdf, drawing, notes.
      - Saves learning_activity_id and learning_activity_title in history.
      - Accepts numeric lat/lng, a "lat,lng" string in 'location', or a free-text city/place.
      - If the linked KC media_context suggests drawing/note-taking style work,
        location is not required.
      - If location is not required, timestamp/timezone/location may remain None.
    """
    data = request.get_json() or {}
    app.logger.info(f"/store-history payload: {data}")

    approved = data.get("approved")
    if not approved:
        return jsonify({
            "error": "Teacher approval required before storing analysis",
            "hint": "Resend with 'approved': true once verified by a teacher."
        }), 400

    student_id = data.get("student_id")
    kc_id = data.get("kc_id")
    learning_activity_id = data.get("learning_activity_id")
    learning_activity_title = data.get("learning_activity_title")
    SOLO_level = data.get("SOLO_level")

    if not student_id or not kc_id or not SOLO_level:
        return jsonify({"error": "student_id, kc_id, and SOLO_level are required"}), 400

    if not learning_activity_id:
        return jsonify({"error": "learning_activity_id is required"}), 400

    if not learning_activity_title:
        return jsonify({"error": "learning_activity_title is required"}), 400

    student_response = data.get("student_response")
    student_response_type = (data.get("student_response_type") or "text").strip().lower()
    student_response_reference = data.get("student_response_reference")
    student_response_transcription = data.get("student_response_transcription")

    if student_response_type not in {"text", "image", "pdf", "drawing", "notes"}:
        return jsonify({
            "error": "student_response_type must be one of: text, image, pdf, drawing, notes"
        }), 400

    justification = data.get("justification")
    misconceptions = data.get("misconceptions")
    target_SOLO_level = data.get("target_SOLO_level")

    if not target_SOLO_level:
        return jsonify({"error": "target_SOLO_level is required"}), 400
    if justification is None:
        return jsonify({"error": "justification is required"}), 400
    if misconceptions is None:
        return jsonify({"error": "misconceptions is required"}), 400

    if not any([student_response, student_response_reference, student_response_transcription]):
        return jsonify({
            "error": (
                "At least one of student_response, student_response_reference, "
                "or student_response_transcription is required."
            )
        }), 400

    kc_meta = kc_store.get(kc_id, {})
    media_context = kc_meta.get("media_context")
    location_required = _location_required_from_media_context(media_context)

    lat = None
    lng = None
    formatted_loc = data.get("location")
    tz_name_from_geo = None
    timestamp_iso = None
    tz_final = None

    if location_required:
        lat, lng, formatted_loc, tz_name_from_geo = _ensure_coordinates_and_location(data)
        app.logger.info(
            f"Normalized -> lat={lat}, lng={lng}, formatted='{formatted_loc}', tz='{tz_name_from_geo}'"
        )

        if lat is None or lng is None:
            return jsonify({
                "error": (
                    "Location is required for this activity context and could not be resolved. "
                    "Send numeric 'lat' and 'lng', or 'location' as 'lat,lng', "
                    "or a geocodable city/place/address string."
                )
            }), 400

        timestamp_iso, tz_final = _now_in_timezone(tz_name_from_geo)

    record = {
        "timestamp": timestamp_iso,
        "location": formatted_loc,
        "kc_id": kc_id,
        "student_id": student_id,
        "learning_activity_id": learning_activity_id,
        "learning_activity_title": learning_activity_title,
        "SOLO_level": SOLO_level,
        "student_response": student_response,
        "student_response_type": student_response_type,
        "student_response_reference": student_response_reference,
        "student_response_transcription": student_response_transcription,
        "justification": justification,
        "misconceptions": misconceptions,
        "target_SOLO_level": target_SOLO_level,
        "lat": lat,
        "lng": lng,
        "timezone": tz_final,
        "approved": True,
        "location_required": location_required,
    }

    student_history.append(record)

    return jsonify({
        "status": "ok",
        "stored": {
            "student_id": student_id,
            "kc_id": kc_id,
            "learning_activity_id": learning_activity_id,
            "learning_activity_title": learning_activity_title,
            "SOLO_level": SOLO_level,
            "approved": True,
            "timestamp": timestamp_iso,
            "timezone": tz_final,
            "location": formatted_loc,
            "lat": lat,
            "lng": lng,
            "student_response_type": student_response_type,
            "student_response_reference": student_response_reference,
            "student_response_transcription": student_response_transcription,
            "location_required": location_required,
        }
    }), 200

# ---------------------- React Agent Helpers -------------------------- #

SOLO_ORDER = {
    "Pre-structural": 0,
    "Uni-structural": 1,
    "Multi-structural": 2,
    "Relational": 3,
    "Extended abstract": 4,
}


def _summarize_student_response(record: dict, max_len: int = 220) -> str:
    text = (
        record.get("student_response")
        or record.get("student_response_transcription")
        or ""
    ).strip()

    if not text:
        response_type = record.get("student_response_type") or "unknown"
        ref = record.get("student_response_reference")
        if ref:
            text = f"{response_type} submission referenced by {ref}"
        else:
            text = f"{response_type} submission with no readable transcription"

    text = " ".join(text.split())
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _infer_language_from_record(record: dict) -> str:
    text = (
        (record.get("student_response") or "")
        + " "
        + (record.get("student_response_transcription") or "")
        + " "
        + (record.get("justification") or "")
    ).lower()

    spanish_markers = [
        " el ", " la ", " los ", " las ", " un ", " una ", " que ", " porque ",
        " no ", " sí ", " dibujo ", " apuntes ", " nota ", " leer ", " texto ",
        " relaciona ", " explica ", " respuesta ", " estudiante "
    ]
    score = sum(1 for m in spanish_markers if m in f" {text} ")
    return "es" if score >= 2 else "en"


def _media_context_category(media_context: str | None) -> str:
    mc = (media_context or "").lower()

    drawing_kw = ["drawing", "draw", "sketch", "dibujo", "dibujar", "boceto"]
    notes_kw = ["notes", "note-taking", "taking notes", "apuntes", "tomar notas", "nota"]
    reading_kw = ["reading", "read", "lectura", "leer", "texto"]
    annotation_kw = ["annotation", "annotate", "annotating", "anotación", "anotaciones"]
    physical_kw = [
        "local environment", "environment", "fieldwork", "site visit", "museum",
        "school", "library", "outdoor", "indoor", "visiting", "place", "nearby",
        "entorno local", "trabajo de campo", "visita", "biblioteca", "escuela",
        "colegio", "museo", "aire libre", "interior"
    ]

    if any(k in mc for k in drawing_kw):
        return "Drawing"
    if any(k in mc for k in annotation_kw):
        return "Annotation"
    if any(k in mc for k in notes_kw):
        return "Notes"
    if any(k in mc for k in reading_kw):
        return "Reading"
    if any(k in mc for k in physical_kw):
        return "Physical"
    return "Virtual"


def _next_solo_label(current_level: str, target_level: str) -> str:
    current_idx = SOLO_ORDER.get(current_level, 0)
    target_idx = SOLO_ORDER.get(target_level, current_idx)
    if current_idx >= target_idx:
        return target_level or current_level or "Relational"

    for label, idx in SOLO_ORDER.items():
        if idx == current_idx + 1:
            return label
    return target_level or current_level or "Relational"


def _reflective_prompt(current_level: str, target_level: str, kc_title: str, lang: str = "es") -> str:
    next_level = _next_solo_label(current_level, target_level)
    title = kc_title or ("el tema" if lang == "es" else "the topic")

    if lang == "es":
        prompts = {
            "Uni-structural": f"Ahora mismo tu respuesta muestra comprensión muy limitada sobre {title}. ¿Qué idea central sí puedes identificar con claridad y cómo se relaciona con la tarea?",
            "Multi-structural": f"Ya mencionas algunos elementos de {title}, pero todavía aparecen separados. ¿Cuáles son los dos o tres elementos más importantes y cómo se relacionan entre sí?",
            "Relational": f"Ya reconoces varios aspectos de {title}. ¿Cómo puedes integrarlos en una explicación coherente que justifique relaciones, causas o funciones?",
            "Extended abstract": f"Tu comprensión de {title} ya puede ir más allá del caso concreto. ¿Qué principio general, comparación o hipótesis puedes formular a partir de lo observado?"
        }
        return prompts.get(next_level, f"Revisa lo que falta en tu razonamiento sobre {title} y explica cómo conectar mejor las ideas principales.")
    else:
        prompts = {
            "Uni-structural": f"Your response currently shows very limited understanding of {title}. What is one central idea you can identify clearly, and how does it relate to the task?",
            "Multi-structural": f"You already mention some elements of {title}, but they still appear disconnected. Which two or three elements matter most, and how do they relate?",
            "Relational": f"You identify several aspects of {title}. How can you integrate them into one coherent explanation that justifies relationships, causes, or functions?",
            "Extended abstract": f"Your understanding of {title} can now go beyond the immediate case. What broader principle, comparison, or hypothesis can you propose?"
        }
        return prompts.get(next_level, f"Review what is missing in your reasoning about {title} and explain how the main ideas connect more clearly.")


def _scaffolded_response(current_level: str, target_level: str, kc_title: str, kc_desc: str, lang: str = "es") -> str:
    title = kc_title or ("el tema" if lang == "es" else "the topic")
    desc = kc_desc or ""

    if lang == "es":
        if SOLO_ORDER.get(target_level, 0) >= SOLO_ORDER["Relational"]:
            return (
                f"Una respuesta más sólida sobre {title} debería integrar varias ideas en una explicación coherente. "
                f"Por ejemplo: '{title} no se entiende solo por elementos aislados; sus partes se relacionan entre sí "
                f"para construir un significado conjunto. {desc}'."
            )
        return (
            f"Una respuesta mejorada sobre {title} debería mencionar más de un aspecto relevante y organizarlos con claridad. "
            f"Por ejemplo: 'En {title} aparecen varios elementos importantes que pueden describirse de forma ordenada antes de relacionarlos'."
        )
    else:
        if SOLO_ORDER.get(target_level, 0) >= SOLO_ORDER["Relational"]:
            return (
                f"A stronger response about {title} should integrate several ideas into one coherent explanation. "
                f"For example: '{title} is not understood through isolated elements alone; its parts relate to one another "
                f"to create a combined meaning. {desc}'."
            )
        return (
            f"An improved response about {title} should mention more than one relevant aspect and organize them clearly. "
            f"For example: 'In {title}, several important elements appear and can be described in an ordered way before connecting them'."
        )


def _educator_summary_for_activity(records: list[dict], current_record: dict, lang: str = "es") -> str:
    sorted_records = sorted(records, key=lambda r: r.get("timestamp") or "")
    current_level = current_record.get("SOLO_level") or "Pre-structural"

    if len(sorted_records) <= 1:
        if lang == "es":
            return (
                f"Esta es la primera evidencia registrada para esta actividad. La valoración debe basarse solo en la respuesta actual: "
                f"el estudiante se sitúa en {current_level} y todavía presenta aspectos a reforzar según la justificación y las lagunas detectadas."
            )
        return (
            f"This is the first recorded evidence for this activity. The evaluation must be based only on the current response: "
            f"the student is currently at {current_level} and still shows areas that need reinforcement according to the justification and detected gaps."
        )

    levels = [r.get("SOLO_level") or "Pre-structural" for r in sorted_records]
    idxs = [SOLO_ORDER.get(l, 0) for l in levels]

    improving = idxs[-1] > idxs[0] and all(b >= a for a, b in zip(idxs, idxs[1:]))
    declining = idxs[-1] < idxs[0] and all(b <= a for a, b in zip(idxs, idxs[1:]))
    fluctuating = not improving and not declining and len(set(idxs)) > 1

    if lang == "es":
        if improving:
            return (
                f"En esta actividad se observa una progresión global desde {levels[0]} hasta {levels[-1]}. "
                f"Hay avance, pero el nivel actual todavía requiere consolidar relaciones, precisión o profundidad conceptual según el caso."
            )
        if declining:
            return (
                f"En esta actividad se aprecia un descenso desde {levels[0]} hasta {levels[-1]}. "
                f"Conviene revisar qué elementos antes presentes ya no aparecen con claridad y reforzar la coherencia del razonamiento."
            )
        if fluctuating:
            return (
                f"En esta actividad el desempeño ha sido fluctuante ({' → '.join(levels)}). "
                f"Hay evidencia parcial de comprensión, pero la consistencia del razonamiento todavía no está consolidada."
            )
        return (
            f"En esta actividad el estudiante mantiene un desempeño bastante estable en {levels[-1]}. "
            f"Existe una base reconocible, aunque aún deben reforzarse aspectos de profundidad o integración."
        )
    else:
        if improving:
            return (
                f"For this activity, there is an overall progression from {levels[0]} to {levels[-1]}. "
                f"There is progress, but the current level still requires stronger relations, precision, or conceptual depth."
            )
        if declining:
            return (
                f"For this activity, there is a decline from {levels[0]} to {levels[-1]}. "
                f"It would be useful to review which elements previously present are no longer clearly expressed and reinforce coherence."
            )
        if fluctuating:
            return (
                f"For this activity, performance has fluctuated ({' → '.join(levels)}). "
                f"There is partial evidence of understanding, but the consistency of reasoning is not yet consolidated."
            )
        return (
            f"For this activity, the student shows a fairly stable performance at {levels[-1]}. "
            f"There is a recognizable base, although depth and integration still need reinforcement."
        )


def _strict_resource_link(url: str | None) -> str | None:
    if not url:
        return None
    url = url.strip()
    if not url:
        return None
    blocked = ["wikipedia.org", "w/index.php?search="]
    if any(b in url.lower() for b in blocked):
        return None
    return url


def _contextual_basis(media_context: str | None, category: str, lang: str = "es") -> dict:
    mc = media_context or ""
    if lang == "es":
        rationale = (
            f"Se propone esta reacción porque el media_context definido en Learning Design Agent es '{mc}'. "
            f"Por ello, la tarea se orienta al formato pedagógico más coherente con esa propuesta ({category})."
        )
    else:
        rationale = (
            f"This reaction is proposed because the media_context defined in the Learning Design Agent is '{mc}'. "
            f"Therefore, the task is aligned with the pedagogical format most consistent with that proposal ({category})."
        )
    return {"media_context": mc, "rationale": rationale}


def _task_from_media_context(
    category: str,
    kc_title: str,
    current_level: str,
    target_level: str,
    media_context: str | None,
    lang: str = "es",
    place_data: dict | None = None,
    weather_data: dict | None = None,
) -> dict:
    title = kc_title or ("el tema" if lang == "es" else "the topic")
    mc = media_context or ""
    place_data = place_data or {}
    weather_data = weather_data or {}

    if category == "Drawing":
        if lang == "es":
            return {
                "task_type": "Drawing",
                "task_title": f"Dibujo guiado sobre {title}",
                "task_description": (
                    f"Realiza un dibujo o esquema sobre {title} y añade al menos dos etiquetas explicativas. "
                    f"El dibujo debe mostrar las partes o ideas clave y no solo su apariencia."
                ),
                "link": None,
                "feasibility_notes": (
                    f"La tarea se propone directamente desde el media_context '{mc}', por lo que no requiere distancia, clima ni lugar físico."
                )
            }
        return {
            "task_type": "Drawing",
            "task_title": f"Guided drawing about {title}",
            "task_description": (
                f"Create a drawing or sketch about {title} and add at least two explanatory labels. "
                f"The drawing should show key parts or ideas, not only appearance."
            ),
            "link": None,
            "feasibility_notes": (
                f"This task is proposed directly from the media_context '{mc}', so it does not require distance, weather, or a physical place."
            )
        }

    if category == "Notes":
        if lang == "es":
            return {
                "task_type": "Notes",
                "task_title": f"Apuntes estructurados sobre {title}",
                "task_description": (
                    f"Escribe una nota breve con 3 ideas clave sobre {title}. Después, añade una frase final explicando cómo se relacionan entre sí."
                ),
                "link": None,
                "feasibility_notes": (
                    f"La tarea aclara explícitamente el formato de respuesta (apuntes/nota) porque el media_context propuesto es '{mc}'."
                )
            }
        return {
            "task_type": "Notes",
            "task_title": f"Structured notes about {title}",
            "task_description": (
                f"Write a short note with 3 key ideas about {title}. Then add one final sentence explaining how those ideas relate to one another."
            ),
            "link": None,
            "feasibility_notes": (
                f"The task explicitly clarifies the response format (notes) because the proposed media_context is '{mc}'."
            )
        }

    if category == "Reading":
        if lang == "es":
            return {
                "task_type": "Reading",
                "task_title": f"Lectura y nota breve sobre {title}",
                "task_description": (
                    f"Lee el recurso o texto disponible sobre {title} y escribe una nota breve con dos ideas principales y una relación entre ellas."
                ),
                "link": None,
                "feasibility_notes": (
                    f"Se propone una tarea de lectura seguida de nota breve porque el media_context es '{mc}'."
                )
            }
        return {
            "task_type": "Reading",
            "task_title": f"Reading and short note about {title}",
            "task_description": (
                f"Read the available resource or text about {title} and write a short note with two main ideas and one relationship between them."
            ),
            "link": None,
            "feasibility_notes": (
                f"A reading-followed-by-note task is proposed because the media_context is '{mc}'."
            )
        }

    if category == "Annotation":
        if lang == "es":
            return {
                "task_type": "Annotation",
                "task_title": f"Anotación guiada sobre {title}",
                "task_description": (
                    f"Anota un texto, imagen o dibujo relacionado con {title}. Marca dos elementos relevantes y añade una breve explicación de por qué son importantes."
                ),
                "link": None,
                "feasibility_notes": (
                    f"La tarea explicita el formato de anotación porque el media_context propuesto es '{mc}'."
                )
            }
        return {
            "task_type": "Annotation",
            "task_title": f"Guided annotation about {title}",
            "task_description": (
                f"Annotate a text, image, or drawing related to {title}. Mark two relevant elements and add a brief explanation of why they matter."
            ),
            "link": None,
            "feasibility_notes": (
                f"The task explicitly uses annotation because the proposed media_context is '{mc}'."
            )
        }

    if category == "Physical":
        distance_m = place_data.get("distance_m")
        open_status = place_data.get("open_status", "unknown")
        fee_status = place_data.get("fee_status", "unknown")
        place_name = place_data.get("name") or ("el lugar cercano" if lang == "es" else "the nearby place")
        address = place_data.get("address") or ""
        condition = weather_data.get("condition")
        temp_f = weather_data.get("temperature_f")

        bad_weather_or_hot = (condition in {"rainy", "stormy"}) or (temp_f is not None and temp_f > 96)
        good_weather_and_not_hot = (condition in {"sunny", "clear", "cloudy"}) and (temp_f is not None and temp_f <= 96)
        site_is_open = (open_status == "open")
        site_is_free = (fee_status == "free")

        if distance_m is not None and distance_m <= 1000:
            if bad_weather_or_hot and site_is_open and site_is_free:
                if lang == "es":
                    return {
                        "task_type": "Indoor",
                        "task_title": f"Actividad interior en {place_name}",
                        "task_description": (
                            f"Entra en {place_name} {f'({address})' if address else ''} y registra dos elementos relacionados con {title}. "
                            f"Después, escribe una explicación breve conectando ambos elementos."
                        ),
                        "link": _strict_resource_link(place_data.get("url")),
                        "feasibility_notes": (
                            f"Se propone una actividad interior porque el media_context es '{mc}', la distancia es {distance_m} m, "
                            f"el clima es '{condition}' y el lugar aparece abierto y gratuito."
                        )
                    }
                return {
                    "task_type": "Indoor",
                    "task_title": f"Indoor activity at {place_name}",
                    "task_description": (
                        f"Go inside {place_name} {f'({address})' if address else ''} and identify two elements related to {title}. "
                        f"Then write a short explanation connecting both elements."
                    ),
                    "link": _strict_resource_link(place_data.get("url")),
                    "feasibility_notes": (
                        f"An indoor activity is proposed because the media_context is '{mc}', the distance is {distance_m} m, "
                        f"the weather is '{condition}', and the place appears open and free."
                    )
                }

            if good_weather_and_not_hot:
                if lang == "es":
                    return {
                        "task_type": "Outdoor",
                        "task_title": f"Observación exterior sobre {title}",
                        "task_description": (
                            f"Observa el exterior de {place_name} {f'({address})' if address else ''} y toma dos notas sobre rasgos relacionados con {title}. "
                            f"Después, explica qué relación tienen con el contenido trabajado."
                        ),
                        "link": _strict_resource_link(place_data.get("url")),
                        "feasibility_notes": (
                            f"Se propone una actividad exterior porque el media_context es '{mc}', la distancia es {distance_m} m "
                            f"y las condiciones permiten trabajo fuera aunque el acceso interior no sea necesariamente viable."
                        )
                    }
                return {
                    "task_type": "Outdoor",
                    "task_title": f"Outdoor observation about {title}",
                    "task_description": (
                        f"Observe the outside of {place_name} {f'({address})' if address else ''} and take two notes about features related to {title}. "
                        f"Then explain how they connect to the content being studied."
                    ),
                    "link": _strict_resource_link(place_data.get("url")),
                    "feasibility_notes": (
                        f"An outdoor activity is proposed because the media_context is '{mc}', the distance is {distance_m} m, "
                        f"and conditions allow outdoor work even if indoor access is not necessarily viable."
                    )
                }

        if lang == "es":
            return {
                "task_type": "Virtual",
                "task_title": f"Tarea virtual sobre {title}",
                "task_description": (
                    f"Revisa un recurso fiable sobre {title} y redacta una respuesta que avance desde {current_level} hacia {target_level}, "
                    f"conectando ideas en lugar de solo listarlas."
                ),
                "link": _strict_resource_link(place_data.get("url")),
                "feasibility_notes": (
                    f"Se propone una tarea virtual porque el media_context es '{mc}', pero la distancia o las condiciones contextuales no hacen viable una actividad presencial."
                )
            }
        return {
            "task_type": "Virtual",
            "task_title": f"Virtual task about {title}",
            "task_description": (
                f"Review a reliable resource about {title} and write a response that moves from {current_level} toward {target_level}, "
                f"connecting ideas rather than only listing them."
            ),
            "link": _strict_resource_link(place_data.get("url")),
            "feasibility_notes": (
                f"A virtual task is proposed because the media_context is '{mc}', but distance or contextual conditions do not make an in-person activity viable."
            )
        }

    # Default virtual
    if lang == "es":
        return {
            "task_type": "Virtual",
            "task_title": f"Profundización sobre {title}",
            "task_description": (
                f"Elabora una respuesta breve sobre {title} que mejore la integración de ideas y avance desde {current_level} hacia {target_level}."
            ),
            "link": None,
            "feasibility_notes": (
                f"La tarea se plantea como virtual porque el media_context '{mc}' no requiere interacción física ni se dispone de un recurso contextual fiable."
            )
        }
    return {
        "task_type": "Virtual",
        "task_title": f"Deepening task about {title}",
        "task_description": (
            f"Write a short response about {title} that improves integration of ideas and moves from {current_level} toward {target_level}."
        ),
        "link": None,
        "feasibility_notes": (
            f"The task is proposed as virtual because the media_context '{mc}' does not require physical interaction and no reliable contextual resource is available."
        )
    }
# ---------------------- React Layer Agent ----------------------------- #
@app.route("/generate-reaction", methods=["POST"])
def generate_reaction():
    """
    Media_context-first reaction generator.

    Behavior:
      - Retrieves latest student history for the given KC.
      - Uses LDA media_context as the primary driver.
      - Applies the 1 km rule only for physical/location-based media_context.
      - Returns pedagogical reaction fields plus contextual task details.
      - Avoids guessed or empty links.
    """
    data = request.get_json() or {}
    kc_id = data.get("kc_id")
    student_id = data.get("student_id")

    if not kc_id or not student_id:
        return jsonify({"error": "kc_id and student_id are required"}), 400

    kc_meta = kc_store.get(kc_id)
    if not kc_meta:
        return jsonify({"error": f"KC with ID {kc_id} not found"}), 404

    # KC metadata
    kc_title = (kc_meta.get("title") or "").strip()
    kc_desc = (kc_meta.get("kc_description") or "").strip()
    target_SOLO = (kc_meta.get("target_SOLO_level") or "").strip() or "Relational"
    media_context = kc_meta.get("media_context") or ""
    related_learning_activity_id = kc_meta.get("related_learning_activity_id")

    # Student history scoped to this KC
    kc_history = [
        r for r in student_history
        if r.get("student_id") == student_id and r.get("kc_id") == kc_id
    ]
    if not kc_history:
        return jsonify({
            "error": f"No student historical data found for student_id={student_id} and kc_id={kc_id}"
        }), 404

    latest_record = sorted(kc_history, key=lambda r: r.get("timestamp") or "", reverse=True)[0]

    learning_activity_id = latest_record.get("learning_activity_id") or related_learning_activity_id
    learning_activity_title = latest_record.get("learning_activity_title")
    if not learning_activity_title and learning_activity_id:
        activity_data = activity_store.get(learning_activity_id, {})
        learning_activity_title = activity_data.get("learning_activity_title")

    current_SOLO = latest_record.get("SOLO_level") or "Pre-structural"
    lang = _infer_language_from_record(latest_record)
    student_response_type = latest_record.get("student_response_type") or "text"
    student_response_summary = _summarize_student_response(latest_record)

    # History for same learning activity only (for trajectory claims)
    same_activity_history = [
        r for r in student_history
        if r.get("student_id") == student_id
        and r.get("learning_activity_id") == learning_activity_id
    ]

    reflective_prompt = _reflective_prompt(current_SOLO, target_SOLO, kc_title, lang)
    scaffolded_response = _scaffolded_response(current_SOLO, target_SOLO, kc_title, kc_desc, lang)
    educator_summary = _educator_summary_for_activity(same_activity_history, latest_record, lang)

    category = _media_context_category(media_context)
    contextual_basis = _contextual_basis(media_context, category, lang)

    timestamp = latest_record.get("timestamp")
    timezone = latest_record.get("timezone")
    location = latest_record.get("location")
    lat = latest_record.get("lat")
    lng = latest_record.get("lng")

    nearest_place = None
    weather = None

    # Only run contextual APIs for physical media_context
    if category == "Physical":
        if lat is None or lng is None:
            return jsonify({
                "error": (
                    "The media_context requires physical/contextual activity, "
                    "but no student coordinates are available in history."
                )
            }), 400

        kc_city = (kc_meta.get("kc_city") or "").strip()
        place_url = None
        open_status = "unknown"
        fee_status = "unknown"
        resource_name = "Unavailable"
        site_address = "Unavailable"
        site_lat = site_lon = None
        distance_m = None

        try:
            keywords = _build_site_keywords(kc_title, kc_desc)
            nearest = _google_nearest_place(
                lat,
                lng,
                keywords,
                GOOGLE_API_KEY,
                exclude_city=kc_city or None
            )
            if nearest:
                site_lat = nearest.get("lat")
                site_lon = nearest.get("lng")
                resource_name = nearest.get("name", "Unknown")
                site_address = nearest.get("address", "Unknown")

                details = _google_place_details(nearest.get("place_id"), GOOGLE_API_KEY)
                if isinstance(details.get("open_now"), bool):
                    open_status = "open" if details["open_now"] else "closed"
                if details.get("price_level") == 0:
                    fee_status = "free"

                # Only keep reliable links
                place_url = _strict_resource_link(details.get("website") or details.get("maps_url"))

                if site_lat is not None and site_lon is not None:
                    distance_m = int(haversine(lat, lng, site_lat, site_lon))
        except Exception as e:
            app.logger.warning(f"React places/context error: {e}")

        if distance_m is not None and distance_m <= 1000:
            condition, temp_f = get_weather(lat, lng)
            weather = {
                "condition": condition,
                "temperature_f": temp_f
            }

        nearest_place = {
            "name": resource_name,
            "address": site_address,
            "url": place_url,
            "distance_m": distance_m,
            "open_status": open_status,
            "fee_status": fee_status
        }

        contextual_task = _task_from_media_context(
            category=category,
            kc_title=kc_title,
            current_level=current_SOLO,
            target_level=target_SOLO,
            media_context=media_context,
            lang=lang,
            place_data=nearest_place,
            weather_data=weather,
        )
    else:
        contextual_task = _task_from_media_context(
            category=category,
            kc_title=kc_title,
            current_level=current_SOLO,
            target_level=target_SOLO,
            media_context=media_context,
            lang=lang,
        )

    # Never return empty/guessed links
    if not contextual_task.get("link"):
        contextual_task["link"] = None

    return jsonify({
        "kc_id": kc_id,
        "student_id": student_id,
        "learning_activity_id": learning_activity_id,
        "learning_activity_title": learning_activity_title,
        "student_response_type": student_response_type,
        "student_response_summary": student_response_summary,
        "timestamp": timestamp,
        "timezone": timezone,
        "location": location,
        "current_SOLO_level": current_SOLO,
        "target_SOLO_level": target_SOLO,
        "reflective_prompt": reflective_prompt,
        "scaffolded_response": scaffolded_response,
        "educator_summary": educator_summary,
        "contextual_basis": contextual_basis,
        "nearest_place": nearest_place,
        "weather": weather,
        "contextual_task": contextual_task
    }), 200

# if __name__ == "__main__":
#     app.run(debug=True)