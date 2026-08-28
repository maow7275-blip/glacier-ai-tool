import hashlib
import os
from pathlib import Path

import paramiko


local_exe = Path(os.environ["LOCAL_EXE"])
local_manifest = Path(os.environ["LOCAL_MANIFEST"])
remote_root = os.environ.get("REMOTE_ROOT", "/www/wwwroot/updateglacieraiw.com")
remote_exe = f"{remote_root}/downloads/{local_exe.name}"
remote_temp = f"{remote_exe}.uploading"
expected_hash = hashlib.sha256(local_exe.read_bytes()).hexdigest()

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(
    os.environ["DOM_HOST"],
    port=int(os.environ["DOM_PORT"]),
    username=os.environ["DOM_USER"],
    password=os.environ["DOM_PASS"],
)

try:
    sftp = paramiko.SFTPClient.from_transport(
        client.get_transport(),
        window_size=128 * 1024 * 1024,
        max_packet_size=1024 * 1024,
    )
    try:
        uploaded_size = sftp.stat(remote_temp).st_size
    except FileNotFoundError:
        uploaded_size = 0
    if uploaded_size > local_exe.stat().st_size:
        raise RuntimeError("Remote temporary file is larger than the local release")

    with local_exe.open("rb") as source, sftp.file(remote_temp, "ab") as target:
        source.seek(uploaded_size)
        target.set_pipelined(True)
        while chunk := source.read(1024 * 1024):
            target.write(chunk)
    _, stdout, stderr = client.exec_command(f"sha256sum '{remote_temp}'")
    if stdout.channel.recv_exit_status() != 0:
        raise RuntimeError(stderr.read().decode("utf-8", errors="replace").strip())
    remote_hash = stdout.read().decode("ascii").split()[0].lower()
    if remote_hash != expected_hash:
        raise RuntimeError(f"Remote SHA-256 mismatch: {remote_hash}")

    _, stdout, stderr = client.exec_command(f"mv -f '{remote_temp}' '{remote_exe}'")
    if stdout.channel.recv_exit_status() != 0:
        raise RuntimeError(stderr.read().decode("utf-8", errors="replace").strip())
    sftp.put(str(local_manifest), f"{remote_root}/update.json")
    sftp.close()
finally:
    client.close()

print(f"domestic release uploaded: {local_exe.name} {expected_hash}")
