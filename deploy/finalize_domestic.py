import os

import paramiko


root = "/www/wwwroot/updateglacieraiw"
temp = f"{root}/downloads/GlacierAI_V3.8.1.exe.parallel-uploading"
final = f"{root}/downloads/GlacierAI_V3.8.1.exe"

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(
    os.environ["DOM_HOST"],
    port=int(os.environ["DOM_PORT"]),
    username=os.environ["DOM_USER"],
    password=os.environ["DOM_PASS"],
)
try:
    _, stdout, stderr = c.exec_command(f"sha256sum '{temp}' && mv -f '{temp}' '{final}'")
    code = stdout.channel.recv_exit_status()
    output = stdout.read().decode("utf-8", errors="replace").strip()
    error = stderr.read().decode("utf-8", errors="replace").strip()
    if code:
        raise SystemExit(error or output)
    print(output)
    sftp = c.open_sftp()
    sftp.put(os.environ["LOCAL_MANIFEST"], f"{root}/update.json")
    sftp.close()
finally:
    c.close()
