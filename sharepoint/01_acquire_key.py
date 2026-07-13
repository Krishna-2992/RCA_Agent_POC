import requests
import os

ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")

headers = {
    "Authorization": f"Bearer {ACCESS_TOKEN}"
}

url = "https://graph.microsoft.com/v1.0/me"

print(requests.get(url, headers=headers).json())