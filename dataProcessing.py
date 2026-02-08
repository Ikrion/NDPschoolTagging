import requests
import pandas as pd
import math
import time
import os
from datetime import datetime

# --- CONFIGURATION ---
EMAIL = "zhanghaien100@gmail.com"
PASSWORD = "Blk-457-13@haien"
TOKEN_FILE = "token_cache.txt"

# --- HELPER FUNCTIONS ---

def get_token():
    auth_url = "https://www.onemap.gov.sg/api/auth/post/getToken"
    res = requests.post(auth_url, json={"email": EMAIL, "password": PASSWORD})
    return res.json().get("access_token")


def get_valid_token():
    # 1. Check if we have a saved token
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r") as f:
            saved_token, expiry_time = f.read().split(",")

        # 2. Check if it's still valid (e.g., within 72 hours)
        if time.time() < float(expiry_time):
            print("Using cached token...")
            return saved_token

    # 3. If no file or expired, request a new one
    print("Token expired or missing. Requesting new token...")
    auth_url = "https://www.onemap.gov.sg/api/auth/post/getToken"
    res = requests.post(auth_url, json={"email": EMAIL, "password": PASSWORD}).json()

    new_token = res.get("access_token")
    # OneMap tokens last 3 days (259200 seconds)
    expiry_timestamp = time.time() + 259200

    # 4. Save to local file
    with open(TOKEN_FILE, "w") as f:
        f.write(f"{new_token},{expiry_timestamp}")

    return new_token


def geocode_address(address, token):
    headers = {"Authorization": token}

    # 1. Get Coordinates first
    search_url = "https://www.onemap.gov.sg/api/common/elastic/search"
    search_params = {"searchVal": address, "returnGeom": "Y", "getAddrDetails": "Y", "pageNum": "1"}

    try:
        res = requests.get(search_url, params=search_params, headers=headers).json()

        if res.get("found", 0) > 0:
            result = res["results"][0]
            lat, lon = result['LATITUDE'], result['LONGITUDE']
            #print(f"📍 Found Coordinates for {address}: {lat}, {lon}")

            # 2. Use Coordinates to find the official Planning Area
            # This is the "Gold Standard" way to get the region
            #area_url = "https://www.onemap.gov.sg/api/public/v2/planningarea/getPlanningArea"
            area_url = f"https://www.onemap.gov.sg/api/public/popapi/getPlanningarea?latitude={lat}&longitude={lon}"
            area_params = {"lat": lat, "log": lon}  # Note: OneMap uses 'log' for longitude here

            # We get the response object first to check the status
            response = requests.request("GET", area_url, headers=headers)
            #area_res = requests.get(area_url, headers=headers)
            #print(f"📡 Planning Area API Status: {response.status_code}")

            if response.status_code == 200:
                area_data = response.json()
                if isinstance(area_data, list) and len(area_data) > 0:
                    area_name = area_data[0].get('pln_area_n', 'UNKNOWN').upper()
                    print(f"🗺️ Area identified as: {area_name}")
                    return float(lat), float(lon), area_name
                else:
                    print(f"⚠️ Area API returned empty list for these coordinates.")
            else:
                print(f"❌ Planning Area API Error: {response.text}")

    except Exception as e:
        print(f"❌ Error during API call: {e}")

    return None, None, "UNKNOWN"


def haversine(lat1, lon1, lat2, lon2):
    """Calculates straight-line distance in km"""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def get_transport_data(token, start_coords, end_coords, mode="pt"):
    """Gets distance and time via Public Transport (pt) or Walk (walk)"""

    # 1. Use a valid current date (OneMap hates past dates)
    current_date = datetime.now().strftime("%m-%d-%Y")  # Format: YYYY-MM-DD MM-DD-YYYY
    current_time = datetime.now().strftime("%H:%M:%S")  # Format: HH:MM:SS

    url = "https://www.onemap.gov.sg/api/public/routingsvc/route"
    headers = {"Authorization": token}
    # Format: lat,lon
    params = {
        "start": f"{start_coords[0]},{start_coords[1]}",
        "end": f"{end_coords[0]},{end_coords[1]}",
        "routeType": "pt",  # Public Transport
        "date": current_date,  # Must be today or future
        "time": "13:00:00",  # Morning peak
        "mode": "TRANSIT",  # Required for pt
        "maxWalkDistance": "1000"  # Increase walk allowance
    }

    try:
        response = requests.get(url, params=params, headers=headers)
        data = response.json()

        # Debug: If things are failing, uncomment the line below to see why
        #print(f"DEBUG Routing Response: {data}")

        # In routingsvc, distance is often inside 'route_summary' or 'itineraries'
        if "plan" in data and "itineraries" in data["plan"]:
            itinerary = data["plan"]["itineraries"][0]

            # Travel time is in seconds
            duration_sec = itinerary.get("duration", 0)
            minutes, seconds = divmod(duration_sec, 60)
            readable_time = f"{int(minutes)}m {int(seconds)}s"
            decimal_minutes = round(duration_sec / 60, 2)  # e.g., 12.5

            # Distance is in meters.
            # If it's not in the top level, check the 'legs'
            distance_m = itinerary.get("distance", 0)

            if distance_m == 0:
                # Sum up distance from all legs (walk -> bus -> walk)
                distance_m = sum(leg.get('distance', 0) for leg in itinerary.get('legs', []))

            return distance_m, decimal_minutes

    except Exception as e:
        print(f"❌ Error: {e}")

    return None, None





# --- MAIN LOGIC ---

def main():
    token = get_valid_token()

    # 1. Load your data (Assuming Excel for this example)
    # user_df = pd.read_excel("users.xlsx")
    # school_df = pd.read_excel("schools.xlsx")

    # Mock Data for testing
    user_data = [{"name": "User A", "address": "730123"}]  # Tampines
    school_data = [
        {"name": "School X", "address": "730556", "area": "WOODLANDS"},  # Same Area
        {"name": "School Y", "address": "640502", "area": "JURONG WEST"}  # Different Area
    ]

    results = []

    for user in user_data:
        print(f"Processing {user['name']}...")
        u_lat, u_lon, u_area = geocode_address(user['address'], token)
        print(f"User is in area: {u_area}")  # DEBUG LINE

        if not u_lat:
            print("Could not find user location!")
            continue

        # 2. REGIONAL FILTERING
        # Only check schools in the same Planning Area
        nearby_schools = [s for s in school_data if s['area'] == u_area]

        for school in nearby_schools:
            print(f"Checking school: {school['name']} in {school['area']}")  # DEBUG LINE
            s_lat, s_lon, _ = geocode_address(school['address'], token)

            if school['area'].upper() == u_area.upper():  # Force uppercase for matching
                print(f"✅ Match found for {school['name']}!")

                s_lat, s_lon, _ = geocode_address(school['address'], token)

                # 3. HAVERSINE DISTANCE (Instant)
                h_dist = haversine(u_lat, u_lon, s_lat, s_lon)

                # 4. TRANSPORT DISTANCE (API call)
                # We only call this for schools that passed the regional filter!
                t_dist, t_time = get_transport_data(token, (u_lat, u_lon), (s_lat, s_lon))

                # Test from SMU (1.296, 103.850) to Orchard (1.304, 103.832)
                #dist, data_time = get_transport_data(token, (1.296, 103.850), (1.304, 103.832))
                #print(f"Distance: {dist}m, Time: {data_time}s")

                results.append({
                    "User": user['name'],
                    "School": school['name'],
                    "Region": u_area,
                    "Straight_Dist_km": round(h_dist, 2),
                    "Transport_Dist_m": t_dist,
                    "Travel_Time_sec": t_time
                })
                time.sleep(0.1)  # Small delay to be nice to the API
            else:
                print(f"❌ {school['name']} is too far (different region).")

            # 3. HAVERSINE DISTANCE (Instant)
            #h_dist = haversine(u_lat, u_lon, s_lat, s_lon)

            # 4. TRANSPORT DISTANCE (API call)
            # We only call this for schools that passed the regional filter!
            #t_dist, t_time = get_transport_data(token, (u_lat, u_lon), (s_lat, s_lon))

            # results.append({
            #     "User": user['name'],
            #     "School": school['name'],
            #     "Region": u_area,
            #     "Straight_Dist_km": round(h_dist, 2),
            #     "Transport_Dist_m": t_dist,
            #     "Travel_Time_sec": t_time
            # })
            # time.sleep(0.1)  # Small delay to be nice to the API

    # 5. Output to Excel
    if not results:
        print("⚠️ No matches found. Excel will be empty.")
    else:
        output_df = pd.DataFrame(results)
        output_df.to_excel("matching_results.xlsx", index=False)
        print(f"Successfully saved {len(results)} rows to Excel.")


if __name__ == "__main__":
    main()