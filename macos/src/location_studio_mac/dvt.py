"""Opt-in DVT location experiment. Requires an already mounted developer image."""
import argparse
import asyncio
import json
import logging
import signal
import shutil
from pymobiledevice3.usbmux import list_devices
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.remote.userspace_tunnel import UserspaceRsdTunnel
from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation

def emit(event,**fields): print(json.dumps({'event':event,**fields}),flush=True)

async def experiment(args):
    devices=[d for d in await list_devices() if str(d.connection_type)=='USB']
    if len(devices)!=1: raise ValueError('RequireExactlyOneUSBDevice')
    phone=await create_using_usbmux(connection_type='USB',autopair=False)
    try:
        serial=phone.identifier
        if not await phone.get_developer_mode_status(): raise ValueError('DeveloperModeRequired')
    finally: await phone.close()
    stop=asyncio.Event();loop=asyncio.get_running_loop()
    for sig in (signal.SIGINT,signal.SIGTERM): loop.add_signal_handler(sig,stop.set)
    async with UserspaceRsdTunnel(serial=serial,autopair=False) as rsd:
        emit('dvt_tunnel_connected')
        async with DvtProvider(rsd) as dvt:
            if stop.is_set():
                emit('dvt_cancelled_before_set');return
            if getattr(args,'probe',False):
                emit('dvt_probe_succeeded');return
            async with LocationSimulation(dvt) as simulation:
                try:
                    await simulation.set(args.latitude,args.longitude)
                    emit('dvt_set_sent',phone_location_verified=False)
                    try: await asyncio.wait_for(stop.wait(),args.duration)
                    except TimeoutError: pass
                finally:
                    try:
                        await asyncio.wait_for(simulation.clear(),10)
                        emit('dvt_clear_sent',phone_restoration_verified=False)
                    except Exception as e:
                        emit('dvt_clear_error',type=type(e).__name__)
    emit('dvt_session_closed')


def summarize(result):
    # Never include deviceIdentifier, ECID, ticket or raw tool logs.
    try:
        data=json.loads(result.stdout)
        return {'event':'developer_image_preparation','exit_code':result.returncode,
                'ddi_metadata_available':bool(data.get('result',{}).get('ddiMetadata')),
                'error_code':data.get('error',{}).get('code')}
    except (ValueError,TypeError):
        return {'event':'developer_image_preparation','exit_code':result.returncode,
                'ddi_metadata_available':False}


async def prepare():
    devices=[d for d in await list_devices() if str(d.connection_type)=='USB']
    if len(devices)!=1: raise ValueError('RequireExactlyOneUSBDevice')
    if not shutil.which('xcrun'): raise ValueError('XcodeRequired')
    phone=await create_using_usbmux(connection_type='USB',autopair=False)
    try:
        serial=phone.identifier
        if not await phone.get_developer_mode_status():
            raise ValueError('DeveloperModeRequired')
    finally:
        await phone.close()
    proc=await asyncio.create_subprocess_exec('xcrun','devicectl','device','info','ddiServices',
        '--device',serial,'--auto-mount-ddis','--timeout','60','--json-output','-',
        stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    try:
        stdout,stderr=await asyncio.wait_for(proc.communicate(),75)
    except BaseException:
        if proc.returncode is None:
            proc.terminate();await proc.wait()
        raise
    from types import SimpleNamespace
    report=summarize(SimpleNamespace(returncode=proc.returncode,stdout=stdout))
    print(json.dumps(report),flush=True)
    return proc.returncode



def main(action,argv):
    parser=argparse.ArgumentParser()
    if action=='dvt_prepare': parser.add_argument('--allow-apple-ticket',action='store_true',required=True)
    else:
        parser.add_argument('--duration',type=int,default=20)
        parser.add_argument('--latitude',type=float,default=0)
        parser.add_argument('--longitude',type=float,default=0)
    args=parser.parse_args(argv)
    logging.disable(logging.CRITICAL)
    try:
        if action=='dvt_prepare': raise SystemExit(asyncio.run(prepare()))
        from .engine import validate
        validate(args.latitude,args.longitude,args.duration)
        if args.duration>180: raise ValueError('DVTDurationTooLong')
        args.probe=action=='dvt_probe'
        asyncio.run(asyncio.wait_for(experiment(args),args.duration+60))
    except Exception as e:
        kind=str(e) if isinstance(e,ValueError) and str(e) in ('DeveloperModeRequired','DVTImageRequired','RequireExactlyOneUSBDevice','XcodeRequired') else 'DVTImageRequired' if type(e).__name__ in ('InvalidServiceError','InvalidService') else type(e).__name__
        emit('error',type=kind);raise SystemExit(1)
