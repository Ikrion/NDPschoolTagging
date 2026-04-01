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
#geoJsonurl = f"https://api-open.data.gov.sg/v1/public/api/datasets/{dataset_id}/poll-download"
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


def check_geo_neighbour():
    # 1. Check if the final neighbor map already exists
    if os.path.exists(ProcessedGeoJSON_FILE):
        with open(ProcessedGeoJSON_FILE, "r") as f:
            return json.load(f)

    # 2. Check if the raw GeoJSON exists; if not, download it
    if not os.path.exists(geoJSON_FILE):
        success = geoJSONProcessing.download_geojson_with_polling()
        if not success:
            return None  # Stop if download failed

    # 3. Generate the neighbor map using your GeoPandas processing script
    print("⚙️ Generating neighbor map (this may take a moment)...")
    try:
        geoJSONProcessing.generate_neighbor_map(geoJSON_FILE)
        with open(ProcessedGeoJSON_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        # If it fails here, the file is likely a 'bad' download (XML error)
        print(f"❌ Format Error: {e}")
        print("🗑️ Removing invalid file. Please try running again.")
        if os.path.exists(geoJSON_FILE):
            os.remove(geoJSON_FILE)
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
                    #print(f"🗺️ Area identified as: {area_name}")
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

#Todo: work on making some QOL improvement
#TOdo: Only need to type the name without knowing their school assignment to swap a user
def targeted_swap(targets, school_assignments, unassigned_users, school_info, token, api_cache, priority_col):
    # --- FLEXIBILITY CHECK ---
    # If the user passed a single dictionary, turn it into a list of one item
    if isinstance(targets, dict):
        targets = [targets]

    print(f"\n🔍 Processing {len(targets)} manual swap request(s)...")

    # Keep track of who was successfully swapped
    swap_results = []

    for target in targets:
        target_username = target['name']

        #If you don't know the user assigned school, it will help to search
        if target['school'] == "":
            #Todo: search for the school that the target user belong to
            target_school = target['school']
        else:
            target_school = target['school']

        print(f"\n   ➔ Seeking replacement for {target_username} at {target_school}...")

        # 1. Verify the target user is actually at this school
        assigned_list = school_assignments.get(target_school, [])
        target_record = None
        for vol in assigned_list:
            if vol['user_data']['name'] == target_username:
                target_record = vol
                break

        if not target_record:
            print(f"    ⚠️ Error: {target_username} is not currently assigned to {target_school}.")
            swap_results.append((target_username, False))
            continue

        school_coords = school_info[target_school]['coords']
        swap_successful = False

        # 2. Exhaustive Search: Priority 2 first, then Priority 3
        for priority_level in [2, 3]:
            # Filter candidates by the current priority level
            candidates = [u for u in unassigned_users if int(u[priority_col]) == priority_level]

            if not candidates:
                continue

            print(f"      Scanning {len(candidates)} Level {priority_level} candidates...")

            best_candidate = None
            best_time = float('inf')
            best_dist = 0

            for candidate in candidates:
                c_name = candidate['name']

                # geocode_address must be available in your global script
                c_lat, c_lon, _ = geocode_address(candidate['address'], token)

                # API Call / Cache Check
                if (c_name, target_school) in api_cache:
                    dist_m, time_sec = api_cache[(c_name, target_school)]
                else:
                    dist_m, time_sec = get_transport_data(token, (c_lat, c_lon), school_coords)
                    api_cache[(c_name, target_school)] = (dist_m, time_sec)
                    time.sleep(0.1)

                    # The Exhaustive Filter: Must be <= 1 hour, and FASTEST so far
                if time_sec is not None and time_sec <= 3600:
                    if time_sec < best_time:
                        best_time = time_sec
                        best_dist = dist_m
                        best_candidate = candidate

            # 3. Execute the Swap if a candidate was found
            if best_candidate:
                mins, secs = divmod(best_time, 60)
                print(f"      ✅ SUCCESS: Replaced with {best_candidate['name']} ({int(mins)}m {int(secs)}s commute).")

                # Remove original target from school
                school_assignments[target_school].remove(target_record)

                # Add new candidate to school
                school_assignments[target_school].append({
                    'user_data': best_candidate,
                    'time_sec': best_time,
                    'dist': best_dist
                })

                # Move candidate out of unassigned pool
                unassigned_users.remove(best_candidate)

                # Move original target into unassigned pool
                target_record['user_data']['Reason'] = "Swapped out via Phase 4"
                unassigned_users.append(target_record['user_data'])

                swap_successful = True
                swap_results.append((target_username, True))
                break  # Exit the priority tier loop since we found a replacement

        # 4. If neither Priority 2 nor 3 yielded a result
        if not swap_successful:
            print(f"      ❌ FAILED: No Priority 2 or 3 users are within 1 hour of {target_school}.")
            swap_results.append((target_username, False))

    return swap_results


def process_with_priority(user_excel_path, school_excel_path, token, neighbors_path):
    # --- 1. PREPARE SCHOOL DATA ---
    school_df = pd.read_excel(school_excel_path)
    school_assignments = {row['school_name']: [] for _, row in school_df.iterrows()}
    school_info = {}

    for _, row in school_df.iterrows():
        s_name = row['school_name']
        school_info[s_name] = {
            "area": str(row.get('Planning Area', 'UNKNOWN')).strip().upper(),
            "coords": (row['Latitude'], row['Longitude']),
            "max": int(row.get('max volunteer', 5))
        }

    # Group schools by area for fast lookup
    school_buckets = {}
    for s_name, info in school_info.items():
        area = info['area']
        if area not in school_buckets: school_buckets[area] = []
        school_buckets[area].append({"name": s_name, "coords": info['coords']})

    # --- 2. PREPARE USER DATA & PRIORITY QUEUE & neighbor data ---
    user_df = pd.read_excel(user_excel_path)
    priority_col = user_df.columns[0]

    # Sort by Priority Level (1 is highest) then convert to deque
    user_df = user_df.sort_values(by=priority_col, ascending=True)
    user_queue = deque(user_df.to_dict('records'))

    unassigned_users = []
    api_cache = {}

    try:
        with open(neighbors_path, 'r') as f:
            area_neighbors = json.load(f)
        print(f"🗺️ Neighbor map loaded from: {neighbors_path}")
    except FileNotFoundError:
        print(f"⚠️ Error: {neighbors_path} not found. Fallback logic will be disabled.")
        area_neighbors = {}
    except json.JSONDecodeError:
        print(f"⚠️ Error: {neighbors_path} is corrupted. Fallback logic will be disabled.")
        area_neighbors = {}

    # --- 3. THE ASSIGNMENT HELPER FUNCTION ---
    def try_assign_to_areas(areas_to_check, current_user, u_lat, u_lon):
        u_name = current_user['name']
        u_priority = int(current_user[priority_col])
        options = []

        for area in areas_to_check:
            schools_in_area = school_buckets.get(area.upper(), [])
            for school in schools_in_area:
                s_name = school['name']

                # Check Cache to save API hits
                if (u_name, s_name) in api_cache:
                    dist_m, time_sec = api_cache[(u_name, s_name)]
                else:
                    # Logic assumes get_transport_data is defined globally
                    dist_m, time_sec = get_transport_data(token, (u_lat, u_lon), school['coords'])
                    api_cache[(u_name, s_name)] = (dist_m, time_sec)
                    time.sleep(0.1)

                # Filter: Travel time must be <= 1 hour (3600 seconds)
                if time_sec is not None and time_sec <= 3600:
                    options.append({'name': s_name, 'time': time_sec, 'dist': dist_m})

        # Sort options: Nearest first
        options.sort(key=lambda x: x['time'])

        for opt in options:
            s_name = opt['name']
            u_time = opt['time']
            current_vols = school_assignments[s_name]
            max_cap = school_info[s_name]['max']

            # Case A: Slot available
            if len(current_vols) < max_cap:
                school_assignments[s_name].append({'user_data': current_user, 'time_sec': u_time, 'dist': opt['dist']})
                print(f"{current_user['name']} is assigned to {s_name} in {school_info[s_name]['area']}.")
                return True

            # Case B: School full - Priority Bumping Logic
            else:
                print(f"{s_name} school is full, trying to swap user.")
                current_vols.sort(key=lambda x: x['time_sec'], reverse=True)
                slowest = current_vols[0]
                slowest_priority = int(slowest['user_data'][priority_col])

                can_bump = False
                if u_priority < slowest_priority:
                    can_bump = True  # Higher priority always bumps lower
                elif u_priority == slowest_priority and (slowest['time_sec'] - u_time) > 600:
                    can_bump = True  # Same priority bumps if 10 mins faster

                if can_bump:
                    school_assignments[s_name].pop(0)
                    school_assignments[s_name].append(
                        {'user_data': current_user, 'time_sec': u_time, 'dist': opt['dist']})
                    user_queue.append(slowest['user_data'])  # Re-queue the bumped person
                    print(f"{current_user['name']} is swap with {slowest['user_data']['name']} in school {s_name}.")
                    return True
        return False

    # --- 4. MAIN PROCESSING LOOP ---
    print(f"🚀 Starting processing for {len(user_queue)} users...")
    while user_queue:
        current_user = user_queue.popleft()
        u_name = current_user['name']
        u_priority = int(current_user[priority_col])

        if u_priority == 4:
            unassigned_users.append(current_user)
            continue

        # Logic assumes geocode_address is defined globally
        u_lat, u_lon, u_area = geocode_address(current_user['address'], token)
        u_area = u_area.strip().upper()

        # Attempt Phase 1: Own Area
        print(f"\nTrying to assign {current_user['name']} to {u_area}")
        assigned = try_assign_to_areas([u_area], current_user, u_lat, u_lon)

        # Attempt Phase 2: Neighboring Areas
        if not assigned:
            print(f"{current_user['name']} is instead getting assign to a neighbor area near {u_area}.")
            neighbors = area_neighbors.get(u_area, [])
            assigned = try_assign_to_areas(neighbors, current_user, u_lat, u_lon)

        # Phase 3: Global Search (Only for Level 1 & 2)
        if not assigned and u_priority in [1, 2]:
            print(f"🌍 Priority {u_priority} Global Search for {current_user['name']}...")
            # Get all areas except the ones we already checked
            already_checked = set([u_area] + area_neighbors.get(u_area, []))
            all_other_areas = [a for a in school_buckets.keys() if a not in already_checked]
            assigned = try_assign_to_areas(all_other_areas, current_user, u_lat, u_lon)

        if not assigned:
            print(f"{current_user['name']} is not assigned as no school with space is available near {u_area}.")
            unassigned_users.append(current_user)

    # --- 5. DATA PREPARATION FOR EXPORT ---
    final_rows = []
    max_cols_found = 0

    for s_name, volunteers in school_assignments.items():
        volunteers.sort(key=lambda x: x['time_sec'])
        row_data = [s_name, school_info[s_name]['max'], school_info[s_name]['area']]

        for vol in volunteers:
            mins, secs = divmod(vol['time_sec'], 60)
            row_data.extend([
                vol['user_data']['name'],
                f"{int(mins)}m {int(secs)}s",
                round(vol['time_sec'] / 60, 2),
                vol['dist']
            ])

        if len(row_data) > max_cols_found: max_cols_found = len(row_data)
        final_rows.append(row_data)

    for row in final_rows:
        while len(row) < max_cols_found: row.append("")

    headers = ["School", "Max Volunteers", "Area"]
    num_users_in_header = (max_cols_found - 3) // 4
    for i in range(1, num_users_in_header + 1):
        headers.extend([f"User {i}", "Travel Time", "Minutes", "Distance (m)"])

    # --- 6. CALCULATE SUMMARY STATISTICS ---
    filled_schools = sum(1 for s_name, vols in school_assignments.items() if len(vols) >= school_info[s_name]['max'])
    unfilled_schools = len(school_assignments) - filled_schools

    assigned_users_list = [v['user_data'] for vols in school_assignments.values() for v in vols]
    total_assigned = len(assigned_users_list)
    total_unassigned = len(unassigned_users)

    def count_priorities(u_list, p_level):
        return sum(1 for u in u_list if int(u[priority_col]) == p_level)

    summary_data = {
        "Metric": ["Total Users Allocated", "Total Users Unassigned",
                   "Level 1: Assigned vs Unassigned", "Level 2: Assigned vs Unassigned",
                   "Level 3: Assigned vs Unassigned", "Level 4: (Not Assigned by Policy)",
                   "Schools Fully Filled", "Schools with Remaining Vacancies"],
        "Value": [total_assigned, total_unassigned,
                  f"{count_priorities(assigned_users_list, 1)} / {count_priorities(unassigned_users, 1)}",
                  f"{count_priorities(assigned_users_list, 2)} / {count_priorities(unassigned_users, 2)}",
                  f"{count_priorities(assigned_users_list, 3)} / {count_priorities(unassigned_users, 3)}",
                  count_priorities(unassigned_users, 4),
                  filled_schools, unfilled_schools]
    }
    df_summary = pd.DataFrame(summary_data)

    # --- 7. FINAL EXPORT TO THREE SHEETS ---
    try:
        df_assignments = pd.DataFrame(final_rows, columns=headers)
        df_unassigned = pd.DataFrame(unassigned_users)[
            [priority_col, 'name', 'address']] if unassigned_users else pd.DataFrame(
            columns=[priority_col, 'name', 'address'])
        df_unassigned.columns = ['Priority', 'Name', 'Address']

        output_path = "data/final_modeling_assignments_with_priority.xlsx"
        with pd.ExcelWriter(output_path, engine='xlsxwriter') as writer:
            df_assignments.to_excel(writer, sheet_name='Assignments', index=False)
            df_unassigned.to_excel(writer, sheet_name='Unassigned Users', index=False)
            df_summary.to_excel(writer, sheet_name='Summary Statistics', index=False)

            # Get workbook and worksheet objects
            workbook = writer.book
            worksheet_assign = writer.sheets['Assignments']

            # --- NEW: Define the Color Format ---
            yellow_format = workbook.add_format({'bg_color': '#FFFFE0'})
            grey_format = workbook.add_format({'bg_color': '#8A8A8A'})

            # --- NEW: Apply Conditional Formatting to Assignments ---
            # We check if the "User 1" column (Column D, index 3) is empty
            # OR better yet, check if the VERY LAST user column is empty.
            num_rows = len(final_rows)
            num_cols = len(headers)

            # --- APPLY ROW-LEVEL HIGHLIGHTING (Unfilled Schools) ---
            # Logic: If the last column of the row is empty (""), highlight row
            # Excel formula: =$D2="" (Checks if the first user slot is empty)
            # Or use a more robust check: compare count of users vs Max Volunteers
            for row_num in range(1, num_rows + 1):
                # Get the actual number of volunteers in this row from our processing
                vols_in_row = len(school_assignments[final_rows[row_num - 1][0]])
                max_cap = final_rows[row_num - 1][1]

                if vols_in_row < max_cap:
                    # Apply yellow to the entire row (Column A to the end)
                    worksheet_assign.set_row(row_num, None, yellow_format)

            # --- APPLY CELL-LEVEL HIGHLIGHTING (Travel Time >= 30m) ---
            # We iterate through the school_assignments to find specific cell coordinates
            for r_idx, (s_name, volunteers) in enumerate(school_assignments.items()):
                # Volunteers are sorted by time in the final_rows export
                volunteers.sort(key=lambda x: x['time_sec'])

                for v_idx, vol in enumerate(volunteers):
                    # Calculation for Travel Time column index:
                    # School(0), Max(1), Area(2) ...
                    # User1(3), TIME(4), Mins(5), Dist(6)
                    # User2(7), TIME(8)...
                    # Formula: 4 + (v_idx * 4)
                    time_col_idx = 4 + (v_idx * 4)

                    if vol['time_sec'] >= 1800:  # 30 mins * 60 seconds
                        mins, secs = divmod(vol['time_sec'], 60)
                        time_str = f"{int(mins)}m {int(secs)}s"

                        # Overwrite the specific cell with the grey format
                        worksheet_assign.write(r_idx + 1, time_col_idx, time_str, grey_format)

            # Formatting for Summary Sheet (as before)
            summary_sheet = writer.sheets['Summary Statistics']
            summary_sheet.set_column('A:A', 35)
            summary_sheet.set_column('B:B', 20)

        print(f"🎉 Success! Processed {len(final_rows)} schools and {len(user_df.to_dict('records'))} users.")
        print(f"📊 Summary: {total_assigned} assigned, {total_unassigned} unassigned.")
        print(f"🏫 Schools: {filled_schools} full, {unfilled_schools} with vacancies.")
        print(f"\n✅ All assignments finalized and saved to: {output_path}")
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

    process_with_priority(user_file_path, school_file_path, token, ProcessedGeoJSON_FILE)


if __name__ == "__main__":
    main()