"""GPL-3.0-only. Added 2026-11-17: HTTP adapter over the unchanged Qt Engine."""
import argparse
import json
import platform
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from PySide6.QtCore import QCoreApplication, QObject, Signal, Slot
from .engine import Engine

PRESETS = {(40.758, -73.9855), (22.2819, 114.1588), (48.8584, 2.2945), (35.6595, 139.7005)}
RESTORE = '已结束会话；请在 iPhone 地图检查真实定位。未恢复时拔线、等待 GPS 更新，必要时重启并复查。'


class Controller(QObject):
    request = Signal(object)

    def __init__(self):
        super().__init__()
        self.engine = Engine()
        self.engine.event.connect(self.consume)
        self.engine.ended.connect(self.ended)
        self.request.connect(self.safe_dispatch)
        self.state = 'idle'
        self.message = RESTORE
        self.error = None
        self.target = None
        self.deadline = 0
        self.pending = None
        self.action = None
        self.device_result = None

    def snapshot(self):
        result = {'state': self.state, 'message': self.message, 'error': self.error,
                  'remaining': max(0, self.deadline-time.monotonic()) if self.state == 'active' else 0}
        if self.target:
            result.update(latitude=self.target[0], longitude=self.target[1])
        return {'session': result}

    def reply(self, code, payload):
        if self.pending:
            call, self.pending = self.pending, None
            call['result'] = (code, payload)
            call['done'].set()

    @Slot(object)
    def safe_dispatch(self, call):
        try:
            self.dispatch(call)
        except Exception:
            self.state = "error"
            self.error = "无法启动设备操作；请检查依赖与沙箱。"
            self.reply(503, {"detail": self.error})
            if not call["done"].is_set():
                call["result"] = (503, {"detail": self.error})
                call["done"].set()

    def dispatch(self, call):
        path, body = call['path'], call['body']
        def respond(code, data):
            call['result'] = (code, data)
            call['done'].set()
        if path == '/api/health':
            respond(200, {'ok': True, 'version': '0.1.0'}); return
        if path == '/api/status':
            respond(200, self.snapshot()); return
        if path == '/api/stop':
            if self.engine.running:
                self.reply(409, {'detail': '会话已取消；请检查真实定位。'})
                self.pending = call
                self.action = 'stop'
                self.state = 'stopping'
                self.engine.stop()
            else:
                self.state = 'idle'; self.message = RESTORE
                respond(200, self.snapshot())
            return
        if self.engine.running or self.pending:
            respond(409, {'detail': '已有设备操作，请先停止。'}); return
        if path == '/api/devices':
            self.pending = call; self.action = 'device'; self.device_result = None
            self.engine.start('device', route='dvt'); return
        if path == '/api/simulate':
            try:
                target = (body['latitude'], body['longitude'])
                duration = body.get('hold_seconds')
                if duration is None: duration = 180
                if target not in PRESETS or type(duration) is not int or not 1 <= duration <= 180:
                    raise ValueError
            except (KeyError, TypeError, ValueError):
                respond(400, {'detail': '只允许四个固定地区预设及 1–180 秒测试。'}); return
            self.pending = call; self.action = 'send'; self.target = target
            self.state = 'connecting'; self.error = None
            self.message = '正在连接 DVT；位置模拟不能保证启用高血压通知。'
            self.duration = duration
            self.deadline = time.monotonic()+duration
            self.engine.start('send', route='dvt', lat=target[0], lon=target[1], duration=duration)
            return
        respond(404, {'detail': '未知接口'})

    def consume(self, event):
        name = event.get('event')
        if name == 'device_ready':
            self.device_result = {'connected': True, 'devices': [
                {'udid': 'usb-current', 'name': 'iPhone', 'ios_version': event.get('ios'), 'model': event.get('model')}], 'error': None}
        elif name in ('device_count', 'device_error'):
            self.device_result = {'connected': False, 'devices': [], 'error': '请只连接一部 iPhone，解锁并信任此电脑。'}
        elif name == 'dvt_set_sent':
            if self.state != 'connecting': return
            self.state = 'active'
            self.deadline = time.monotonic()+self.duration
            self.message = 'DVT 定位请求已发送；手机位置及健康 App 功能均需人工核验。'
            self.reply(200, self.snapshot())
        elif name in ('error', 'process_error', 'dvt_clear_error'):
            self.state = 'error'
            self.error = 'DVT 操作失败；检查 USB、开发者模式及开发者镜像，并核验真实定位。'
            self.message = RESTORE
            self.reply(409 if event.get('type') == 'RequireExactlyOneUSBDevice' else 503, {'detail': self.error})

    def ended(self):
        if self.state != 'error':
            self.state = 'idle'; self.message = RESTORE
        if self.pending:
            if self.action == 'device' and self.state != 'stopping':
                self.reply(200, self.device_result or {'connected': False, 'devices': [], 'error': '未能识别 iPhone。'})
            else:
                self.reply(200 if self.state == 'idle' else 503, self.snapshot())
        self.action = None


def handler_for(controller):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # No request bodies, device identifiers or raw worker logs.

        def handle_request(self):
            if self.headers.get('Host') not in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'):
                self.send_json(403, {'detail': '无效本机地址'}); return
            if self.headers.get('Origin') or self.headers.get('Sec-Fetch-Site') in ('cross-site', 'same-site'):
                self.send_json(403, {'detail': '仅允许本机助手客户端。'}); return
            allowed = {'GET': {'/api/health', '/api/status', '/api/devices'},
                       'POST': {'/api/simulate', '/api/stop'}}
            if self.path not in allowed.get(self.command, set()):
                self.send_json(404, {'detail': '未知接口'}); return
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 <= size <= 2048: raise ValueError
                body = json.loads(self.rfile.read(size)) if size else {}
                if not isinstance(body, dict): raise ValueError
            except (ValueError, UnicodeError):
                self.send_json(400, {'detail': '无效请求'}); return
            call = {'path': self.path, 'body': body, 'done': threading.Event()}
            controller.request.emit(call)
            if not call['done'].wait(50):
                # Stop timed-out work rather than leave a location session unattended.
                controller.request.emit({'path': '/api/stop', 'body': {}, 'done': threading.Event()})
                self.send_json(504, {'detail': '操作超时，已请求停止；请检查真实定位。'}); return
            self.send_json(*call['result'])

        def send_json(self, code, payload):
            raw = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            try: self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError): pass

        do_GET = handle_request
        do_POST = handle_request
    return Handler


def main():
    parser = argparse.ArgumentParser(description='Watch Hypertension Assistant — GPL-3.0-only，无担保，许可证见 macos/LICENSE')
    parser.add_argument('--host', choices=['127.0.0.1'], default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8900)
    args = parser.parse_args()
    if platform.system() != 'Darwin': parser.error('仅支持 macOS')
    app = QCoreApplication([])
    controller = Controller()
    server = ThreadingHTTPServer((args.host, args.port), handler_for(controller))
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    from PySide6.QtCore import QTimer
    timer = QTimer(); timer.timeout.connect(lambda: None); timer.start(200)
    def shutdown(*_):
        server.shutdown()
        controller.engine.ended.connect(app.quit)
        if controller.engine.running: controller.engine.stop()
        else: app.quit()
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    app.exec()
    server.server_close()


if __name__ == '__main__':
    main()
