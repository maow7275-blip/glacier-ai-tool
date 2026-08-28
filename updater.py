"""Small Windows helper that replaces GlacierAI after the app exits."""

import argparse
import ctypes
import os
import subprocess
import sys
import time


def process_is_running(pid):
    handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return False
    try:
        exit_code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
        return exit_code.value == 259
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


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
