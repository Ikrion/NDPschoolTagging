import json
import requests
import pandas as pd
import math
import time
import os
from datetime import datetime
from collections import deque
import geoJSONProcessing
import onemapApiHelper
from jsondatasystem import JSONStorage
from  exceldatasystem import ExcelStorage
from dataStorageSystem import DataManager

# Place this near your imports/configuration
session = requests.Session()

# --- CONFIGURATION ---
EMAIL = "zhanghaien100@gmail.com"
PASSWORD = "Blk-457-13@haien"
TOKEN_FILE = "token_cache.txt"
#geoJsonurl = f"https://api-open.data.gov.sg/v1/public/api/datasets/{dataset_id}/poll-download"
geoJSON_FILE = "data/MasterPlan2025PlanningAreaBoundaryNoSea.geojson"
ProcessedGeoJSON_FILE = "data/area_neighbors.json"
user_file_path = "data/users.xlsx"
school_file_path = "data/schools.xlsx"

# --- HELPER FUNCTIONS ---
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


def haversine(lat1, lon1, lat2, lon2):
    """Calculates straight-line distance in km"""
    r = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


def create_allocation_formatter(school_assignments, school_info, final_rows):
    """
    A factory that creates a custom formatting function for our specific school data.
    """

    def format_excel(workbook, worksheet, sheet_name):
        # We only want to apply these intense rules to the Assignments sheet
        if sheet_name != 'Assignments':
            # For other sheets, maybe just make the headers bold
            header_fmt = workbook.add_format({'bold': True, 'bg_color': '#F2F2F2', 'border': 1})
            worksheet.set_row(0, None, header_fmt)
            return

        # --- DEFINE FORMATS ---
        yellow_row = workbook.add_format({'bg_color': '#FFFFE0'})
        grey_cell = workbook.add_format({'bg_color': '#D3D3D3'})
        header_fmt = workbook.add_format({'bold': True, 'bg_color': '#F2F2F2'})

        # Format Header
        worksheet.set_row(0, None, header_fmt)

        # --- APPLY HIGHLIGHTS ---
        for r_idx, row in enumerate(final_rows):
            s_name = row[0]  # School name is the first item in the row

            # Note: We safely get the list, defaulting to empty if not found
            volunteers = school_assignments.get(s_name, [])
            max_cap = school_info[s_name]['max']

            # 1. Row-Level Highlight: Unfilled Schools (Light Yellow)
            if len(volunteers) < max_cap:
                worksheet.set_row(r_idx + 1, None, yellow_row)

            # 2. Cell-Level Highlight: Travel Time >= 30 mins (Grey)
            # Ensure the volunteers match the sorted order of the export
            volunteers_sorted = sorted(volunteers, key=lambda x: x['time_sec'])

            for v_idx, vol in enumerate(volunteers_sorted):
                # Calculate the exact column index for "Travel Time"
                # School(0), Max(1), Area(2) | User1(3), TIME(4)...
                time_col_idx = 4 + (v_idx * 4)

                if vol['time_sec'] >= 1800:  # 30 mins
                    mins, secs = divmod(vol['time_sec'], 60)
                    time_str = f"{int(mins)}m {int(secs)}s"

                    # Paint over that specific cell
                    worksheet.write(r_idx + 1, time_col_idx, time_str, grey_cell)

    # Return the inner function so ExcelStorage can use it
    return format_excel


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
        response = session.get(url, params=params, headers=headers)
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
        _, _, fresh_area = onemapApiHelper.geocode_address(row['address'], token)
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
    """
    To process the Excel file containing the school data and save the processed data as a JSON file
    :param school_excel_path: Path to the Excel file containing the school data
    :param token: API token to call the onemap API
    :return: Dictionary containing the school in each area of singapore
    """
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
        lat, lon, area = onemapApiHelper.geocode_address(s_row['address'], token)

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


def targeted_swap(targets, storage_path, token):
    """
    Reworked to load from JSON, find users, swap them,
    and retire original users to Priority 4.
    """
    # Initialize OOP Storage
    storage = JSONStorage(storage_path)
    manager = DataManager(storage)

    # 1. LOAD CURRENT STATE
    full_data = manager.get_all()  # This retrieves the master dict
    if not full_data:
        print("❌ Error: Could not load data from storage.")
        return

    assignments = full_data.get("assignments", {})
    unassigned = full_data.get("unassigned_users", [])

    # --- Retrieving school coords ---
    school_df = pd.read_excel(school_file_path)
    school_assignments = {row['school_name']: [] for _, row in school_df.iterrows()}
    school_infos = {}

    for _, row in school_df.iterrows():
        s_name = row['school_name']
        school_infos[s_name] = {
            "area": str(row.get('Planning Area', 'UNKNOWN')).strip().upper(),
            "coords": (row['Latitude'], row['Longitude']),
            "max": int(row.get('max volunteer', 5))
        }

    # --- FLEXIBILITY CHECK ---
    # If the user passed a single dictionary, turn it into a list of one item
    # if isinstance(targets, dict):
    #     targets = [targets]
    #
    # print(f"\n🔍 Processing {len(targets)} manual swap request(s)...")

    # Keep track of who was successfully swapped
    swap_results = []

    for target in targets:

        target_school = None
        target_user_key = None  # e.g., "User 1"

        # 2. FIND TARGET IN ASSIGNMENTS
        for school_name, school_info in assignments.items():
            # Iterate through keys like 'User 1', 'User 2'
            for key, value in school_info.items():
                if isinstance(value, dict) and value.get("Name") == target:
                    target_school = school_name
                    target_user_key = key
                    break
            if target_school: break

        if not target_school:
            print(f"⚠️ '{target}' not found in active assignments.")
            continue

        print(f"Found {target} at {target_school}. Searching for replacement...")

        # 3. EXHAUSTIVE SEARCH FOR REPLACEMENT (Priority 2 or 3)
        # Note: We need school coordinates. In a real DB-first app,
        # these should be stored in a separate 'schools' table/json.
        # For now, I'm assuming you have a way to get the school's lat/lon.
        #school_coords = get_school_coords(target_school)
        school_coords = school_infos[target_school]["coords"]

        best_replacement = None
        best_time = float('inf')
        best_dist = 0

        for p_level in [2, 3]:
            candidates = [u for u in unassigned if int(u.get('Priority', 0)) == p_level]

            for cand in candidates:
                # Get transport data (API/Cache)
                c_lat, c_lon, _ = onemapApiHelper.geocode_address(cand['Address'], token)
                dist_m, time_sec = get_transport_data(token, (c_lat, c_lon), school_coords)

                if time_sec and time_sec <= 3600 and time_sec < best_time and dist_m < best_dist:
                    best_time = time_sec
                    best_dist = dist_m
                    best_replacement = cand
                    print(f"Current replacement: {best_replacement['Name']}")

        # 4. EXECUTE SWAP AND RETIRE
        if best_replacement:
            mins, secs = divmod(best_time, 60)

            # A. Prepare the original user for retirement (Priority 4)
            # We recreate their record to match the 'unassigned' format
            retired_user = {
                "Priority": 4,
                "Name": target,
                "Address": "Retrieved from original data...",  # Ideally keep original address here
                "Reason": "Manually swapped and retired to Priority 4"
            }

            # B. Update the School Assignment
            assignments[target_school][target_user_key] = {
                "Name": best_replacement['Name'],
                "Travel Time": f"{int(mins)}m {int(secs)}s",
                "Total Minutes": round(best_time / 60, 2),
                "Distance (meters)": best_dist
            }

            # C. Update Unassigned List
            unassigned.remove(best_replacement)
            unassigned.append(retired_user)

            print(f"✅ Swapped {target} with {best_replacement['Name']}.")
        else:
            print(f"❌ No suitable replacement found for {target}.")

    # 5. SAVE BACK TO JSON once all the targets are swap if any
    full_data["assignments"] = assignments
    full_data["unassigned_users"] = unassigned
    manager.save_all(full_data)
    print("\n💾 Database updated successfully.")


def process_with_priority(user_excel_path, school_excel_path, token, neighbors_path):
    # --- Initialize Timing Dictionary ---
    timings = {}
    total_start = time.perf_counter()
    # --- 1. PREPARE SCHOOL DATA ---
    stage1_start = time.perf_counter() # timing start
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

    timings["1. Load School Data Timing"] = time.perf_counter() - stage1_start #Timing end

    # --- 2. PREPARE USER DATA & PRIORITY QUEUE & neighbor data ---
    stage2_start = time.perf_counter() # timing start
    user_df = pd.read_excel(user_excel_path)
    priority_col = user_df.columns[0]

    # Sort by Priority Level (1 is highest) then convert to deque
    user_df = user_df.sort_values(by=priority_col, ascending=True)
    user_queue = deque(user_df.to_dict('records'))

    #cache to save on API calls
    unassigned_users = []
    api_cache = {}
    user_geo_cache = {}

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

    timings["2. Load User Data & Neighbors Timing"] = time.perf_counter() - stage2_start #timing end
    # --- 3. THE ASSIGNMENT HELPER FUNCTION (OPTIMIZED) ---
    def try_assign_to_areas(areas_to_check, current_user, u_lat, u_lon):
        u_name = current_user['name']
        u_priority = int(current_user[priority_col])

        # Step A: Gather all potential schools and calculate straight-line distance
        potential_schools = []
        for area in areas_to_check:
            for school in school_buckets.get(area.upper(), []):
                # This takes 0.0001 seconds (No API call)
                dist_km = haversine(u_lat, u_lon, school['coords'][0], school['coords'][1])
                potential_schools.append({'school': school, 'dist_km': dist_km})

        # Step B: Sort by physical distance first
        potential_schools.sort(key=lambda x: x['dist_km'])

        # Step C: Evaluate one by one, and EXIT EARLY once assigned
        for item in potential_schools:
            school = item['school']
            s_name = school['name']

            # Check Cache to save API hits, this part is to get the distance from the user house to the school so
            # that we can calculate if the user is close to the school or other user is closer.
            # It doesn't matter if the school is full as long as the traveling time is 10 min faster, the user
            # will get assigned to the school, replacing the slowest of the user that is currently assigned
            if (u_name, s_name) in api_cache:
                dist_m, time_sec = api_cache[(u_name, s_name)]
            else:
                dist_m, time_sec = get_transport_data(token, (u_lat, u_lon), school['coords'])
                api_cache[(u_name, s_name)] = (dist_m, time_sec)
                #time.sleep(0.1)  # Respect API limits (I don't think this is need as the code that will
                # continue running will most likely help to delay the API from running too fast

            # Filter: Travel time must be <= 1 hour (3600 seconds) before checking the slot and etc
            # This first filter is helpful only when the user is checking for school that are not in their original area
            if time_sec is not None and time_sec <= 3600:
                current_vols = school_assignments[s_name]
                max_cap = school_info[s_name]['max']

                # Case A: Slot available
                if len(current_vols) < max_cap:
                    school_assignments[s_name].append(
                        {'user_data': current_user, 'time_sec': time_sec, 'dist': dist_m})
                    print(f"{u_name} is assigned to {s_name} in {school_info[s_name]['area']}.")
                    return True  # BOOM! We exit the function, saving dozens of API calls.
                # Case B: School full - Priority Bumping Logic
                else:
                    current_vols.sort(key=lambda x: x['time_sec'], reverse=True)
                    slowest = current_vols[0]
                    slowest_priority = int(slowest['user_data'][priority_col])

                    can_bump = False
                    if u_priority < slowest_priority:
                        can_bump = True
                    elif u_priority == slowest_priority and (slowest['time_sec'] - time_sec) > 600:
                        can_bump = True

                    if can_bump:
                        school_assignments[s_name].pop(0)
                        school_assignments[s_name].append(
                            {'user_data': current_user, 'time_sec': time_sec, 'dist': dist_m})
                        user_queue.append(slowest['user_data'])
                        print(f"{u_name} swapped with {slowest['user_data']['name']} in {s_name}.")
                        return True  # Exit early!
        return False

    # --- 4. MAIN PROCESSING LOOP ---
    stage4_start = time.perf_counter() #timing start
    print(f"🚀 Starting processing for {len(user_queue)} users...")
    while user_queue:
        user_start = time.perf_counter() #user timing start
        current_user = user_queue.popleft()
        u_name = current_user['name']
        u_priority = int(current_user[priority_col])

        if u_priority == 4:
            current_user['reason'] = "priority 4, doesn't get assigned."
            unassigned_users.append(current_user)
            continue

        # Logic assumes geocode_address is defined globally
        address = current_user['address']
        if address in user_geo_cache:
            u_lat, u_lon, u_area = user_geo_cache[address]
        else:
            u_lat, u_lon, u_area = onemapApiHelper.geocode_address(address, token)
            user_geo_cache[address] = (u_lat, u_lon, u_area)

        u_area = u_area.strip().upper()

        # Attempt Phase 1: Own Area
        user_phase1_start = time.perf_counter()
        print(f"\nTrying to assign {current_user['name']} to {u_area}")
        assigned = try_assign_to_areas([u_area], current_user, u_lat, u_lon)
        timings[f"{current_user['name']} phase 1 timing"] = time.perf_counter() - user_phase1_start  # timing end

        # Attempt Phase 2: Neighboring Areas
        if not assigned:
            user_phase2_start = time.perf_counter()
            print(f"{current_user['name']} is instead getting assign to a neighbor area near {u_area}.")
            neighbors = area_neighbors.get(u_area, [])
            assigned = try_assign_to_areas(neighbors, current_user, u_lat, u_lon)
            timings[f"{current_user['name']} phase 2 timing"] = time.perf_counter() - user_phase2_start  # timing end

        # Phase 3: Global Search (Only for Level 1 & 2)
        if not assigned and u_priority in [1, 2]:
            user_phase3_start = time.perf_counter()
            print(f"🌍 Priority {u_priority} Global Search for {current_user['name']}...")
            # Get all areas except the ones we already checked
            already_checked = set([u_area] + area_neighbors.get(u_area, []))
            all_other_areas = [a for a in school_buckets.keys() if a not in already_checked]
            assigned = try_assign_to_areas(all_other_areas, current_user, u_lat, u_lon)
            timings[f"{current_user['name']} phase 3 timing"] = time.perf_counter() - user_phase3_start  # timing end

        if not assigned:
            print(f"{current_user['name']} is not assigned as no school with space is available near {u_area}.")
            current_user['reason'] = f"priority {u_priority}, but unable to find school within 1hr nearby."
            unassigned_users.append(current_user)

        timings[f"{current_user['name']} timing"] = time.perf_counter() - user_start  # timing end

    timings["3. Main Allocation Loop Timing"] = time.perf_counter() - stage4_start #timing end
    # --- 5. DATA PREPARATION FOR EXPORT ---
    stage5_start = time.perf_counter()
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

    timings["4. Prepare Export Data Timing"] = time.perf_counter() - stage5_start

    # --- 6. CALCULATE SUMMARY STATISTICS ---
    stage6_start = time.perf_counter()
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
    timings["5. Calculate Summary Statistics Timing"] = time.perf_counter() - stage6_start

    # --- 7. FINAL EXPORT TO THREE SHEETS --- Todo: to change to json export
    # --- 7. FINAL OOP EXPORT TO JSON (NESTED STRUCTURE) ---
    stage7_start = time.perf_counter()
    try:
        # 1. Prepare Assignments (Build the nested dictionary directly)
        json_assignments = {}

        for s_name, volunteers in school_assignments.items():
            # Get the base info for the school
            school_data = {
                "Max Volunteers": school_info[s_name]['max'],
                "Area": school_info[s_name]['area']
            }

            # Sort volunteers by travel time (fastest first)
            volunteers_sorted = sorted(volunteers, key=lambda x: x['time_sec'])

            # Dynamically create "User 1", "User 2", etc. inside the school dict
            for v_idx, vol in enumerate(volunteers_sorted):
                mins, secs = divmod(vol['time_sec'], 60)

                user_key = f"User {v_idx + 1}"
                school_data[user_key] = {
                    "Name": vol['user_data']['name'],
                    "Travel Time": f"{int(mins)}m {int(secs)}s",
                    "Total Minutes": round(vol['time_sec'] / 60, 2),
                    "Distance (meters)": vol['dist']
                }

            # Assign this fully built block to the school name key
            json_assignments[s_name] = school_data

        # 2. Prepare Unassigned Users (Clean dictionaries)
        clean_unassigned = []
        for u in unassigned_users:
            clean_unassigned.append({
                'Priority': u[priority_col],
                'Name': u['name'],
                'Address': u['address'],
                'Reason': u['reason'],
            })

        # 3. Package everything into one master dictionary
        export_data = {
            "assignments": json_assignments,
            "unassigned_users": clean_unassigned,
            "summary_statistics": summary_data
        }

        # 4. Initialize the OOP Storage System for JSON
        storage = JSONStorage("data/final_modeling_assignments_OOP_V2.json")
        manager = DataManager(storage)

        # 5. Save everything
        manager.save_all(export_data)

        print(f"🎉 Success! Processed {len(final_rows)} schools and {len(user_df.to_dict('records'))} users.")
        print(f"📊 Summary: {total_assigned} assigned, {total_unassigned} unassigned.")
        print(f"🏫 Schools: {filled_schools} full, {unfilled_schools} with vacancies.")
        print(f"\n✅ Export complete. Data successfully saved to JSON via OOP DataManager.")
    except Exception as e:
        print(f"❌ JSON Export failed: {e}")
        #print(f"\n✅ All assignments finalized and saved to: {manager.storage.getfilepath()}")
    timings["6. JSON File Export"] = time.perf_counter() - stage7_start

    # --- 8. PRINT FINAL TIMING REPORT ---
    total_time = time.perf_counter() - total_start
    # Finalize the report structure
    performance_report = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_runtime_seconds": round(total_time, 4),
        "breakdown": {stage: round(duration, 4) for stage, duration in timings.items()},
        "metadata": {
            "total_users": len(user_df),
            "total_schools": len(school_df),
            "api_hits_estimated": len(api_cache)
        }
    }

    try:
        # Define the report path (e.g., using a timestamp to keep history)
        report_filename = f"data/performance_logs/report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        # Ensure the directory exists
        os.makedirs(os.path.dirname(report_filename), exist_ok=True)

        # Use your existing OOP Storage system
        perf_storage = JSONStorage(report_filename)
        perf_manager = DataManager(perf_storage)

        perf_manager.save_all(performance_report)

        print(f"\n📈 Performance report saved to: {report_filename}")

    except Exception as e:
        print(f"⚠️ Failed to save performance report: {e}")


def exporttoexcel(final_rows, unassigned_users, summary_data, headers, school_assignments, school_info):
    try:
        # Prepare the data dictionary for multi-sheet export
        export_data = {
            "Assignments": final_rows,
            "Unassigned Users": unassigned_users,
            "Summary Statistics": summary_data  # From your pandas summary dataframe
        }

        # Specify exact column headers for sheets that need it
        export_columns = {
            "Assignments": headers,
            "Unassigned Users": ['Priority', 'name', 'address'],
            "Summary Statistics": ["Metric", "Value"]
        }

        # Generate the custom formatter using your current variables
        my_formatter = create_allocation_formatter(school_assignments, school_info, final_rows)

        # Initialize the OOP Storage System
        storage = ExcelStorage("data/final_modeling_assignments.xlsx")
        manager = DataManager(storage)

        # Save everything with one command
        manager.save_all(
            data=export_data,
            columns=export_columns,
            format_func=my_formatter
        )
        return manager

    except Exception as e:
        print(f"❌ Export failed: {e}")

# --- MAIN LOGIC ---

def main():
    token = onemapApiHelper.get_valid_token()

    # 1. Load your data (Assuming Excel for this example)
    # user_df = pd.read_excel("data/users.xlsx")
    # school_df = pd.read_excel("data/schools.xlsx")


    #geoneighbour_dict = check_geo_neighbour()
    start = time.perf_counter()
    process_with_priority(user_file_path, school_file_path, token, ProcessedGeoJSON_FILE)
    end = time.perf_counter()
    print(f"Time taken for process to run: {end - start:.4f} seconds")

    # import random
    #
    # test = 67
    # numbers = []
    # while test != 0:
    #     numbers.append(random.randrange(2,7))
    #     test -= 1
    # random.shuffle(numbers)
    #
    # for n in numbers:
    #     print(f"{n}")



    #---Data System Testing---
    # Choose storage type dynamically
    # json_store = jsondatasystem.JSONStorage("data.json")
    # excel_store = exceldatasystem.ExcelStorage("data.xlsx")
    #
    # # Plug into manager
    # manager = dataStorageSystem.DataManager(json_store)
    #
    # manager.add_record({"name": "Alice", "age": 25})
    # manager.add_record({"name": "Bob", "age": 30})
    #
    # print(manager.get_all())
    #
    # # Switch storage easily
    # manager = dataStorageSystem.DataManager(excel_store)
    # manager.add_record({"name": "Charlie", "age": 40})


if __name__ == "__main__":
    main()