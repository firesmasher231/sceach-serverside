from flask import Flask, request, jsonify
import requests
import base64
from flask_cors import CORS, cross_origin
import inference_module
import math
import psycopg2
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
CORS(app)

# Initialize Flask-Limiter
limiter = Limiter(
    get_remote_address,  # Function to determine the address to limit by
    app=app,
    default_limits=["500 per day", "50 per hour"],  # Global rate limits
)

# Access environment variables
api_key = os.getenv("API_KEY")
api_url = os.getenv("API_URL")
project_id = os.getenv("PROJECT_ID")
model_version = int(os.getenv("MODEL_VERSION"))

import psycopg2


def latlon_to_tile(lat, lon, zoom):
    lat_rad = math.radians(lat)
    n = 2.0**zoom
    xtile = int((lon + 180.0) / 360.0 * n)
    ytile = int(
        (1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi)
        / 2.0
        * n
    )
    return xtile, ytile


def fetch_tile(version, zoom, x, y):
    url = f"https://wayback.maptiles.arcgis.com/arcgis/rest/services/World_Imagery/MapServer/tile/{version}/{zoom}/{y}/{x}"
    print(url)
    headers = {
        "Referer": "https://livingatlas.arcgis.com/",
        "Origin": "https://livingatlas.arcgis.com",
        "sec-ch-ua": '"Not)A;Brand";v="99", "Google Chrome";v="127", "Chromium";v="127"',
        "sec-ch-ua-mobile": "?0",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
        "sec-ch-ua-platform": '"Windows"',
    }

    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.content
    else:
        return None


def fetch_and_encode_tile(version, zoom, x, y):
    tile_data = fetch_tile(version, zoom, x, y)
    if tile_data:
        return base64.b64encode(tile_data).decode("utf-8")
    else:
        return None


def save_to_database(
    description, latitude, longitude, county, severity, status, before_img, after_img
):

    connection = None
    try:
        # connection = psycopg2.connect(
        #     database=os.getenv("DB_NAME"),
        #     host=os.getenv("DB_HOST"),
        #     user=os.getenv("DB_USER"),
        #     password=os.getenv("DB_PASSWORD"),
        #     port=os.getenv("DB_PORT"),
        # )

        connection = psycopg2.connect(os.getenv("DATABASE_URL"))

        cursor = connection.cursor()

        insert_query = """
        INSERT INTO violations (description, latitude, longitude, county, severity, status, before_img, after_img)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id;
        """

        cursor.execute(
            insert_query,
            (
                description,
                latitude,
                longitude,
                county,
                severity,
                status,
                before_img,
                after_img,
            ),
        )
        new_id = cursor.fetchone()[0]

        connection.commit()
        cursor.close()
        connection.close()

        return new_id

    except (Exception, psycopg2.DatabaseError) as error:
        print(f"Error: {error}")
        if connection is not None:
            connection.rollback()
            cursor.close()
            connection.close()
        return (
            jsonify({"error": "Failed to save processed images to the database"}),
            500,
        )


request_count = 0

# Define ANSI escape codes for colors
GREEN = "\033[92m"
YELLOW = "\033[93m"
RESET = "\033[0m"


# Middleware to increment request count
@app.before_request
def before_request():
    global request_count
    request_count += 1

    # Print the colored output
    print(f"{GREEN}request:{RESET} {YELLOW}{request_count}{RESET}")

import random


@app.route("/submit_scan", methods=["GET"])
@cross_origin()  # Allow CORS for this route
@limiter.limit("3 per second")
def get_tile():

    x = request.args.get("x")
    y = request.args.get("y")
    zoom = 18

    if not x or not y:
        return jsonify({"error": "Please provide both x and y coordinates"}), 400

    try:
        x = float(x)
        y = float(y)

        lat = x
        lon = y

        # Convert to tile coordinates
        xtile, ytile = latlon_to_tile(lat, lon, zoom)

        print(f"Tile coordinates for lat: {lat}, lon: {lon} at zoom level {zoom}:")
        print(f"Column: {xtile}, Row: {ytile}")
    except ValueError:
        return jsonify({"error": "Error Translating coordinates"}), 400

    years_versions = {
        "2024-03-07": "60013",
        # "2023-06-13": "25982",
        "2023-02-23": "57965",
        #  "2017-10-04": "15212",
        # "2016-10-25": "4222",
    }
    zoom_level = zoom

    tiles = {}
    for year, version in years_versions.items():
        encoded_tile = fetch_and_encode_tile(version, zoom_level, xtile, ytile)
        if encoded_tile:
            tiles[year] = encoded_tile
        else:
            return jsonify({"error": f"Failed to fetch tile for year {year}"}), 500

    processed_images,percentage_difference = inference_module.main(
        api_key, api_url, project_id, model_version, tiles
    )

    if percentage_difference == None:
        percentage_difference = 0

    try:
        percentage_difference = percentage_difference.__round__(2)
    except:
        percentage_difference = 0

    
    # for year, (image, area) in processed_images.items():
    #     print(f"Detected hedge with area: {area:.2f} square pixels in { year }")

    # Example data, replace with actual data from processed_images

    description = str(percentage_difference) + "% - "+ "Illegal trimming of hedges"
        
        
    # latitude = 53
    # longitude = -6
    county = "Cork"
    severity = percentage_difference
    status = "pending"
    # before_img = "a"

    # after_img = "b"
    if len(processed_images) < 2:
        return jsonify({"error": "Not enough processed images returned"}), 500

    # Extract the first and second values from the JSON object
    processed_values = list(processed_images.values())
    if len(processed_values) < 2:
        return jsonify({"error": "Not enough values in processed images"}), 500

    # if (len(processed_images) >= 2):
    # print(processed_images)
    print("lat", lat, "lon", lon)
    inserted_id = save_to_database(
        description,
        lat,
        lon,
        county,
        severity,
        status,
        processed_values[0],
        processed_values[1],
    )

    # try:
    #     print("1", processed_images["2024-03-07"][1])
    #     print("2", processed_images["2023-02-23"][1])
    #     difference = (
    #         (
    #             (
    #                 float(processed_images["2024-03-07"][1])
    #                 - float(processed_images["2023-02-23"][1])
    #             )
    #             / float(processed_images["2023-02-23"][1])
    #         )
    #         * 100
    #     ).__round__(2)
    # except:
    #     difference = 0

    return jsonify(
        {
            "processed_images": processed_images,
            "new_id": inserted_id,
            "difference": percentage_difference
    })
    # return jsonify(processed_images)


import os


@app.route("/submit_images", methods=["GET"])
@cross_origin()  # Allow CORS for this route
def process_images():

    # get all images in /images and pass them thru the inference model, save results to /ssed
    images = {}

    for filename in os.listdir("images"):
        with open(f"images/{filename}", "rb") as file:
            encoded_image = base64.b64encode(file.read()).decode("utf-8")
            images[filename] = encoded_image

    processed_images = inference_module.main(
        api_key, api_url, project_id, model_version, images
    )

    processed_values = list(processed_images.values())

    #  save results to /ssed
    for filename, image in processed_images.items():
        with open(f"ssed/{filename}", "wb") as file:
            file.write(base64.b64decode(image))

    return jsonify({"processed_images": processed_images, "new_id": inserted_id})


@app.route("/all_imgs", methods=["GET"])
@cross_origin()  # Allow CORS for this route
def get_all_images():
    images = {}
    for filename in os.listdir("ssed"):
        with open(f"ssed/{filename}", "rb") as file:
            encoded_image = base64.b64encode(file.read()).decode("utf-8")
            images[filename] = encoded_image

    return jsonify(images)

@app.route("/test", methods=["GET"])
@cross_origin()  # Allow CORS for this route
def test():
    
    return jsonify("testing")



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3001)
