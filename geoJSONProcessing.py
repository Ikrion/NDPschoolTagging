import geopandas as gpd
import json


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