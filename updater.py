"""Small Windows helper that replaces GlacierAI after the app exits."""

import argparse
import os
import subprocess
import sys
import time


def process_is_running(pid):
    """Check the parent process without importing ctypes.

    The updater is shipped as a tiny standalone executable.  Calling the
    native ``tasklist`` command keeps it independent from the optional
    ``_ctypes`` extension, which was missing from some older customer builds.
    """
    if pid <= 0:
        return False
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
            creationflags=creationflags,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return f'"{pid}"' in result.stdout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--target", required=True)
    args = parser.parse_args()

    deadline = time.monotonic() + 90
    while process_is_running(args.pid) and time.monotonic() < deadline:
        time.sleep(0.25)

    while time.monotonic() < deadline:
        try:
            os.replace(args.source, args.target)
            subprocess.Popen([args.target], cwd=os.path.dirname(args.target))
            return 0
        except OSError:
            time.sleep(0.5)
    return 1


if __name__ == "__main__":
    sys.exit(main())
