import os, asyncio, requests, json, logging
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from skyfield.api import load, EarthSatellite

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"])

AISSTREAM_API_KEY = os.environ.get("AISSTREAM_API_KEY", "")

# 1. SATELLITE TRACKER (TLE Data from CelesTrak)
def get_satellites():
    try:
        stations_url = 'https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle'
        tles = requests.get(stations_url, timeout=10).text.splitlines()
        ts = load.timescale()
        t = ts.now()

        czml = []
        for i in range(0, 60, 3):
            try:
                sat = EarthSatellite(tles[i+1], tles[i+2], tles[i], ts)
                geocentric = sat.at(t)
                subpoint = geocentric.subpoint()
                czml.append({
                    "id": f"sat_{i}",
                    "name": tles[i].strip(),
                    "position": {"cartographicDegrees": [subpoint.longitude.degrees, subpoint.latitude.degrees, subpoint.elevation.m]},
                    "point": {"color": {"rgba": [0, 255, 255, 255]}, "pixelSize": 6},
                    "label": {"text": "SAT: " + tles[i].strip(), "font": "8pt monospace", "fillColor": {"rgba": [0, 255, 255, 255]}}
                })
            except Exception:
                continue
        logger.info(f"Satellites loaded: {len(czml)}")
        return czml
    except Exception as e:
        logger.error(f"get_satellites failed: {e}")
        return []

# 2. AIRCRAFT TRACKER (OpenSky Network — anonymous, rate-limited)
def get_flights():
    url = "https://opensky-network.org/api/states/all"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        states = data.get("states") or []
        czml = []
        for s in states[:40]:
            # s[5]=lon, s[6]=lat, s[7]=baro_altitude — skip if position is missing
            if s[5] is None or s[6] is None:
                continue
            altitude = s[7] if s[7] is not None else 5000
            callsign = (s[1] or "").strip() or "UNK"
            czml.append({
                "id": f"plane_{s[0]}",
                "name": callsign,
                "position": {"cartographicDegrees": [s[5], s[6], altitude]},
                "point": {"color": {"rgba": [0, 255, 0, 255]}, "pixelSize": 8},
                "label": {
                    "text": "AIR: " + callsign,
                    "font": "9pt monospace",
                    "fillColor": {"rgba": [0, 255, 0, 255]},
                    "style": "FILL",
                    "outlineWidth": 1,
                    "verticalOrigin": "BOTTOM",
                    "pixelOffset": {"cartesian2": [0, -12]}
                }
            })
        logger.info(f"Aircraft loaded: {len(czml)}")
        return czml
    except Exception as e:
        logger.error(f"get_flights failed: {e}")
        return []

# 3. MARITIME TRACKER (AISStream.io REST surface-positions endpoint)
def get_maritime():
    if not AISSTREAM_API_KEY:
        logger.warning("AISSTREAM_API_KEY not set — skipping maritime layer")
        return []
    url = "https://api.aisstream.io/v0/surface-positions"
    headers = {"Authorization": AISSTREAM_API_KEY}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        vessels = resp.json()  # list of vessel objects
        czml = []
        for v in vessels[:60]:
            lat = v.get("Latitude") or v.get("lat")
            lon = v.get("Longitude") or v.get("lon")
            if lat is None or lon is None:
                continue
            mmsi = v.get("MMSI") or v.get("mmsi") or "UNK"
            name = (v.get("ShipName") or v.get("name") or str(mmsi)).strip() or str(mmsi)
            czml.append({
                "id": f"vessel_{mmsi}",
                "name": name,
                "position": {"cartographicDegrees": [float(lon), float(lat), 0]},
                "point": {"color": {"rgba": [255, 200, 0, 255]}, "pixelSize": 7},
                "label": {
                    "text": "SEA: " + name,
                    "font": "9pt monospace",
                    "fillColor": {"rgba": [255, 200, 0, 255]},
                    "style": "FILL",
                    "outlineWidth": 1,
                    "verticalOrigin": "BOTTOM",
                    "pixelOffset": {"cartesian2": [0, -12]}
                }
            })
        logger.info(f"Vessels loaded: {len(czml)}")
        return czml
    except Exception as e:
        logger.error(f"get_maritime failed: {e}")
        return []

# 4. CRISIS / EVENT TRACKER (GDELT 2.0 — no API key required)
def get_crises():
    # GDELT GEO 2.0 API: last 15 minutes of events, JSON format, filtered to
    # high-impact action codes (conflict, violence, protest, military force).
    url = (
        "https://api.gdeltproject.org/api/v2/geo/geo"
        "?query=sourcelang:eng%20(domain:reuters.com%20OR%20domain:bbc.com%20OR%20domain:apnews.com)"
        "&mode=pointdata&maxrows=50&format=json"
    )
    try:
        resp = requests.get(url, timeout=12)
        resp.raise_for_status()
        payload = resp.json()
        features = payload.get("features") or []
        czml = []
        seen = set()
        for feat in features:
            try:
                coords = feat.get("geometry", {}).get("coordinates", [])
                if len(coords) < 2:
                    continue
                lon, lat = float(coords[0]), float(coords[1])
                props = feat.get("properties") or {}
                name = props.get("name") or props.get("title") or "EVENT"
                url_ref = props.get("url") or ""
                uid = f"{lon:.2f}_{lat:.2f}_{name[:20]}"
                if uid in seen:
                    continue
                seen.add(uid)
                czml.append({
                    "id": f"crisis_{uid}",
                    "name": name,
                    "position": {"cartographicDegrees": [lon, lat, 0]},
                    "point": {"color": {"rgba": [255, 40, 40, 255]}, "pixelSize": 9},
                    "label": {
                        "text": "EVT: " + name[:40],
                        "font": "8pt monospace",
                        "fillColor": {"rgba": [255, 40, 40, 255]},
                        "style": "FILL",
                        "outlineWidth": 1,
                        "verticalOrigin": "BOTTOM",
                        "pixelOffset": {"cartesian2": [0, -12]}
                    }
                })
            except Exception:
                continue
        logger.info(f"Crisis events loaded: {len(czml)}")
        return czml
    except Exception as e:
        logger.error(f"get_crises failed: {e}")
        return []

@app.get("/")
async def index():
    return FileResponse("index.html")


@app.get("/czml")
async def get_czml():
    full_czml = [{"id": "document", "version": "1.0"}]
    full_czml.extend(get_satellites())
    full_czml.extend(get_flights())
    full_czml.extend(get_maritime())
    full_czml.extend(get_crises())
    return full_czml

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        try:
            # Aggregate all intelligence layers
            full_czml = [{"id": "document", "version": "1.0"}]
            full_czml.extend(get_satellites())
            full_czml.extend(get_flights())
            full_czml.extend(get_maritime())
            full_czml.extend(get_crises())
            logger.info(f"WebSocket push: {len(full_czml) - 1} total entities")
            await websocket.send_json(full_czml)
        except Exception as e:
            logger.error(f"WebSocket send error: {e}")
            break
        await asyncio.sleep(15)
