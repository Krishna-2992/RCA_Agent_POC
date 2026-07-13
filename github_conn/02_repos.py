import os
import requests

headers = {
    "Authorization": f"Bearer {os.getenv('GITHUB_TOKEN')}"
}

repos_response = requests.get(
    "https://api.github.com/user/repos?per_page=100",
    headers=headers
)

repos_data = repos_response.json()

repositories = [
    repo["full_name"]
    for repo in repos_data
]

print(repositories)