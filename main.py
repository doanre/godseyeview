import os
import requests
import asyncio
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

app = FastAPI()

# Allow your frontend to talk to your backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def get_index():
    return FileResponse('index.html')

async def fetch_osint_data():
    url = "https://opensky-network.org/api/states/all"
    try:
        # Requesting a smaller bounding box (e.g., Europe/Middle East) improves speed
        response = requests.get(url, timeout=5)
        states = response.json().get('states', [])[:30]
        
        czml = [{"id": "document", "name": "WorldView_Feed", "version": "1.0"}]
        for s in states:
            czml.append({
                "id": f"ac_{s[0]}",
                "name": f"Flight {s[1]}",
                "position": {"cartographicDegrees": [s[5] or 0, s[6] or 0, s[7] or 5000]},
                "point": {"color": {"rgba": [0, 255, 0, 255]}, "pixelSize": 8},
                "label": {"text": s[1], "font": "10pt monospace", "showBackground": True}
            })
        return czml
    except:
        return [{"id": "document", "version": "1.0"}]

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        data = await fetch_osint_data()
        await websocket.send_json(data)
        await asyncio.sleep(15)