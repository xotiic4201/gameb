from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx
import random
from datetime import datetime

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Real camera database from research [citation:1][citation:2][citation:4]
CAMERAS = [
    {"name": "Helsinki - Kehä 1", "lat": 60.233, "lon": 24.866, 
     "url": "https://weathercam.digitraffic.fi/C0151301.jpg", "country": "Finland"},
    {"name": "Glasgow City", "lat": 55.864, "lon": -4.251, 
     "url": "https://glasgow-cctv.ubdc.ac.uk/api/yolo/image/1", "country": "UK"},
    # ... more from database
]

@app.get("/api/cameras/nearby")
async def get_nearby_cameras(lat: float, lon: float, radius: int = 50):
    """Find cameras within radius (km) of coordinates [citation:5]"""
    nearby = []
    for cam in CAMERAS:
        distance = calculate_distance(lat, lon, cam["lat"], cam["lon"])
        if distance <= radius:
            cam["distance"] = round(distance, 2)
            nearby.append(cam)
    return {"cameras": nearby, "count": len(nearby)}

@app.get("/api/camera/feed/{camera_id}")
async def get_camera_feed(camera_id: str):
    """Proxy camera images to avoid CORS"""
    camera = next((c for c in CAMERAS if c["name"] == camera_id), None)
    if not camera:
        return {"error": "Camera not found"}
    
    async with httpx.AsyncClient() as client:
        response = await client.get(camera["url"])
        return Response(content=response.content, media_type="image/jpeg")

def calculate_distance(lat1, lon1, lat2, lon2):
    """Haversine formula for distance in km"""
    # Implementation
    pass
