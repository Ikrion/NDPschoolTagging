import json

import requests
import pandas as pd
import math
import time
import os
from datetime import datetime
from collections import deque

import geoJSONProcessing

# --- CONFIGURATION ---
EMAIL = "zhanghaien100@gmail.com"
PASSWORD = "Blk-457-13@haien"
TOKEN_FILE = "token_cache.txt"
dataset_id = "d_2cc750190544007400b2cfd5d7f53209"
#geoJsonurl = f"https://api-open.data.gov.sg/v1/public/api/datasets/{dataset_id}/poll-download"
local_filename = 'data/MasterPlan2025PlanningAreaBoundaryNoSea.geojson'
geoJSON_FILE = "data/MasterPlan2025PlanningAreaBoundaryNoSea.geojson"
ProcessedGeoJSON_FILE = "data/area_neighbors.json"

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


def download_geojson_with_polling():

    #print(f"📡 Requesting download for dataset: {dataset_id}")

    initiate_url = f"https://api-open.data.gov.sg/v1/public/api/datasets/{dataset_id}/initiate-download"
    poll_url = f"https://api-open.data.gov.sg/v1/public/api/datasets/{dataset_id}/poll-download"
    #local_filename = 'data/MasterPlan2025PlanningAreaBoundaryNoSea.geojson'

    os.makedirs('data', exist_ok=True)

    try:
        # --- STEP 1: INITIATE ---
        print(f"🚀 Initiating download for {dataset_id}...")
        init_res = requests.get(initiate_url)  # Note: Some v1 endpoints require POST to initiate
        init_data = init_res.json()

        print (f"Init code: {init_data.get('code')}")
        if init_data.get('code') != 0:
            print(f"❌ Initialization failed: {init_data.get('errorMsg')}")
            return False

        time.sleep(10)  # Give it 10 seconds between API request
        # --- STEP 2: POLL ---
        print("⏳ Polling for file readiness...")
        for attempt in range(12):  # Try for 60 seconds (12 * 5s)
            poll_res = requests.get(poll_url)
            poll_data = poll_res.json()

            # Debug: Uncomment the line below if you get more errors to see the raw response
            print(f"DEBUG: {poll_data}")
            print (f"Poll Code: {poll_data.get('code')}")
            if poll_data.get('code') != 0:
                # Only print error if code is NOT 1
                print(f"❌ API Error: {poll_data.get('errorMsg')}")
                return False

            # The important part: Check the nested 'data' object
            data_block = poll_data.get('data', {})
            #status = data_block.get('status')

            download_link = data_block.get('url')
            if not download_link:
                print("❌ Status COMPLETED but no URL found in response.")
                return False

            print("✅ File ready! Downloading now...")
            file_response = requests.get(download_link)
            if file_response.status_code == 200:
                with open(local_filename, 'wb') as f:
                    f.write(file_response.content)
                print(f"📂 Saved to {local_filename}")
                return True

            # if status == 'COMPLETED':
            #     download_link = data_block.get('url')
            #     if not download_link:
            #         print("❌ Status COMPLETED but no URL found in response.")
            #         return False
            #
            #     print("✅ File ready! Downloading now...")
            #     file_response = requests.get(download_link)
            #     if file_response.status_code == 200:
            #         with open(local_filename, 'wb') as f:
            #             f.write(file_response.content)
            #         print(f"📂 Saved to {local_filename}")
            #         return True
            #
            # elif status == 'FAILED':
            #     print("❌ Server failed to generate the dataset.")
            #     return False
            #
            # else:
            #     # If status is PENDING or still preparing
            #     print(f"   ...Status: {status} (Attempt {attempt + 1})")
            #     time.sleep(7)  # Give it 7 seconds between checks

    except Exception as e:
        print(f"❌ Logic error: {e}")

    return False


def check_geo_neighbour():
    # 1. Check if the final neighbor map already exists
    if os.path.exists(ProcessedGeoJSON_FILE):
        with open(ProcessedGeoJSON_FILE, "r") as f:
            return json.load(f)

    # 2. Check if the raw GeoJSON exists; if not, download it
    if not os.path.exists(local_filename):
        success = download_geojson_with_polling()
        if not success:
            return None  # Stop if download failed

    # 3. Generate the neighbor map using your GeoPandas processing script
    print("⚙️ Generating neighbor map (this may take a moment)...")
    try:
        geoJSONProcessing.generate_neighbor_map(local_filename)
        with open(ProcessedGeoJSON_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        # If it fails here, the file is likely a 'bad' download (XML error)
        print(f"❌ Format Error: {e}")
        print("🗑️ Removing invalid file. Please try running again.")
        if os.path.exists(local_filename):
            os.remove(local_filename)
        return None

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
            #area_params = {"lat": lat, "log": lon}  # Note: OneMap uses 'log' for longitude here

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
    # Track current assignments: { 'School Name': [ {user_dict}, ... ] }
    school_assignments = {row['school_name']: [] for _, row in school_df.iterrows()}
    # Store School Info (Area, Coords, Max Volunteers)
    school_info = {}

    max_possible_vols = 0  # Track the largest max_volunteer for header creation

    for _, row in school_df.iterrows():
        cap = int(row.get('max volunteer', 5))
        if cap > max_possible_vols: max_possible_vols = cap

        school_info[row['school_name']] = {
            "area": str(row.get('Planning Area', 'UNKNOWN')).strip().upper(),
            "coords": (row['Latitude'], row['Longitude']),
            "max": cap
        }

    # Pre-process schools into regional buckets for fast lookup
    school_buckets = {}
    for s_name, info in school_info.items():
        area = info['area']
        if area not in school_buckets:
            school_buckets[area] = []
        school_buckets[area].append({"name": s_name, "coords": info['coords']})

    # --- 2. PREPARE USER QUEUE & CACHE ---
    user_df = pd.read_excel(user_excel_path)
    # Convert users to a list of dictionaries and put in a queue
    user_queue = deque(user_df.to_dict('records'))

    # Cache to store API results: { (user_name, school_name): (dist, time_sec) }
    # This prevents re-calling the API if a user is bumped and re-processed
    api_cache = {}

    # Get the planning area neighbour
    # Used for nearby neighbour planning area searches
    geoneighbour_dict = check_geo_neighbour()

    print(f"🚀 Starting Assignment Logic for {len(user_queue)} users...")

    while user_queue:
        current_user = user_queue.popleft()
        u_name = current_user['name']

        # Geocode the user once
        u_lat, u_lon, u_area = geocode_address(current_user['address'], token)
        u_area = u_area.strip().upper()

        # We define a helper block for the matching logic so we don't write it twice
        def try_assign_to_areas(areas_to_check):
            options = []
            for area in areas_to_check:
                schools_in_area = school_buckets.get(area, [])
                for school in schools_in_area:
                    s_name = school['name']

                    # API Cache saves us from massive API limits during fallback!
                    if (u_name, s_name) in api_cache:
                        dist_m, time_sec = api_cache[(u_name, s_name)]
                    else:
                        dist_m, time_sec = get_transport_data(token, (u_lat, u_lon), school['coords'])
                        api_cache[(u_name, s_name)] = (dist_m, time_sec)
                        time.sleep(0.2)

                    if time_sec is not None:
                        options.append({'name': s_name, 'time': time_sec, 'dist': dist_m, 'area': area})

            # Sort all gathered options from nearest to furthest
            options.sort(key=lambda x: x['time'])

            # Try to assign (Space Available OR 10-Min Swap)
            for opt in options:
                s_name = opt['name']
                u_time = opt['time']
                current_vols = school_assignments[s_name]
                max_cap = school_info[s_name]['max']

                if len(current_vols) < max_cap:
                    school_assignments[s_name].append(
                        {'user_data': current_user, 'time_sec': u_time, 'dist': opt['dist']})
                    return True  # Success!
                else:
                    current_vols.sort(key=lambda x: x['time_sec'], reverse=True)
                    slowest = current_vols[0]
                    if (slowest['time_sec'] - u_time) > 600:
                        school_assignments[s_name].pop(0)
                        school_assignments[s_name].append(
                            {'user_data': current_user, 'time_sec': u_time, 'dist': opt['dist']})
                        user_queue.append(slowest['user_data'])
                        return True  # Success (via Swap)!

            return False  # Failed to assign in these areas

        # --- PHASE 1: Try Primary Area ---
        assigned = try_assign_to_areas([u_area])

        # --- PHASE 2: Try Neighboring Areas ---
        if not assigned:
            neighbors = geoneighbour_dict.get(u_area, [])
            if neighbors:
                print(f"⚠️ {u_name} couldn't match in {u_area}. Expanding search to neighbors: {neighbors}")
                assigned = try_assign_to_areas(neighbors)

        # --- PHASE 3: Total Failure ---
        if not assigned:
            print(f"❌ {u_name} completely failed to match in {u_area} AND its neighbors.")

        # --- 3. FORMAT DATA FOR HORIZONTAL EXPORT ---
        final_rows = []
        max_cols_found = 0

        for s_name, volunteers in school_assignments.items():
            # Sort volunteers for this specific school row (fastest first)
            volunteers.sort(key=lambda x: x['time_sec'])

            # Start row with base school info
            row_data = [s_name, school_info[s_name]['max'], school_info[s_name]['area']]

            # Add User 1, Time, Mins, Dist, User 2, Time, Mins, Dist...
            for vol in volunteers:
                mins, secs = divmod(vol['time_sec'], 60)
                row_data.extend([
                    vol['user_data']['name'],
                    f"{int(mins)}m {int(secs)}s",
                    round(vol['time_sec'] / 60, 2),
                    vol['dist']
                ])

            # Pad the row with empty values if the school isn't full
            slots_left = school_info[s_name]['max'] - len(volunteers)
            if slots_left > 0:
                row_data.extend([""] * (slots_left * 4))

            final_rows.append(row_data)

            # Track the longest row to create headers later
            if len(row_data) > max_cols_found:
                max_cols_found = len(row_data)

        # --- 4. DYNAMIC PADDING & HEADERS ---
        # Ensure every row is the same length as the longest row
        for row in final_rows:
            while len(row) < max_cols_found:
                row.append("")

        # Build headers based on the actual number of columns (2 + N*4)
        headers = ["School", "Max Volunteers", "Area"]
        num_users_in_header = (max_cols_found - 2) // 4

        for i in range(1, num_users_in_header + 1):
            headers.extend([f"User {i}", "Travel Time", "Minutes", "Distance (m)"])

    # --- 5. EXPORT ---
    try:
        output_df = pd.DataFrame(final_rows, columns=headers)
        output_df.to_excel("data/final_modeling_assignments.xlsx", index=False)
        print(f"🎉 Success! Processed {len(final_rows)} schools and {len(user_df.to_dict('records'))} users.")
        print("🎉 All assignments finalized and saved.")
    except Exception as e:
        print(f"❌ Export failed: {e}")

# --- MAIN LOGIC ---

def main():
    token = get_valid_token()


    # 1. Load your data (Assuming Excel for this example)
    # user_df = pd.read_excel("data/users.xlsx")
    # school_df = pd.read_excel("data/schools.xlsx")
    user_file_path = "data/users.xlsx"
    school_file_path = "data/schools.xlsx"
    
    #geoneighbour_dict = check_geo_neighbour()

    process_user_with_swaps(user_file_path, school_file_path, token)


if __name__ == "__main__":
    main()