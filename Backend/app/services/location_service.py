import requests
from fastapi import HTTPException
from math import radians, sin, cos, sqrt, atan2

# This is a placeholder for a real plus code to lat/lon conversion API
PLUS_CODE_API_URL = "https://plus.codes/api/v1/decode"

def get_lat_lon_from_plus_code(plus_code: str) -> dict:
    """ 
    This function is a placeholder. It's supposed to convert a plus code 
    to latitude and longitude by calling an external API. 
    In a real environment, this would make an actual HTTP request.
    For now, it returns a hardcoded value for demonstration.
    """
    # Fake coordinates for demonstration. 
    # A real implementation would use the requests code below.
    if "8GCRVC24+25" in plus_code: # Example plus code for a shop
        return {"latitude": 28.692656, "longitude": 77.240313}
    else: # Example plus code for a rider
        return {"latitude": 28.7041, "longitude": 77.1025}
    
    # --- Real implementation using requests ---
    # try:
    #     response = requests.get(f"{PLUS_CODE_API_URL}?address={plus_code}")
    #     response.raise_for_status()
    #     data = response.json()
    #     if data.get("plus_code") and data["plus_code"].get("geometry"):
    #         location = data["plus_code"]["geometry"]["location"]
    #         return {"latitude": location["lat"], "longitude": location["lng"]}
    #     else:
    #         raise HTTPException(status_code=400, detail="Invalid plus code")
    # except requests.exceptions.RequestException as e:
    #     raise HTTPException(status_code=500, detail=f"External API error: {e}")

def _haversine_distance(lat1, lon1, lat2, lon2) -> float:
    """Calculate the great-circle distance between two points on the earth."""
    R = 6371  # Radius of the Earth in kilometers

    lat1_rad = radians(lat1)
    lon1_rad = radians(lon1)
    lat2_rad = radians(lat2)
    lon2_rad = radians(lon2)

    dlon = lon2_rad - lon1_rad
    dlat = lat2_rad - lat1_rad

    a = sin(dlat / 2)**2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    distance = R * c
    return distance


def get_distance_between_plus_codes(code1: str, code2: str) -> float:
    """Calculates the distance between two plus codes in kilometers."""
    loc1 = get_lat_lon_from_plus_code(code1)
    loc2 = get_lat_lon_from_plus_code(code2)

    distance = _haversine_distance(
        loc1["latitude"], loc1["longitude"],
        loc2["latitude"], loc2["longitude"]
    )
    
    return distance
