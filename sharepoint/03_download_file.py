import requests
import os

DOWNLOAD_DIR = "sharepoing_downloads"

ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")

DRIVE_ID = os.getenv("DRIVE_ID")

FOLDER_ID = os.getenv("FOLDER_ID")

headers = {
    "Authorization": f"Bearer {ACCESS_TOKEN}"
}

url = (
    f"https://graph.microsoft.com/v1.0/drives/"
    f"{DRIVE_ID}/items/{FOLDER_ID}/children"
)

response = requests.get(url, headers=headers)

response.raise_for_status()

files = response.json()["value"]

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

for file in files:

    item_id = file["id"]

    filename = file["name"]

    download_url = (

        f"https://graph.microsoft.com/v1.0/drives/"

        f"{DRIVE_ID}/items/{item_id}/content"

    )

    pdf = requests.get(download_url, headers=headers)

    pdf.raise_for_status()

    with open(os.path.join(DOWNLOAD_DIR, filename), "wb") as f:

        f.write(pdf.content)

    print(f"Downloaded {filename}")