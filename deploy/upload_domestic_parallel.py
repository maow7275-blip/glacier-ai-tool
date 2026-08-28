import concurrent.futures
import hashlib
import os
from pathlib import Path

import paramiko


local_exe = Path(os.environ["LOCAL_EXE"])
local_manifest = Path(os.environ["LOCAL_MANIFEST"])
remote_root = os.environ.get("REMOTE_ROOT", "/www/wwwroot/updateglacieraiw.com")
remote_exe = f"{remote_root}/downloads/{local_exe.name}"
remote_temp = f"{remote_exe}.parallel-uploading"
expected_hash = hashlib.sha256(local_exe.read_bytes()).hexdigest()
file_size = local_exe.stat().st_size


def connect():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        os.environ["DOM_HOST"],
        port=int(os.environ["DOM_PORT"]),
        username=os.environ["DOM_USER"],
        password=os.environ["DOM_PASS"],
    )
    return client


def upload_range(start, end):
    client = connect()
    try:
        sftp = paramiko.SFTPClient.from_transport(
            client.get_transport(),
            window_size=128 * 1024 * 1024,
            max_packet_size=1024 * 1024,
        )
        with local_exe.open("rb") as source, sftp.file(remote_temp, "r+b") as target:
            source.seek(start)
            target.seek(start)
            target.set_pipelined(True)
            remaining = end - start
            while remaining:
                chunk = source.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise RuntimeError("Unexpected end of local release file")
                target.write(chunk)
                remaining -= len(chunk)
        sftp.close()
    finally:
        client.close()


control = connect()
try:
    _, stdout, stderr = control.exec_command(f"truncate -s {file_size} '{remote_temp}'")
    if stdout.channel.recv_exit_status() != 0:
        raise RuntimeError(stderr.read().decode("utf-8", errors="replace").strip())

    worker_count = 4
    chunk_size = (file_size + worker_count - 1) // worker_count
    ranges = [
        (start, min(start + chunk_size, file_size))
        for start in range(0, file_size, chunk_size)
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
        list(executor.map(lambda bounds: upload_range(*bounds), ranges))

    _, stdout, stderr = control.exec_command(f"sha256sum '{remote_temp}'")
    if stdout.channel.recv_exit_status() != 0:
        raise RuntimeError(stderr.read().decode("utf-8", errors="replace").strip())
    remote_hash = stdout.read().decode("ascii").split()[0].lower()
    if remote_hash != expected_hash:
        raise RuntimeError(f"Remote SHA-256 mismatch: {remote_hash}")

    _, stdout, stderr = control.exec_command(f"mv -f '{remote_temp}' '{remote_exe}'")
    if stdout.channel.recv_exit_status() != 0:
        raise RuntimeError(stderr.read().decode("utf-8", errors="replace").strip())
    sftp = control.open_sftp()
    sftp.put(str(local_manifest), f"{remote_root}/update.json")
    sftp.close()
finally:
    control.close()

print(f"domestic release uploaded: {local_exe.name} {expected_hash}")
