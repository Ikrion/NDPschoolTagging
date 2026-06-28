import requests
import time
import os
import threading
import random

class OneMapRateLimiter:
    def __init__(self):
        self.max_calls_per_minute = 250
        self.window_seconds = 60

        self.window_start = time.time()
        self.call_count = 0

        self.lock = threading.Lock()

    def wait_if_needed(self):
        while True:
            with self.lock:
                now = time.time()

                # Start a new window
                if now - self.window_start >= self.window_seconds:
                    self.window_start = now
                    self.call_count = 0

                # Under the limit
                if self.call_count < self.max_calls_per_minute:
                    self.call_count += 1
                    print(
                        f"OneMap Rate: {self.call_count}/{self.max_calls_per_minute}"
                    )
                    return True

                # Need to wait until next window
                wait_time = self.window_seconds - (now - self.window_start)
                wait_time = max(wait_time, 0)

            # Sleep outside the lock
            sleep_time = wait_time + random.uniform(0.1, 0.5)
            print(
                f"Rate limit reached ({self.call_count}/{self.max_calls_per_minute}). "
                f"Waiting {sleep_time:.2f}s..."
            )
            time.sleep(sleep_time)

# Place this near your imports/configuration
session = requests.Session()
# --- CONFIGURATION ---
EMAIL = "zhanghaien100@gmail.com"
PASSWORD = "Blk-457-13@haien"
TOKEN_FILE = "token_cache.txt"

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
        res = session.get(search_url, params=search_params, headers=headers).json()

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