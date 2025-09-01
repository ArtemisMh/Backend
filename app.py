from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
from zoneinfo import ZoneInfo
import uuid
import requests
import os
import math


app = Flask(__name__)

CORS(app, resources={r"/*": {"origins": "*"}})  # adjust origins as needed

# Secure keys from environment variables
OPENCAGE_API_KEY = os.getenv("OPENCAGE_API_KEY")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY") # Only for timezone lookup


kc_store = {}
student_history = []

# ---------------------- Root route — health check ---------------------- #
@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "success", "message": "Backend is live!"})

# ---------------------- Learning Design Agent ------------------------- #

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
    latest = request.args.get("latest", "").lower() == "true"

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
        "misconceptions": None
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
            return plat, plng, loc, None  # use provided string as label

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
        "timezone": tz_final
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
            "lng": lng
        }
    }), 200

# ---------------------- React Layer Agent ----------------------------- #

@app.route("/generate-reaction", methods=["POST"])
def generate_reaction():
    """
    Returns:
      {
        kc_id, student_id,
        location: { formatted, coordinates, lat, lng, timestamp, timezone },
        nearest_site: { name, address, url, distance_m|null, open_status, fee_status },
        weather: null OR { condition, temperature_f },
        task: {
          task_type: "Virtual"|"Indoor"|"Outdoor",
          task_title, task_description,
          link|null,
          feasibility_notes
        }
      }
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
        return jsonify({"error": "Student coordinates not found in history for the given kc_id and student_id."}), 400

    location_block = {
        "formatted": last_rec.get("location"),
        "coordinates": f"{lat1},{lon1}",
        "lat": lat1,
        "lng": lon1,
        "timestamp": last_rec.get("timestamp"),
        "timezone": last_rec.get("timezone"),
    }

    # 2) KC-driven keyword for relevant site search
    kc = kc_store.get(kc_id, {})
    kc_title = (kc.get("title") or "").strip()
    kc_desc  = (kc.get("description") or "").strip()
    keywords = kc_title if kc_title else (kc_desc if kc_desc else "cultural heritage")

    # 3) Nearest relevant site via Google Places
    site_lat = site_lon = None
    site_name = "Unavailable"
    site_address = "Unavailable"
    site_url = None
    open_status = "unknown"   # "open"|"closed"|"unknown"
    fee_status  = "unknown"   # "free"|"unknown"

    try:
        if GOOGLE_API_KEY:
            nearby_url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
            params = {
                "location": f"{lat1},{lon1}",
                "radius": 1500,          # 1.5 km cone
                "keyword": keywords,
                "key": GOOGLE_API_KEY
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
                    d_params = {"place_id": place_id, "fields": "opening_hours,price_level", "key": GOOGLE_API_KEY}
                    d = requests.get(details_url, params=d_params, timeout=12)
                    if d.ok:
                        dj = d.json() or {}
                        res = dj.get("result", {})
                        if isinstance(res.get("opening_hours", {}).get("open_now"), bool):
                            open_status = "open" if res["opening_hours"]["open_now"] else "closed"
                        if "price_level" in res:
                            fee_status = "free" if res["price_level"] == 0 else "unknown"
    except Exception as e:
        app.logger.warning(f"Places API error: {e}")
        site_lat = site_lon = None  # force virtual

    # 4) Distance FIRST
    if site_lat is not None and site_lon is not None:
        distance_m = haversine(lat1, lon1, site_lat, site_lon)
    else:
        distance_m = None  # unknown/no site

    is_within_1km = (distance_m is not None) and (distance_m <= 1000)
    app.logger.info(f"/generate-reaction student={student_id} kc={kc_id} latest=({lat1},{lon1}) "
                    f"site=({site_lat},{site_lon}) distance={distance_m}")

    # Helper: KC-relevant virtual link even without Places
    def kc_virtual_link():
        query = kc_title or kc_desc or "heritage"
        return f"https://en.wikipedia.org/w/index.php?search={requests.utils.quote(query)}"

    # 5) If distance unknown OR > 1 km → Virtual (skip weather/access)
    if (distance_m is None) or (not is_within_1km):
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
                f"Distance is {'unknown' if distance_m is None else int(distance_m)} m. "
                "Al ser mayor a 1000 m o desconocida, se omiten verificaciones de clima y acceso y se asigna actividad virtual."
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
                "distance_m": (None if distance_m is None else int(distance_m)),
                "open_status": "unknown",
                "fee_status": "unknown"
            },
            "weather": None,
            "task": task
        }), 200

    # 6) Within 1 km → check weather & temperature, then decide task
    condition, temp_f = get_weather(lat1, lon1)  # ("sunny"/"cloudy"/"rainy"/"stormy"/"unknown", temp in °F)

    bad_weather_or_hot       = (condition in {"rainy", "stormy"}) or (temp_f is not None and temp_f > 96)
    good_weather_and_not_hot = (condition in {"sunny", "clear", "cloudy"}) and (temp_f is not None and temp_f <= 96)
    site_is_open             = (open_status == "open")
    site_is_free             = (fee_status  == "free")

    if bad_weather_or_hot and site_is_open and site_is_free:
        # A) Bad/hot AND open & free → Indoor
        task = {
            "task_type": "Indoor",
            "task_title": f"Exploración interior en {site_name}",
            "task_description": (
                f"Entra a {site_name} ({site_address}) y observa un elemento simbólico (por ejemplo, un relieve o un vitral). "
                "Escribe tres oraciones: qué ves, qué crees que significa y cómo se conecta con el tema del KC."
            ),
            "feasibility_notes": (
                f"Within 1 km ({int(distance_m)} m). Weather='{condition}', "
                f"temp={'unknown' if temp_f is None else f'{temp_f}°F'}. "
                "Sitio abierto y gratuito; interior recomendado."
            )
        }

    elif good_weather_and_not_hot and (not site_is_open or not site_is_free):
        # B) Good & ≤96°F AND (closed OR not free) → Outdoor
        task = {
            "task_type": "Outdoor",
            "task_title": f"Observación exterior de {site_name}",
            "task_description": (
                f"Desde el exterior de {site_name}, dibuja o fotografía un rasgo visible (arco, torre, fachada). "
                "Explica en dos oraciones cómo ese rasgo se relaciona con el tema del KC."
            ),
            "feasibility_notes": (
                f"Within 1 km ({int(distance_m)} m). Weather='{condition}', "
                f"temp={'unknown' if temp_f is None else f'{temp_f}°F'} (≤ 96°F). "
                "Interior no accesible (cerrado o con costo); actividad exterior."
            )
        }

    elif good_weather_and_not_hot and site_is_open and site_is_free:
        # C) Good & ≤96°F AND open & free → Outdoor
        task = {
            "task_type": "Outdoor",
            "task_title": f"Recorrido guiado al aire libre en {site_name}",
            "task_description": (
                f"Camina alrededor de {site_name} y localiza dos detalles arquitectónicos. "
                "Describe cómo cada detalle ayuda a entender el tema del KC y compara sus funciones."
            ),
            "feasibility_notes": (
                f"Within 1 km ({int(distance_m)} m). Weather='{condition}', "
                f"temp={'unknown' if temp_f is None else f'{temp_f}°F'} (≤ 96°F). "
                "Sitio abierto y gratuito; actividad exterior recomendada."
            )
        }

    else:
        # D) Mixed/unknown → Virtual
        def kc_virtual_link():
            query = kc_title or kc_desc or "heritage"
            return f"https://en.wikipedia.org/w/index.php?search={requests.utils.quote(query)}"
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

# if __name__ == "__main__":
#     app.run(debug=True)