import requests
import pandas as pd
import math
import time
import os
from datetime import datetime
from collections import deque

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
            # minutes, seconds = divmod(duration_sec, 60)
            # readable_time = f"{int(minutes)}m {int(seconds)}s"
            # decimal_minutes = round(duration_sec / 60, 2)  # e.g., 12.5

            # Distance is in meters.
            # If it's not in the top level, check the 'legs'
            distance_m = itinerary.get("distance", 0)

            if distance_m == 0:
                # Sum up distance from all legs (walk -> bus -> walk)
                distance_m = sum(leg.get('distance', 0) for leg in itinerary.get('legs', []))

            return distance_m, duration_sec

    except Exception as e:
        print(f"❌ Error: {e}")

    return None, None


def verify_school_areas(school_excel_path, token):
    # 1. Load your current "Updated" file
    current_df = pd.read_excel(school_excel_path)

    # 2. Create a copy to store fresh API results
    fresh_data = current_df.copy()
    new_areas = []

    print("Checking for changes in Planning Areas...")
    for _, row in fresh_data.iterrows():
        # Call API again to see what it says NOW
        _, _, fresh_area = geocode_address(row['address'], token)
        new_areas.append(fresh_area)
        time.sleep(0.2)

    fresh_data['Planning Area'] = new_areas

    # 3. Compare 'Planning Area' column between current and fresh
    # This will show only the rows where the area name differs
    changes = current_df[current_df['Planning Area'] != fresh_data['Planning Area']]

    if not changes.empty:
        print(f"🚨 Found {len(changes)} differences!")
        print(changes[['school_name', 'Planning Area']])  # Shows old vs new logic
        # You could save these to a 'corrections.xlsx' file
    else:
        print("✅ All school areas match the API records.")


def process_schools(school_excel_path, token):
    # --- STEP 1: LOAD DATA ---
    school_df = pd.read_excel(school_excel_path)
    # --- STEP 2: PRE-PROCESS SCHOOLS (The "Bucket" Strategy) ---
    # We group schools by Planning Area so we don't search all of them every time
    school_buckets = {}
    print("Pre-processing schools...")
    print("Geocoding schools and fetching areas...")

    areas = []
    lats = []
    lons = []

    for _, s_row in school_df.iterrows():
        # Using your working geocode function
        lat, lon, area = geocode_address(s_row['address'], token)

        areas.append(area)
        lats.append(lat)
        lons.append(lon)

        if area not in school_buckets:
            school_buckets[area] = []

        school_buckets[area].append({
            "name": s_row['school_name'],
            "coords": (lat, lon)
        })
        time.sleep(0.1)  # Small delay to avoid rate limits

    # 2. Add the new columns to the DataFrame
    school_df['Planning Area'] = areas
    school_df['Latitude'] = lats
    school_df['Longitude'] = lons

    # 3. Save it back to the same file
    # Ensure the file is CLOSED in Excel before running this!
    school_df.to_excel(school_excel_path, index=False)
    print(f"✅ {school_excel_path} has been updated with new columns.")

    return school_buckets


def process_user_with_swaps(user_excel_path, school_excel_path, token):
    # --- 1. PREPARE SCHOOL DATA ---
    school_df = pd.read_excel(school_excel_path)
    # Track assignments: { school_name: [ {user_data, time}, ... ] }
    school_assignments = {row['school_name']: [] for _, row in school_df.iterrows()}
    # Track capacities: { school_name: max_volunteers }
    school_capacities = {row['school_name']: row.get('max volunteer', 5) for _, row in school_df.iterrows()}

    # Pre-process schools into buckets (Using your existing process_schools logic)
    school_buckets = process_schools(school_excel_path, token)

    # --- 2. PREPARE USER QUEUE & CACHE ---
    user_df = pd.read_excel(user_excel_path)
    # Convert users to a list of dictionaries and put in a queue
    user_queue = deque(user_df.to_dict('records'))

    # Cache to store API results: { (user_name, school_name): (dist, time_sec) }
    # This prevents re-calling the API if a user is bumped and re-processed
    api_cache = {}

    print(f"🚀 Starting Assignment Logic for {len(user_queue)} users...")

    while user_queue:
        current_user = user_queue.popleft()
        u_name = current_user['name']

        # Geocode user to get their area
        u_lat, u_lon, u_area = geocode_address(current_user['address'], token)
        nearby_schools = school_buckets.get(u_area, [])

        if not nearby_schools:
            print(f"⚠️ No schools in {u_area} for {u_name}. Skipping.")
            continue

        # Calculate/Fetch travel times for ALL schools in the area
        travel_options = []
        for school in nearby_schools:
            s_name = school['name']

            # Check cache first
            if (u_name, s_name) in api_cache:
                dist_m, time_sec = api_cache[(u_name, s_name)]
            else:
                dist_m, time_sec = get_transport_data(token, (u_lat, u_lon), school['coords'])
                api_cache[(u_name, s_name)] = (dist_m, time_sec)
                time.sleep(0.2)  # API Rate Limit protection

            if time_sec is not None:
                travel_options.append({
                    'school_name': s_name,
                    'time_sec': time_sec,
                    'dist_m': dist_m,
                    'area': u_area
                })

        # Sort schools by fastest travel time
        travel_options.sort(key=lambda x: x['time_sec'])

        assigned = False
        for option in travel_options:
            target_school = option['school_name']
            u_time = option['time_sec']

            # Check if user has already been rejected/bumped from this school
            # (Optional: Add logic to prevent infinite loops)

            current_volunteers = school_assignments[target_school]
            max_cap = school_capacities[target_school]

            # CASE A: School has space
            if len(current_volunteers) < max_cap:
                school_assignments[target_school].append({
                    'user_data': current_user,
                    'time_sec': u_time,
                    'dist_m': option['dist_m'],
                    'area': u_area
                })
                print(f"✅ {u_name} assigned to {target_school} ({u_time // 60} min)")
                assigned = True
                break

            # CASE B: School is full, check for swap (>10 min / 600 sec difference)
            else:
                # Find the slowest volunteer currently at the school
                current_volunteers.sort(key=lambda x: x['time_sec'], reverse=True)
                slowest = current_volunteers[0]

                time_diff = slowest['time_sec'] - u_time

                if time_diff > 600:  # 600 seconds = 10 minutes
                    # BUMP the slowest person
                    school_assignments[target_school].pop(0)  # Remove slowest
                    bumped_user = slowest['user_data']

                    # Add current user
                    school_assignments[target_school].append({
                        'user_data': current_user,
                        'time_sec': u_time,
                        'dist_m': option['dist_m'],
                        'area': u_area
                    })

                    print(f"🔄 {u_name} bumped {bumped_user['name']} from {target_school} (Saved {time_diff // 60} min)")

                    # Put bumped user back in the queue to find a new school
                    user_queue.append(bumped_user)
                    assigned = True
                    break

        if not assigned:
            print(f"❌ {u_name} could not be assigned to any school in {u_area}.")

    # --- 3. FLATTEN RESULTS & EXPORT ---
    final_results = []
    for s_name, volunteers in school_assignments.items():
        for vol in volunteers:
            mins, secs = divmod(vol['time_sec'], 60)
            final_results.append({
                "School": s_name,
                "User": vol['user_data']['name'],
                "Area": vol['area'],
                "Travel Time": f"{int(mins)}m {int(secs)}s",
                "Minutes": round(vol['time_sec'] / 60, 2),
                "Distance (m)": vol['dist_m']
            })

    result_df = pd.DataFrame(final_results)
    result_df.to_excel("data/final_modeling_assignments.xlsx", index=False)
    print("🎉 All assignments finalized and saved.")


# --- MAIN LOGIC ---

def main():
    token = get_valid_token()

    # 1. Load your data (Assuming Excel for this example)
    # user_df = pd.read_excel("data/users.xlsx")
    # school_df = pd.read_excel("data/schools.xlsx")
    user_file_path = "data/users.xlsx"
    school_file_path = "data/schools.xlsx"

    # Mock Data for testing
    user_data = [{"name": "User A", "address": "730123"}]  # Tampines
    school_data = [
        {"name": "School X", "address": "730556", "area": "WOODLANDS"},  # Same Area
        {"name": "School Y", "address": "640502", "area": "JURONG WEST"}  # Different Area
    ]

    process_user_with_swaps(user_file_path, school_file_path, token)

    # results = []
    #
    # for user in user_data:
    #     print(f"Processing {user['name']}...")
    #     u_lat, u_lon, u_area = geocode_address(user['address'], token)
    #     print(f"User is in area: {u_area}")  # DEBUG LINE
    #
    #     if not u_lat:
    #         print("Could not find user location!")
    #         continue
    #
    #     # 2. REGIONAL FILTERING
    #     # Only check schools in the same Planning Area
    #     nearby_schools = [s for s in school_data if s['area'] == u_area]
    #
    #     for school in nearby_schools:
    #         print(f"Checking school: {school['name']} in {school['area']}")  # DEBUG LINE
    #         s_lat, s_lon, _ = geocode_address(school['address'], token)
    #
    #         if school['area'].upper() == u_area.upper():  # Force uppercase for matching
    #             print(f"✅ Match found for {school['name']}!")
    #
    #             s_lat, s_lon, _ = geocode_address(school['address'], token)
    #
    #             # 3. HAVERSINE DISTANCE (Instant)
    #             h_dist = haversine(u_lat, u_lon, s_lat, s_lon)
    #
    #             # 4. TRANSPORT DISTANCE (API call)
    #             # We only call this for schools that passed the regional filter!
    #             t_dist, t_time = get_transport_data(token, (u_lat, u_lon), (s_lat, s_lon))
    #
    #             # Test from SMU (1.296, 103.850) to Orchard (1.304, 103.832)
    #             #dist, data_time = get_transport_data(token, (1.296, 103.850), (1.304, 103.832))
    #             #print(f"Distance: {dist}m, Time: {data_time}s")
    #
    #             results.append({
    #                 "User": user['name'],
    #                 "School": school['name'],
    #                 "Region": u_area,
    #                 "Straight_Dist_km": round(h_dist, 2),
    #                 "Transport_Dist_m": t_dist,
    #                 "Travel_Time_sec": t_time
    #             })
    #             time.sleep(0.1)  # Small delay to be nice to the API
    #         else:
    #             print(f"❌ {school['name']} is too far (different region).")
    #
    #         # 3. HAVERSINE DISTANCE (Instant)
    #         #h_dist = haversine(u_lat, u_lon, s_lat, s_lon)
    #
    #         # 4. TRANSPORT DISTANCE (API call)
    #         # We only call this for schools that passed the regional filter!
    #         #t_dist, t_time = get_transport_data(token, (u_lat, u_lon), (s_lat, s_lon))
    #
    #         # results.append({
    #         #     "User": user['name'],
    #         #     "School": school['name'],
    #         #     "Region": u_area,
    #         #     "Straight_Dist_km": round(h_dist, 2),
    #         #     "Transport_Dist_m": t_dist,
    #         #     "Travel_Time_sec": t_time
    #         # })
    #         # time.sleep(0.1)  # Small delay to be nice to the API
    #
    # # 5. Output to Excel
    # if not results:
    #     print("⚠️ No matches found. Excel will be empty.")
    # else:
    #     output_df = pd.DataFrame(results)
    #     output_df.to_excel("data/matching_results.xlsx", index=False)
    #     print(f"Successfully saved {len(results)} rows to Excel.")


if __name__ == "__main__":
    main()