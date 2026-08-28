import os

import paramiko


token = os.environ["GITHUB_TOKEN"]
release_id = os.environ["RELEASE_ID"]
repository = os.environ["REPOSITORY"]
asset_name = os.environ["ASSET_NAME"]
remote_path = os.environ["REMOTE_PATH"]

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(
    "89.116.246.21",
    username="root",
    key_filename="C:/Users/Administrator/Desktop/vps-proxy.pem",
)
upload_url = (
    f"https://uploads.github.com/repos/{repository}/releases/{release_id}/assets"
    f"?name={asset_name}"
)
command = (
    "curl -fsS --retry 5 -X POST "
    f"-H 'Authorization: Bearer {token}' "
    "-H 'Content-Type: application/octet-stream' "
    f"--data-binary '@{remote_path}' '{upload_url}' "
    "-o /tmp/glacier-github-upload.json"
)
_, stdout, stderr = client.exec_command(command)
exit_code = stdout.channel.recv_exit_status()
error = stderr.read().decode("utf-8", errors="replace").strip()
client.close()
if exit_code:
    raise SystemExit(error or f"Upload failed with exit code {exit_code}")
print("release asset upload completed")
