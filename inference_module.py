from inference_sdk import InferenceHTTPClient
from PIL import Image
import matplotlib.pyplot as plt
import os
import numpy as np
import io
import base64
import cv2

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


from shapely.geometry import MultiPolygon, Polygon
from matplotlib.patches import Polygon as MplPolygon


def draw_predictions(image, predictions, fill_color="red", alpha=1.0):
    plt.figure(figsize=(10, 10))
    plt.imshow(image)
    ax = plt.gca()

    if isinstance(predictions, MultiPolygon):
        # Iterate over each Polygon in the MultiPolygon
        for polygon in predictions.geoms:
            x, y = polygon.exterior.xy
            ax.add_patch(
                MplPolygon(
                    np.column_stack([x, y]), 
                    fill=True, 
                    edgecolor=fill_color, 
                    facecolor=fill_color, 
                    alpha=alpha
                )
            )
    elif isinstance(predictions, Polygon):
        # Handle a single Polygon
        x, y = predictions.exterior.xy
        ax.add_patch(
            MplPolygon(
                np.column_stack([x, y]), 
                fill=True, 
                edgecolor=fill_color, 
                facecolor=fill_color, 
                alpha=alpha
            )
        )
    else:
        # Assuming predictions is a dictionary with key "predictions"
        for prediction in predictions["predictions"]:
            points = prediction["points"]
            mpl_polygon = MplPolygon(
                [(p["x"], p["y"]) for p in points], 
                fill=True, 
                edgecolor=fill_color, 
                facecolor=fill_color, 
                alpha=alpha
            )
            ax.add_patch(mpl_polygon)
            ax.text(
                points[0]["x"],
                points[0]["y"],
                prediction["class"],
                color="white",
                fontsize=12,
            )

    plt.axis("off")
    plt.subplots_adjust(left=0, right=1, top=1, bottom=0)

    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight", pad_inches=0)
    buf.seek(0)
    plt.close()
    return base64.b64encode(buf.read()).decode("utf-8")


from skimage import exposure, img_as_ubyte


def preprocess_image(pil_image):
    # Convert PIL image to numpy array
    img_array = np.array(pil_image)

    # Apply CLAHE
    if img_array.ndim == 3:
        # Convert the image to LAB color space
        lab = cv2.cvtColor(img_array, cv2.COLOR_RGB2LAB)
        l, a, b = cv2.split(lab)

        # Apply CLAHE to the L channel
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        cl = clahe.apply(l)

        # Merge the CLAHE enhanced L channel back with A and B channels
        limg = cv2.merge((cl, a, b))

        # Convert LAB back to RGB
        img_array = cv2.cvtColor(limg, cv2.COLOR_LAB2RGB)
    else:
        # Apply CLAHE to the grayscale image
        img_array = exposure.equalize_adapthist(img_array, clip_limit=0.03)
        img_array = img_as_ubyte(img_array)

    # Convert back to PIL image
    return Image.fromarray(img_array)


def process_image(base64_image, client, project_id, model_version):
    image_data = base64.b64decode(base64_image)
    pil_image = Image.open(io.BytesIO(image_data))

    if pil_image.mode == "RGBA":
        pil_image = pil_image.convert("RGB")

    # Preprocess the image using CLAHE
    # preprocessed_image = preprocess_image(pil_image)

    preprocessed_image = pil_image

    results = client.infer(preprocessed_image, model_id=f"{project_id}/{model_version}")

    return results, pil_image


# def main(api_key, api_url, project_id, model_version, base64_images):
#     client = configure_client(api_key, api_url)
#     processed_images = {}
#     results = {}
#     pil_images = {}
#     for year, base64_image in base64_images.items():
#         results[year], pil_images[year] = process_image(
#             base64_image, client, project_id, model_version
#         )


#     total_area = 0
#     for year, result in results.items():
#         for prediction in result["predictions"]:
#             if prediction["class"] == "hedge":
#                 area = polygon_area(prediction["points"])
#                 total_area += area
#                 print(f"Detected hedge with area: {area:.2f} square pixels")

#     from shapely.geometry import Polygon

#     print("results",results)

#     try:
            
#         hedge1 = Polygon(
#             [(p["x"], p["y"]) for p in results["2024-03-07"]["predictions"][0]["points"]]
#         )
#         hedge2 = Polygon(
#             [(p["x"], p["y"]) for p in results["2023-02-23"]["predictions"][0]["points"]]
#         )

#         difference = hedge1.difference(hedge2)
#         print(
#             f"Difference in area between 2024-03-07 and 2023-02-23: {difference.area:.2f} square pixels"
#         )

#         processed_images["difference"] = (draw_predictions(
#             pil_images["2023-02-23"] , difference, fill_color="orange", alpha=0.4
#         ))
#         processed_images["2023-02-23"] = draw_predictions(
#             pil_images["2024-03-07"], results["2023-02-23"], fill_color="blue", alpha=0
#         )
#     except:

#         processed_images["difference"] = (draw_predictions(
#             pil_images["2023-02-23"] , results["2023-02-23"], fill_color="orange", alpha=0
#         ))
#         processed_images["2023-02-23"] = draw_predictions(
#             pil_images["2024-03-07"], results["2023-02-23"], fill_color="blue", alpha=0
#         )
        

#     print(f"Total area of all detected hedges: {total_area:.2f} square pixels")

#     return processed_images

def main(api_key, api_url, project_id, model_version, base64_images):
    client = configure_client(api_key, api_url)
    processed_images = {}
    results = {}
    pil_images = {}
    hedge_areas = {}

    for year, base64_image in base64_images.items():
        results[year], pil_images[year] = process_image(
            base64_image, client, project_id, model_version
        )
        hedge_areas[year] = 0  # Initialize area for each image

    total_area = 0
    for year, result in results.items():
        for prediction in result["predictions"]:
            if prediction["class"] == "hedge":
                area = polygon_area(prediction["points"])
                hedge_areas[year] += area  # Accumulate area for the specific image
                total_area += area
                print(f"Detected hedge with area: {area:.2f} square pixels")

    from shapely.geometry import Polygon

    # print("results", results)

    try:
        hedge1 = Polygon(
            [(p["x"], p["y"]) for p in results["2024-03-07"]["predictions"][0]["points"]]
        )
        hedge2 = Polygon(
            [(p["x"], p["y"]) for p in results["2023-02-23"]["predictions"][0]["points"]]
        )

        difference = hedge1.difference(hedge2)
        print(
            f"Difference in area between 2024-03-07 and 2023-02-23: {difference.area:.2f} square pixels"
        )

        processed_images["difference"] = draw_predictions(
            pil_images["2023-02-23"], difference, fill_color="orange", alpha=0.4
        )
        processed_images["2023-02-23"] = draw_predictions(
            pil_images["2024-03-07"], results["2023-02-23"], fill_color="blue", alpha=0
        )

        # Calculate the percentage difference
        area1 = hedge1.area
        area2 = hedge2.area
        percentage_difference = abs(area1 - area2) / ((area1 + area2) / 2) * 100
        print(f"Percentage difference: {percentage_difference:.2f}%")

    except Exception as e:
        print(f"Error calculating areas or drawing predictions: {str(e)}")
        processed_images["difference"] = draw_predictions(
            pil_images["2023-02-23"], results["2023-02-23"], fill_color="orange", alpha=0
        )
        processed_images["2023-02-23"] = draw_predictions(
            pil_images["2024-03-07"], results["2023-02-23"], fill_color="blue", alpha=0
        )
        percentage_difference = None

    print(f"Total area of all detected hedges: {total_area:.2f} square pixels")

    return processed_images, percentage_difference

if __name__ == "__main__":
    api_key = os.getenv("API_KEY")
    api_url = os.getenv("API_URL")
    project_id = os.getenv("PROJECT_ID")
    model_version = int(os.getenv("MODEL_VERSION"))
    base64_images = {
        "image1": "base64_encoded_string1",
        "image2": "base64_encoded_string2",
    }
    processed_images = main(api_key, api_url, project_id, model_version, base64_images)
    print(processed_images)