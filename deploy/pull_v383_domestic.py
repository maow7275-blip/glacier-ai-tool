import os
import paramiko

c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(os.environ['DOM_HOST'], port=int(os.environ['DOM_PORT']), username=os.environ['DOM_USER'], password=os.environ['DOM_PASS'])
try:
    cmd = "set -e; url='https://github.com/maow7275-blip/glacier-ai-tool/releases/download/v3.8.3/GlacierAI_V3.8.3.exe'; temp='/www/wwwroot/updateglacieraiw.com/downloads/GlacierAI_V3.8.3.exe.uploading'; final='/www/wwwroot/updateglacieraiw.com/downloads/GlacierAI_V3.8.3.exe'; curl -L --fail --retry 5 -o \"$temp\" \"$url\"; sha256sum \"$temp\"; mv -f \"$temp\" \"$final\""
    _,o,e=c.exec_command(cmd); print(o.read().decode()); print(e.read().decode())
finally: c.close()
