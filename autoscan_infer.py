from inference_sdk import InferenceHTTPClient
from PIL import Image
import matplotlib.pyplot as plt
import os
import numpy as np
import io
import base64
from shapely.geometry import *

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def configure_client(api_key, api_url):
    os.environ["API_KEY"] = api_key
    return InferenceHTTPClient(api_url=api_url, api_key=os.environ["API_KEY"])


def polygon_area(points):
    x = [p["x"] for p in points]
    y = [p["y"] for p in points]
    return 0.5 * np.abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))


def draw_predictions(image, predictions):
    plt.figure(figsize=(10, 10))
    plt.imshow(image)
    ax = plt.gca()

    if isinstance(predictions, Polygon):
        # Handle a single Polygon
        x, y = predictions.exterior.xy
        ax.plot(x, y, color="red")
        ax.add_patch(plt.Polygon(np.column_stack([x, y]), fill=None, edgecolor="red"))
    elif isinstance(predictions, MultiPolygon):
        # Iterate over each Polygon in the MultiPolygon
        for polygon in predictions.geoms:
            x, y = polygon.exterior.xy
            ax.plot(x, y, color="red")
            ax.add_patch(
                plt.Polygon(np.column_stack([x, y]), fill=None, edgecolor="red")
            )
    elif isinstance(predictions, GeometryCollection):
        # Handle GeometryCollection
        for geom in predictions.geoms:
            if isinstance(geom, Polygon):
                x, y = geom.exterior.xy
                ax.plot(x, y, color="red")
                ax.add_patch(
                    plt.Polygon(np.column_stack([x, y]), fill=None, edgecolor="red")
                )
            elif isinstance(geom, LineString):
                x, y = geom.xy
                ax.plot(x, y, color="blue")
            elif isinstance(geom, Point):
                ax.plot(geom.x, geom.y, "bo")
    else:
        # Assuming predictions is a dictionary with key "predictions"
        for prediction in predictions["predictions"]:
            points = prediction["points"]
            mpl_polygon = plt.Polygon(
                [(p["x"], p["y"]) for p in points], fill=None, edgecolor="red"
            )
            ax.add_patch(mpl_polygon)
            ax.text(
                points[0]["x"],
                points[0]["y"],
                prediction["class"],
                color="red",
                fontsize=12,
            )

    plt.axis("off")
    plt.subplots_adjust(left=0, right=1, top=1, bottom=0)

    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight", pad_inches=0)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


def process_image(image_path, client, project_id, model_version):
    pil_image = Image.open(image_path)

    if pil_image.mode == "RGBA":
        pil_image = pil_image.convert("RGB")

    results = client.infer(pil_image, model_id=f"{project_id}/{model_version}")
    return results, pil_image


def draw_predictions(image, predictions):
    plt.figure(figsize=(10, 10))
    plt.imshow(image)
    ax = plt.gca()

    if isinstance(predictions, Polygon):
        # Handle a single Polygon
        x, y = predictions.exterior.xy
        ax.plot(x, y, color="red")
        ax.add_patch(plt.Polygon(np.column_stack([x, y]), fill=None, edgecolor="red"))
    elif isinstance(predictions, MultiPolygon):
        # Iterate over each Polygon in the MultiPolygon
        for polygon in predictions.geoms:
            x, y = polygon.exterior.xy
            ax.plot(x, y, color="red")
            ax.add_patch(
                plt.Polygon(np.column_stack([x, y]), fill=None, edgecolor="red")
            )
    else:
        # Assuming predictions is a dictionary with key "predictions"
        for prediction in predictions["predictions"]:
            points = prediction["points"]
            mpl_polygon = plt.Polygon(
                [(p["x"], p["y"]) for p in points], fill=None, edgecolor="red"
            )
            ax.add_patch(mpl_polygon)
            ax.text(
                points[0]["x"],
                points[0]["y"],
                prediction["class"],
                color="red",
                fontsize=12,
            )

    plt.axis("off")
    plt.subplots_adjust(left=0, right=1, top=1, bottom=0)

    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight", pad_inches=0)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


def compare_images(image1, image2, results1, results2):
    if not results1["predictions"] or not results2["predictions"]:
        print("No predictions found in one of the images.")
        return None, None

    hedge1 = Polygon([(p["x"], p["y"]) for p in results1["predictions"][0]["points"]])
    hedge2 = Polygon([(p["x"], p["y"]) for p in results2["predictions"][0]["points"]])

    difference = hedge1.difference(hedge2)
    diff_area = difference.area

    return diff_area, difference


def main(api_key, api_url, project_id, model_version, input_folder, output_folder):
    client = configure_client(api_key, api_url)

    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    # Group images by their coordinates (x, y)
    image_groups = {}
    for image_file in os.listdir(input_folder):
        if os.path.isfile(os.path.join(input_folder, image_file)):
            # Assuming file name format is version_x_y.jpg
            parts = image_file.split("_")
            coord_key = f"{parts[1]}_{parts[2]}"
            if coord_key not in image_groups:
                image_groups[coord_key] = []
            image_groups[coord_key].append(image_file)

    # Process each pair
    for coord_key, files in image_groups.items():
        if len(files) == 2:  # Ensure there are exactly two versions
            image_file1 = files[0]
            image_file2 = files[1]

            image_path1 = os.path.join(input_folder, image_file1)
            image_path2 = os.path.join(input_folder, image_file2)

            results1, pil_image1 = process_image(
                image_path1, client, project_id, model_version
            )
            results2, pil_image2 = process_image(
                image_path2, client, project_id, model_version
            )

            diff_area, difference = compare_images(
                pil_image1, pil_image2, results1, results2
            )

            if diff_area is None or difference is None:
                print(
                    f"Skipping pair {image_file1} and {image_file2} due to no predictions."
                )
                continue

            diff_percentage = (
                diff_area / polygon_area(results1["predictions"][0]["points"])
            ) * 100

            diff_image_name = (
                f"difference_{int(diff_percentage)}_percent_{coord_key.replace(".jpg","")}.png"
            )
            diff_image_path = os.path.join(output_folder, diff_image_name)

            diff_image_base64 = draw_predictions(pil_image2, difference)
            diff_image = Image.open(io.BytesIO(base64.b64decode(diff_image_base64)))
            diff_image.save(diff_image_path)

            print(
                f"Processed {image_file1} and {image_file2}: Difference {diff_percentage:.2f}% saved as {diff_image_name}"
            )
        else:
            print(
                f"Skipping group {coord_key}: Expected 2 versions, found {len(files)}."
            )

if __name__ == "__main__":
    api_key = os.getenv("API_KEY")
    api_url = os.getenv("API_URL")
    project_id = os.getenv("PROJECT_ID")
    model_version = int(os.getenv("MODEL_VERSION"))
    input_folder = "images"
    output_folder = "inferred"

    main(api_key, api_url, project_id, model_version, input_folder, output_folder)