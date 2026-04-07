import os, asyncio, requests, json
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from skyfield.api import load, EarthSatellite

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"])

# 1. SATELLITE TRACKER (TLE Data from CelesTrak)
def get_satellites():
    stations_url = 'https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle'
    # For a real app, cache this file locally once a day
    tles = requests.get(stations_url).text.splitlines()
    ts = load.timescale()
    t = ts.now()
    
    czml = []
    # Just grab the top 20 active satellites for performance
    for i in range(0, 60, 3): 
        try:
            sat = EarthSatellite(tles[i+1], tles[i+2], tles[i], ts)
            geocentric = sat.at(t)
            subpoint = geocentric.subpoint()
            czml.append({
                "id": f"sat_{i}", "name": tles[i].strip(),
                "position": {"cartographicDegrees": [subpoint.longitude.degrees, subpoint.latitude.degrees, subpoint.elevation.m]},
                "point": {"color": {"rgba": [0, 255, 255, 255]}, "pixelSize": 6},
                "label": {"text": "SAT: " + tles[i].strip(), "font": "8pt monospace", "fillColor": {"rgba": [0, 255, 255, 255]}}
            })
        except: continue
    return czml

# 2. AIRCRAFT TRACKER (OpenSky Network)
def get_flights():
    url = "https://opensky-network.org/api/states/all"
    try:
        data = requests.get(url, timeout=5).json()
        states = data.get('states', [])[:40]
        return [{
            "id": f"plane_{s[0]}", "name": s[1],
            "position": {"cartographicDegrees": [s[5], s[6], s[7] or 5000]},
            "point": {"color": {"rgba": [0, 255, 0, 255]}, "pixelSize": 8},
            "label": {"text": "AIR: " + (s[1] or "UNK"), "font": "9pt monospace", "fillColor": {"rgba": [0, 255, 0, 255]}}
        } for s in states]
    except: return []

@app.get("/")
async def get_czml():
    full_czml = [{"id": "document", "version": "1.0"}]
    full_czml.extend(get_satellites())
    full_czml.extend(get_flights())
    return full_czml

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        # Aggregate all intelligence layers
        full_czml = [{"id": "document", "version": "1.0"}]
        full_czml.extend(get_satellites())
        full_czml.extend(get_flights())
        # Note: For Ships, integrate AISStream.io WebSockets here
        
        await websocket.send_json(full_czml)
        await asyncio.sleep(15)
