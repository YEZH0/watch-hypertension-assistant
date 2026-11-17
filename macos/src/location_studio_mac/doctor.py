"""GPL-3.0-only. Read-only dependency check; no USB or Apple ticket requests."""
import importlib.metadata
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def inspect_environment():
    checks = []
    def add(name, ok, blocking=True):
        checks.append({'name': name, 'ok': bool(ok), 'blocking': blocking})
    add('macOS', platform.system() == 'Darwin')
    add('Python >= 3.11', sys.version_info >= (3, 11))
    for package in ('ios-location-studio-mac', 'watch-hypertension-assistant', 'PySide6', 'pymobiledevice3'):
        try:
            version = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            version = None
        add(package, version is not None)
        checks[-1]['version'] = version
    add('sandbox-exec', Path('/usr/bin/sandbox-exec').is_file())
    xcrun = shutil.which('xcrun')
    ready = False
    if xcrun:
        try:
            ready = subprocess.run([xcrun, '--find', 'devicectl'], capture_output=True,
                                   timeout=10, check=False).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            pass
    add('Xcode devicectl（首次镜像准备）', ready, blocking=False)
    return {'platform': platform.system(), 'macos': platform.mac_ver()[0],
            'architecture': platform.machine(), 'checks': checks,
            'ready': all(c['ok'] for c in checks if c['blocking']),
            'device_authorization': 'unknown_pending_user_verification',
            'notice': '未访问 USB、未发送坐标、未请求 Apple 票据；设备与地图仍需人工核验。'}


def main():
    result = inspect_environment()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['ready'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
