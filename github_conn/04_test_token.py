import os
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("GITHUB_TOKEN")

OWNER = "Krishna-2992"
REPO = "Dummy_RCA_Payment_app"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json"
}

# ---------------------------------------------------
# Check authenticated user
# ---------------------------------------------------

print("\nChecking authenticated user...")

response = requests.get(
    "https://api.github.com/user",
    headers=headers
)

print("Status:", response.status_code)

if response.status_code == 200:
    print("Authenticated as:", response.json()["login"])
else:
    print(response.text)
    exit()


# ---------------------------------------------------
# Check repository access
# ---------------------------------------------------

print(f"\nChecking access to {OWNER}/{REPO}")

response = requests.get(
    f"https://api.github.com/repos/{OWNER}/{REPO}",
    headers=headers
)

print("Status:", response.status_code)

if response.status_code == 200:
    repo = response.json()

    print("\nSUCCESS")
    print("Repository exists and token can access it.")
    print("Full name:", repo["full_name"])
    print("Private:", repo["private"])

elif response.status_code == 404:
    print("\nFAILED")
    print("Repository not found OR token has no access.")

else:
    print(response.text)


# ---------------------------------------------------
# Check repository contents
# ---------------------------------------------------

print("\nChecking repository contents...")

response = requests.get(
    f"https://api.github.com/repos/{OWNER}/{REPO}/contents",
    headers=headers
)

print("Status:", response.status_code)

if response.status_code == 200:
    print("\nTop level files:")
    for item in response.json():
        print("-", item["name"])

else:
    print(response.text)