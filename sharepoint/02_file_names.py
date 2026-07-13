import requests
import os

ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")

DRIVE_ID = "b!iGrRnQriWUarYCrGXVICzrHCgcmdmPtAuMEHeKyGxhqv3MbJuQLPTpJeAWaUSDwM"

FOLDER_ID = "01HFX3W2523YELY3UT2ZBYLGPNNRFEQBNH"

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

for file in files:
    print(file["name"])