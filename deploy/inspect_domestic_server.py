import os

import paramiko


c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(
    os.environ["DOM_HOST"],
    port=int(os.environ["DOM_PORT"]),
    username=os.environ["DOM_USER"],
    password=os.environ["DOM_PASS"],
)
for command in (
    "uname -a",
    "ls -la /www/wwwroot/updateglacieraiw.com",
    "find /www/server -maxdepth 3 -type f -iname '*nginx*' 2>/dev/null | head -20",
    "ps aux | egrep 'nginx|apache|php|caddy' | grep -v grep",
):
    _, stdout, stderr = c.exec_command(command)
    stdout.channel.recv_exit_status()
    print("---", command)
    print(stdout.read().decode("utf-8", errors="replace"))
    print(stderr.read().decode("utf-8", errors="replace"))
c.close()
