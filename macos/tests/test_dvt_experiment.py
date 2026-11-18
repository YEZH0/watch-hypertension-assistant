import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest


def load(name):
    from location_studio_mac import dvt
    return dvt


def test_official_tool_summary_redacts_identifiers():
    module=load('prepare_dvt')
    report=module.summarize(SimpleNamespace(returncode=0,stdout='{"result":{"ddiMetadata":{"ready":true},"deviceIdentifier":"secret"}}'))
    assert report['ddi_metadata_available']
    assert 'secret' not in str(report) and 'deviceIdentifier' not in str(report)


@pytest.mark.parametrize('set_fails',[False,True])
async def test_dvt_always_clears_and_closes(monkeypatch,set_fails):
    module=load('test_dvt');calls=[]
    class Context:
        def __init__(self,*a,**kw): pass
        async def __aenter__(self): calls.append('open');return self
        async def __aexit__(self,*a): calls.append('close')
        async def set(self,*a):
            calls.append('set')
            if set_fails: raise RuntimeError('synthetic')
        async def clear(self): calls.append('clear')
        async def is_image_mounted(self,*args):return True
    class Phone:
        identifier='synthetic'
        async def close(self): calls.append('phone_close')
        async def get_developer_mode_status(self):return True
    async def devices(): return [SimpleNamespace(connection_type='USB')]
    async def phone(**kwargs): return Phone()
    monkeypatch.setattr(module,'list_devices',devices)
    monkeypatch.setattr(module,'create_using_usbmux',phone)
    for name in ('UserspaceRsdTunnel','DvtProvider','LocationSimulation'): monkeypatch.setattr(module,name,Context)
    if set_fails:
        with pytest.raises(RuntimeError): await module.experiment(SimpleNamespace(latitude=1,longitude=2,duration=.01))
    else: await module.experiment(SimpleNamespace(latitude=1,longitude=2,duration=.01))
    assert 'clear' in calls and calls.count('close')==3
