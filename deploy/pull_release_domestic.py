import os
import paramiko

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(os.environ["DOM_HOST"], port=int(os.environ["DOM_PORT"]), username=os.environ["DOM_USER"], password=os.environ["DOM_PASS"])
cmd = "set -e; url='https://github.com/maow7275-blip/glacier-ai-release/releases/download/v3.8.1/GlacierAI_V3.8.1.exe'; temp='/www/wwwroot/updateglacieraiw.com/downloads/GlacierAI_V3.8.1.exe.uploading'; final='/www/wwwroot/updateglacieraiw.com/downloads/GlacierAI_V3.8.1.exe'; curl -L --fail --retry 5 -o \"$temp\" \"$url\"; sha256sum \"$temp\"; mv -f \"$temp\" \"$final\""
_, stdout, stderr = c.exec_command(cmd)
code = stdout.channel.recv_exit_status()
print(stdout.read().decode())
print(stderr.read().decode())
c.close()
raise SystemExit(code)
