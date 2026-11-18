"""Tests use a fake engine; never send coordinates to a real device."""
import json
import threading
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication
from location_studio_mac import bridge


class FakeEngine(QObject):
    event = Signal(dict)
    ended = Signal()
    def __init__(self):
        super().__init__(); self.running = False; self.calls = []
    def start(self, action, **kwargs):
        self.running = True; self.calls.append((action, kwargs))
    def stop(self):
        self.running = False; self.ended.emit()


@pytest.fixture
def controller(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(bridge, 'Engine', FakeEngine)
    result = bridge.Controller()
    result._app = app
    return result


def call(c, path, body=None):
    request = {'path': path, 'body': body or {}, 'done': threading.Event()}
    c.safe_dispatch(request)
    return request


def test_fixed_presets_and_duration(controller):
    for target in bridge.PRESETS:
        request = call(controller, '/api/simulate', dict(latitude=target[0], longitude=target[1], hold_seconds=30))
        assert controller.state == 'connecting'
        controller.consume({'event': 'dvt_set_sent'})
        assert request['result'][1]['session']['state'] == 'active'
        assert controller.engine.calls[-1][1]['route'] == 'dvt'
        stopped = call(controller, '/api/stop')
        assert stopped['result'][1]['session']['state'] == 'idle'
    for body in ({'latitude': 40.758, 'longitude': -73.9855, 'hold_seconds': 0}, {'latitude': 0, 'longitude': 0}, {'latitude': 40.758, 'longitude': -73.9855, 'hold_seconds': 181}):
        assert call(controller, '/api/simulate', body)['result'][0] == 400


def test_no_device_and_redaction(controller):
    req = call(controller, '/api/simulate', {'latitude':22.2819, 'longitude':114.1588})
    controller.consume({'event':'error','type':'RequireExactlyOneUSBDevice','detail':'secret-udid'})
    assert req['result'][0] == 409
    assert 'secret' not in json.dumps(req['result'])
    controller.engine.running = False
    devices = call(controller, '/api/devices')
    controller.consume({'event':'device_ready','ios':'26.1','model':'iPhone17,3','udid':'secret'})
    assert not devices['done'].is_set()
    controller.engine.running = False
    controller.ended()
    assert devices['result'][1]['devices'][0]['udid'] == 'usb-current'
    assert 'secret' not in json.dumps(devices['result'])


def test_failure_and_stop_during_connect(controller):
    pending = call(controller, '/api/simulate', {'latitude':22.2819, 'longitude':114.1588})
    stopped = call(controller, '/api/stop')
    assert pending['result'][0] == 409
    assert stopped['result'][1]['session']['state'] == 'idle'
    assert '恢复' in stopped['result'][1]['session']['message']


def test_http_health_and_origin(controller):
    server = ThreadingHTTPServer(('127.0.0.1', 0), bridge.handler_for(controller))
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    results = []
    def client():
        url = f'http://127.0.0.1:{server.server_port}/api/health'
        with urllib.request.urlopen(url) as response:
            results.append(json.load(response))
        try:
            urllib.request.urlopen(urllib.request.Request(url, headers={'Origin':'https://example.com'}))
        except urllib.error.HTTPError as error:
            results.append(error.code)
    worker = threading.Thread(target=client); worker.start()
    import time
    until = time.monotonic()+5
    while worker.is_alive() and time.monotonic()<until:
        controller._app.processEvents(); time.sleep(.005)
    worker.join(1)
    server.shutdown(); server.server_close()
    assert results == [{'ok':True, 'version':'0.1.0'},403]
