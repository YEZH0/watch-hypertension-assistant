"""Real QProcess + sandbox, synthetic worker only. No USB or location calls."""
import sys
import threading
import time
from PySide6.QtWidgets import QApplication
from location_studio_mac import bridge
from location_studio_mac.engine import Engine
import pytest


def wait(app, predicate, seconds=8):
    until = time.monotonic()+seconds
    while not predicate() and time.monotonic()<until:
        app.processEvents(); time.sleep(.005)
    assert predicate()


@pytest.mark.parametrize('ending', ['timeout', 'cancel', 'crash', 'watchdog'])
def test_worker_cleanup_and_exit_state(monkeypatch, tmp_path, ending):
    app = QApplication.instance() or QApplication([])
    script = tmp_path/'synthetic.py'
    script.write_text('''import json, signal, time, os
stop = False
def cancel(*_):
    global stop
    stop = True
signal.signal(signal.SIGINT, cancel)
def emit(name): print(json.dumps({'event': name}), flush=True)
emit('dvt_tunnel_connected')
emit('dvt_set_sent')
try:
    end = time.monotonic() + DURATION
    while not stop and time.monotonic() < end: time.sleep(.005)
    CRASH
finally:
    emit('dvt_clear_sent')
    emit('dvt_session_closed')
'''.replace('DURATION', '.15' if ending in ('timeout','crash') else '60').replace('CRASH', 'os._exit(17)' if ending == 'crash' else 'pass'))
    engine = Engine()
    engine.command = lambda *args: [sys.executable, str(script)]
    monkeypatch.setattr(bridge, 'Engine', lambda: engine)
    controller = bridge.Controller()
    events = []; engine.event.connect(events.append)
    call = {'path':'/api/simulate', 'body':{'latitude':40.758,'longitude':-73.9855,'hold_seconds':1}, 'done':threading.Event()}
    controller.safe_dispatch(call)
    wait(app, call['done'].is_set)
    assert call['result'][1]['session']['state'] == 'active'
    if ending == 'cancel':
        stop = {'path':'/api/stop','body':{},'done':threading.Event()}
        controller.safe_dispatch(stop)
    elif ending == 'watchdog':
        engine.guard.start(10)
    wait(app, lambda:not engine.running)
    assert controller.state == ('error' if ending == 'crash' else 'idle')
    if ending == 'crash':
        assert not any(e.get('event') == 'dvt_clear_sent' for e in events)
        assert controller.snapshot()['session']['error']
    else:
        assert any(e.get('event') == 'dvt_clear_sent' for e in events)
    assert '恢复' in controller.snapshot()['session']['message']
    # Engine lifecycle does not promote any event to map/health/restoration evidence.
    assert not any(key in controller.snapshot()['session'] for key in ('map_verified','restored','hypertension_enabled'))


def test_bridge_sigterm_stops_synthetic_worker(tmp_path):
    import json
    import os
    import signal
    import socket
    import subprocess
    import urllib.request
    marker = tmp_path/'synthetic-cleared'
    worker = tmp_path/'worker.py'
    worker.write_text('''import json, signal, time
from pathlib import Path
stop = False
def cancel(*_):
    global stop
    stop = True
signal.signal(signal.SIGINT, cancel)
print(json.dumps({'event':'dvt_set_sent'}),flush=True)
try:
    while not stop: time.sleep(.005)
finally:
    Path(MARKER).write_text('synthetic cleanup only')
    print(json.dumps({'event':'dvt_clear_sent'}),flush=True)
'''.replace('MARKER',repr(str(marker))))
    driver = tmp_path/'driver.py'
    driver.write_text('from location_studio_mac import bridge\nfrom location_studio_mac.engine import Engine\nimport sys\ndef factory():\n    e=Engine()\n    e.command=lambda *a:[sys.executable,'+repr(str(worker))+']\n    return e\nbridge.Engine=factory\nbridge.main()\n')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
    proc = subprocess.Popen([sys.executable,str(driver),'--port',str(port)],
                            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                            start_new_session=True)
    url = f'http://127.0.0.1:{port}'
    try:
        until = time.monotonic()+8
        while True:
            try:
                with urllib.request.urlopen(url+'/api/health',timeout=.2) as r:
                    assert json.load(r)['ok']
                break
            except OSError:
                if time.monotonic()>=until: raise
                time.sleep(.02)
        req = urllib.request.Request(url+'/api/simulate', data=json.dumps(
            {'latitude':40.758,'longitude':-73.9855,'hold_seconds':10}).encode(),
            headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=8) as r:
            assert json.load(r)['session']['state'] == 'active'
        proc.send_signal(signal.SIGTERM)
        assert proc.wait(timeout=8) == 0
        assert marker.exists()
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid,signal.SIGKILL); proc.wait()
