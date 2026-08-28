import os
import requests

token = os.environ["GITHUB_TOKEN"]
repo = os.environ["REPOSITORY"]
name = os.environ["ASSET_NAME"]
path = os.environ["LOCAL_EXE"]
headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
base = f"https://api.github.com/repos/{repo}"
release = requests.get(f"{base}/releases/tags/v3.8.1", headers=headers, timeout=30).json()
for asset in release.get("assets", []):
    if asset["name"] == name:
        response = requests.delete(asset["url"], headers=headers, timeout=30)
        response.raise_for_status()
        break
with open(path, "rb") as source:
    response = requests.post(
        f"https://uploads.github.com/repos/{repo}/releases/{release['id']}/assets",
        params={"name": name},
        headers={**headers, "Content-Type": "application/octet-stream"},
        data=source,
        timeout=600,
    )
response.raise_for_status()
print("release asset replaced")
