import os
import requests

headers = {
    "Authorization": f"Bearer {os.getenv('GITHUB_TOKEN')}"
}

user_response = requests.get(
    "https://api.github.com/user",
    headers=headers
)

user_data = user_response.json()

github_username = user_data["login"]

print(github_username)