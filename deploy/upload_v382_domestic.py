import os
from pathlib import Path
import paramiko

host, user, password, port = os.environ["DOM_HOST"], os.environ["DOM_USER"], os.environ["DOM_PASS"], int(os.environ["DOM_PORT"])
local = Path(os.environ["LOCAL_EXE"])
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy()); c.connect(host, port=port, username=user, password=password)
try:
    sftp = paramiko.SFTPClient.from_transport(c.get_transport(), window_size=128*1024*1024, max_packet_size=1024*1024)
    remote_tmp = '/www/wwwroot/updateglacieraiw.com/downloads/GlacierAI_V3.8.2.exe.uploading'
    with local.open('rb') as src, sftp.file(remote_tmp, 'wb') as dst:
        dst.set_pipelined(True)
        while chunk := src.read(1024*1024): dst.write(chunk)
    sftp.close()
    _,o,e=c.exec_command("sha256sum /www/wwwroot/updateglacieraiw.com/downloads/GlacierAI_V3.8.2.exe.uploading && mv -f /www/wwwroot/updateglacieraiw.com/downloads/GlacierAI_V3.8.2.exe.uploading /www/wwwroot/updateglacieraiw.com/downloads/GlacierAI_V3.8.2.exe")
    print(o.read().decode()); print(e.read().decode());
    s=c.open_sftp(); s.put(os.environ['LOCAL_MANIFEST'],'/www/wwwroot/updateglacieraiw.com/update.json'); s.put(os.environ['LOCAL_PAGE'],'/www/wwwroot/updateglacieraiw.com/index.html'); s.close()
finally: c.close()
