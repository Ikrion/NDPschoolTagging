import geopandas as gpd
import json
import os


def download_geojson_with_polling():
    dataset_id = "d_2cc750190544007400b2cfd5d7f53209"
    initiate_url = f"https://api-open.data.gov.sg/v1/public/api/datasets/{dataset_id}/initiate-download"
    poll_url = f"https://api-open.data.gov.sg/v1/public/api/datasets/{dataset_id}/poll-download"

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


def generate_neighbor_map(geojson_path):
    # Load the map of Singapore
    sg_map = gpd.read_file(geojson_path)

    neighbor_dict = {}

    for index, area in sg_map.iterrows():
        area_name = area['PLN_AREA_N'].upper()

        # GeoPandas magic: Find all areas that touch this area's border
        touching = sg_map[sg_map.geometry.touches(area.geometry)]

        # Extract their names into a list
        neighbor_names = touching['PLN_AREA_N'].str.upper().tolist()

        neighbor_dict[area_name] = neighbor_names

    # Save it to a JSON file so your main script can use it instantly
    with open("data/area_neighbors.json", "w") as f:
        json.dump(neighbor_dict, f)

    print("✅ Neighbor map generated and saved!")