"""Local isolated worker. Never emits identifiers or credential contents."""
import asyncio
import json
import sys
from pathlib import Path


def resources():
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS) / 'upstream'
    return Path(__file__).resolve().parents[2] / 'vendor/accessory-location'


def run():
    action = sys.argv[2]
    if action in ('dvt_prepare','dvt_probe','dvt_send'):
        from .dvt import main
        main(action,sys.argv[3:]);return
    if action == 'helper':
        import runpy
        runpy.run_path(str(resources() / 'tools/local_mfi_v3_helper.py'), run_name='__main__')
        return
    if action == 'device':
        asyncio.run(device())
        return
    from pymobiledevice3.usbmux import list_devices
    devices = asyncio.run(list_devices())
    if sum(str(d.connection_type) == "USB" for d in devices) != 1:
        print(json.dumps({"event":"error","type":"RequireExactlyOneUSBDevice"}),flush=True)
        raise SystemExit(1)
    from accessory_location.cli import main
    sys.argv = [sys.argv[0], *sys.argv[2:]]
    main()


async def device():
    from pymobiledevice3.usbmux import list_devices
    from pymobiledevice3.lockdown import create_using_usbmux
    phone = None
    try:
        devices = [d for d in await list_devices() if str(d.connection_type) == 'USB']
        if len(devices) != 1:
            print(json.dumps({'event': 'device_count', 'count': len(devices)}), flush=True)
            return
        phone = await create_using_usbmux(connection_type='USB', autopair=False)
        print(json.dumps({'event': 'device_ready', 'ios': phone.product_version,
                          'model': phone.product_type}), flush=True)
    except Exception as e:
        print(json.dumps({'event': 'device_error', 'type': type(e).__name__}), flush=True)
    finally:
        if phone is not None:
            await phone.close()
