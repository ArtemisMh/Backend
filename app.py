from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
from zoneinfo import ZoneInfo
import uuid
import requests
import os
import math


app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})  # adjust/restrict origins as needed


# -------------------------- Environment keys --------------------------- #
OPENCAGE_API_KEY = os.getenv("OPENCAGE_API_KEY")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY") # Only for timezone lookup

# --------------------------- In-memory stores -------------------------- #
kc_store = {}
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
    app.logger.info(f"KC stored: {kc_id}")
    return jsonify({
        "status": "success",
        "message": f"Knowledge component {kc_id} received",
        "kc": data
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

    # Return only key metadata fields
    return jsonify({
        "kc_id": kc_data.get("kc_id"),
        "title": kc_data.get("title"),
        "target_SOLO_level": kc_data.get("target_SOLO_level")
    }), 200

@app.route("/list_kcs", methods=["GET"])
def list_kcs():
    return jsonify({"kcs": list(kc_store.values())}), 200

# ---------------------- Student History (GET) ------------------------- #    
@app.route("/get-student-history", methods=["GET"])
def get_student_history():
    student_id = request.args.get("student_id")
    kc_id = request.args.get("kc_id")
    latest = (request.args.get("latest", "") or "").lower() == "true"

    if not student_id:
        return jsonify({"error": "student_id is required"}), 400

    # Filter stored records
    results = [r for r in student_history if r.get("student_id") == student_id]
    if kc_id:
        results = [r for r in results if r.get("kc_id") == kc_id]

    # Sort by timestamp (ISO strings sort lexicographically if consistent)
    results_sorted = sorted(results, key=lambda r: r.get("timestamp", ""), reverse=True)
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
            "educational_grade": record.get("educational_grade"),
            "SOLO_level": record.get("SOLO_level"),
            "student_response": record.get("student_response"),
            "justification": record.get("justification"),
            "misconceptions": record.get("misconceptions"),
            "target_SOLO_level": record.get("target_SOLO_level")
        })

    return jsonify({"records": response}), 200

# ---------------------- Analyze Layer Agent --------------------------- #
@app.route("/analyze-response", methods=["POST"])
def analyze_response():
    data = request.get_json() or {}
    kc_id = data.get("kc_id")
    student_id = data.get("student_id")
    educational_grade_text = data.get("educational_grade")  # keep original casing
    response_text = (data.get("student_response") or "").lower()

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
        "educational_grade": educational_grade_text,
        "SOLO_level": solo_level,
        "justification": justification,
        "misconceptions": None,
        "approved": False   # always start unapproved
    }), 200

# ---------------------- Utilities ------------------------------------ #
def haversine(lat1, lon1, lat2, lon2):
    """Great-circle distance in meters using the Haversine formula."""
    R = 6371000  # Earth radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
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
            "units": "imperial"  # Fahrenheit
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
            return plat, plng, loc, None  # keep provided string as label

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

    # Unknown coords
    return None, None, (loc if isinstance(loc, str) else None), None

def _now_in_timezone(tz_name: str):
    """
    Returns (timestamp_iso, tz_name_final). Falls back to UTC if tz_name is missing/invalid.
    Uses Python's zoneinfo (no pytz dependency).
    """
    try:
        tz = ZoneInfo(tz_name) if tz_name else ZoneInfo("UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    dt = datetime.now(tz)
    # ISO 8601 with offset, e.g., 2025-09-01T10:22:13+0200
    return dt.strftime("%Y-%m-%dT%H:%M:%S%z"), str(tz)


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
        "rankby": "distance",   # nearest-first, no radius cap
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
            results = _nearby_rankby_distance(lat, lng, "library OR school OR learning center OR educational resource", api_key)
        except Exception:
            results = []

    if not results:
        return None

    # Prefer a result not in exclude_city (soft filter)
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
    Stores a SOLO assessment result and normalizes location:
      - Accepts numeric lat/lng, or a "lat,lng" string in 'location', or a free-text 'location'.
      - If free-text, geocodes via OpenCage to get lat/lng and a formatted label.
      - Derives timezone from geocoding annotations when available; computes local timestamp.
    """
    data = request.get_json() or {}
    app.logger.info(f"/store-history payload: {data}")

    # Check approval first
    approved = data.get("approved")
    if not approved:
        return jsonify({
            "error": "Teacher approval required before storing analysis",
            "hint": "Resend with 'approved': true once verified by a teacher."
        }), 400

    # Required core fields
    student_id = data.get("student_id")
    kc_id = data.get("kc_id")
    SOLO_level = data.get("SOLO_level")

    if not student_id or not kc_id or not SOLO_level:
        return jsonify({"error": "student_id, kc_id, and SOLO_level are required"}), 400

    # Optional fields the Analyze Layer Agent may include
    student_response = data.get("student_response")
    justification = data.get("justification")
    misconceptions = data.get("misconceptions")
    target_SOLO_level = data.get("target_SOLO_level")
    educational_grade = data.get("educational_grade")

    # Normalize/resolve coordinates and location label
    lat, lng, formatted_loc, tz_name_from_geo = _ensure_coordinates_and_location(data)
    app.logger.info(f"Normalized -> lat={lat}, lng={lng}, formatted='{formatted_loc}', tz='{tz_name_from_geo}'")

    if lat is None or lng is None:
        return jsonify({
            "error": (
                "Could not resolve coordinates from the provided location. "
                "Send numeric 'lat' and 'lng', or 'location' as 'lat,lng', "
                "or a geocodable place/address string."
            )
        }), 400

    # Timezone + timestamp: prefer geocoded timezone; otherwise UTC
    timestamp_iso, tz_final = _now_in_timezone(tz_name_from_geo)

    # Build the record
    record = {
        "timestamp": timestamp_iso,
        "location": formatted_loc or data.get("location"),
        "kc_id": kc_id,
        "student_id": student_id,
        "SOLO_level": SOLO_level,
        "student_response": student_response,
        "justification": justification,
        "misconceptions": misconceptions,
        "target_SOLO_level": target_SOLO_level,
        "educational_grade": educational_grade,
        "lat": lat,
        "lng": lng,
        "timezone": tz_final,
        "approved": True
    }

    # Persist in-memory
    student_history.append(record)

    return jsonify({
        "status": "ok",
        "stored": {
            "student_id": student_id,
            "kc_id": kc_id,
            "SOLO_level": SOLO_level,
            "timestamp": timestamp_iso,
            "timezone": tz_final,
            "location": record["location"],
            "lat": lat,
            "lng": lng,
            "approved": True
        }
    }), 200

# ---------------------- React Layer Agent ----------------------------- #

@app.route("/generate-reaction", methods=["POST"])
def generate_reaction():
    """
    Returns:
      kc_id, student_id,
      location: { formatted, coordinates, lat, lng, timestamp, timezone },
      nearest_place: { name, address, url, distance_m|null, open_status, fee_status },
      weather: null OR { condition, temperature_f },
      task: { task_type, task_title, task_description, link|null, feasibility_notes }
    """
    data = request.get_json() or {}
    kc_id = data.get("kc_id")
    student_id = data.get("student_id")
    if not kc_id or not student_id:
        return jsonify({"error": "kc_id and student_id are required"}), 400

    # 1) Latest stored coordinates from history (authoritative)
    lat1 = lon1 = None
    last_rec = None
    for rec in reversed(student_history):
        if rec.get("student_id") == student_id and rec.get("kc_id") == kc_id:
            lat1 = rec.get("lat")
            lon1 = rec.get("lng")
            last_rec = rec
            break
    if lat1 is None or lon1 is None or last_rec is None:
        return jsonify({"error": "Student coordinates not found in the history for the given kc_id and student_id."}), 400

    location_block = {
        "formatted": last_rec.get("location"),
        "coordinates": f"{lat1},{lon1}",
        "lat": lat1,
        "lng": lon1,
        "timestamp": last_rec.get("timestamp"),
        "timezone": last_rec.get("timezone"),
    }

    # 2) Current SOLO, KC metadata
    current_SOLO = last_rec.get("SOLO_level") or ""
    kc_meta = kc_store.get(kc_id, {})
    kc_title = (kc_meta.get("title") or "").strip()
    kc_desc  = (kc_meta.get("description") or "").strip()
    target_SOLO = (kc_meta.get("target_SOLO_level") or "").strip()
    kc_city = (kc_meta.get("kc_city") or "").strip()  # optional, if provided in KC

    # 3) Nearest relevant site (rank-by-distance) with optional city exclusion
    site_lat = site_lon = None
    resource_name = "Unavailable"
    site_address = "Unavailable"
    site_url = None
    open_status = "unknown"   # "open"|"closed"|"unknown"
    fee_status  = "unknown"   # "free"|"unknown"

    try:
        keywords = _build_site_keywords(kc_title, kc_desc)
        nearest = _google_nearest_place(lat1, lon1, keywords, GOOGLE_API_KEY, exclude_city=kc_city or None)
        if nearest:
            site_lat = nearest["lat"]
            site_lon = nearest["lng"]
            resource_name = nearest["name"]
            site_address = nearest["address"]

            details = _google_place_details(nearest["place_id"], GOOGLE_API_KEY)
            if isinstance(details.get("open_now"), bool):
                open_status = "open" if details["open_now"] else "closed"
            if "price_level" in details and details["price_level"] == 0:
                fee_status = "free"
            site_url = details.get("website") or details.get("maps_url")
    except Exception as e:
        app.logger.warning(f"Places search/details error: {e}")
        site_lat = site_lon = None  # distance unknown

    # 4) Distance FIRST
    if site_lat is not None and site_lon is not None:
        distance_m = haversine(lat1, lon1, site_lat, site_lon)
    else:
        distance_m = None

    is_within_1km = (distance_m is not None) and (distance_m <= 1000)
    app.logger.info(f"/generate-reaction student={student_id} kc={kc_id} "
                    f"latest=({lat1},{lon1}) site=({site_lat},{site_lon}) distance={distance_m}")

    # Helper: best heritage link for virtual tasks
    details_for_link = {"website": site_url} if site_url else {}
    best_link = _best_heritage_link(resource_name, details_for_link, kc_title, last_rec.get("location") or "")

    # 5) If distance unknown OR > 1 km → Virtual (skip weather/access)
    if (distance_m is None) or (not is_within_1km):
        question = _solo_transition_prompt(current_SOLO, target_SOLO, kc_title or kc_desc, "es")
        task = {
            "task_type": "Virtual",
            "task_title": f"Exploración virtual: {kc_title or 'material'}",
            "task_description": (
                f"Revisa el recurso en línea y responde: {question} "
                "Incluye 1 evidencia (captura o cita del material) en tu respuesta."
            ),
            "link": best_link,
            "feasibility_notes": (
                f"Distance is {'unknown' if distance_m is None else int(distance_m)} m. "
                "Regla: al superar 1000 m (o sin recurso cercano), se omiten clima/acceso y se asigna tarea virtual."
            )
        }

        return jsonify({
            "kc_id": kc_id,
            "student_id": student_id,
            "location": location_block,
            "nearest_place": {
                "name": resource_name,
                "address": site_address,
                "url": site_url,
                "distance_m": (None if distance_m is None else int(distance_m)),
                "open_status": "unknown",
                "fee_status": "unknown"
            },
            "weather": None,
            "task": task
        }), 200

    # 6) Within 1 km → check weather & temperature, then decide task
    condition, temp_f = get_weather(lat1, lon1)
    bad_weather_or_hot       = (condition in {"rainy", "stormy"}) or (temp_f is not None and temp_f > 96)
    good_weather_and_not_hot = (condition in {"sunny", "clear", "cloudy"}) and (temp_f is not None and temp_f <= 96)
    site_is_open             = (open_status == "open")
    site_is_free             = (fee_status  == "free")

    if bad_weather_or_hot and site_is_open and site_is_free:
        task = {
            "task_type": "Indoor",
            "task_title": f"Exploración interior en {resource_name}",
            "task_description": (
                f"Entra a {resource_name} ({site_address}). Busca un elemento que conecte con «{kc_title or kc_desc}» "
                "y explica en 3 oraciones qué ves, qué significa y cómo se relaciona con el tema."
            ),
            "feasibility_notes": (
                f"Within 1 km ({int(distance_m)} m). Clima='{condition}', "
                f"temp={'unknown' if temp_f is None else f'{temp_f}°F'}. Recurso accesible y gratuito."
            )
        }

    elif good_weather_and_not_hot and (not site_is_open or not site_is_free):
        task = {
            "task_type": "Outdoor",
            "task_title": f"Observación exterior de {resource_name}",
            "task_description": (
                f"Desde el exterior de {resource_name}, identifica dos rasgos visibles relacionados con «{kc_title or kc_desc}». "
                "Describe su función y semejanza/diferencia en 3–4 oraciones."
            ),
            "feasibility_notes": (
                f"Within 1 km ({int(distance_m)} m). Clima='{condition}', "
                f"temp={'unknown' if temp_f is None else f'{temp_f}°F'} (≤96°F). Interior no accesible (cerrado o con costo)."
            )
        }

    elif good_weather_and_not_hot and site_is_open and site_is_free:
        task = {
            "task_type": "Outdoor",
            "task_title": f"Recorrido guiado al aire libre en {resource_name}",
            "task_description": (
                f"Rodea {resource_name}. Toma dos notas o ejemplos de detalles que expliquen «{kc_title or kc_desc}». "
                "Compara su función y relación con el tema en 4 oraciones."
            ),
            "feasibility_notes": (
                f"Within 1 km ({int(distance_m)} m). Clima='{condition}', "
                f"temp={'unknown' if temp_f is None else f'{temp_f}°F'} (≤96°F). Recurso accesible y gratuito."
            )
        }

    else:
        # Safe fallback: virtual with site-specific link
        question = _solo_transition_prompt(current_SOLO, target_SOLO, kc_title or kc_desc, "es")
        task = {
            "task_type": "Virtual",
            "task_title": f"Exploración virtual (resguardo): {kc_title or 'material'}",
            "task_description": (
                f"Revisa el recurso en línea y responde: {question} "
                "Incluye 1 evidencia (captura o cita del material)."
            ),
            "link": _best_heritage_link(resource_name, {"website": site_url} if site_url else {}, kc_title, last_rec.get("location") or ""),
            "feasibility_notes": (
                f"Within 1 km ({int(distance_m)} m), pero condiciones insuficientes "
                f"(clima='{condition}', temp={temp_f}, open='{open_status}', fee='{fee_status}')."
            )
        }

    return jsonify({
        "kc_id": kc_id,
        "student_id": student_id,
        "location": location_block,
        "nearest_place": {
            "name": resource_name,
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

# if __name__ == "__main__":
#     app.run(debug=True)