"""Bounded QProcess controller; the GUI never implements the iAP2 protocol."""
import json
import math
import os
import shlex
import signal
import sys
import tempfile
from pathlib import Path
from PySide6.QtCore import QObject, QProcess, QTimer, Signal
from .worker import resources


def validate(lat, lon, duration):
    lat, lon = float(lat), float(lon)
    duration = int(duration)
    if not math.isfinite(lat) or not -90 <= lat <= 90:
        raise ValueError('纬度必须在 -90 至 90 之间')
    if not math.isfinite(lon) or not -180 <= lon <= 180:
        raise ValueError('经度必须在 -180 至 180 之间')
    if not 1 <= duration <= 3600:
        raise ValueError('时长必须在 1 至 3600 秒之间')
    return lat, lon, duration


class State:
    def __init__(self):
        self.identified = self.authenticated = self.subscribed = False
        self.acks = 0
        self.dvt_connected = self.dvt_set = False
        self.map_verified = self.restored = False

    def consume(self, event):
        name = event.get('event')
        if name == 'dvt_tunnel_connected': self.dvt_connected = True
        if name == 'dvt_set_sent': self.dvt_set = True
        if name == 'identification_accepted': self.identified = True
        if name == 'authentication_succeeded': self.authenticated = True
        if name == 'location_requested': self.subscribed = bool(event.get('sentences'))
        if name == 'location_stopped': self.subscribed = False
        if name == 'location_link_acknowledged': self.acks = int(event.get('count', 0))
        # Never promote an ACK or upstream finished event to phone verification.


class Engine(QObject):
    event = Signal(dict)
    ended = Signal()
    def __init__(self):
        super().__init__()
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self.read)
        self.process.readyReadStandardError.connect(lambda: self.process.readAllStandardError())
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(self.failed)
        self.buffer = b''
        self.guard = QTimer(self); self.guard.setSingleShot(True)
        self.guard.timeout.connect(self.stop)
        self.kill_timer = QTimer(self); self.kill_timer.setSingleShot(True)
        self.kill_timer.timeout.connect(self.kill_group)
        # Private launcher has no credentials; retained until app exits.
        self.temp = tempfile.TemporaryDirectory(prefix='ios-location-studio-')
        self.helper = Path(self.temp.name) / 'auth-helper'
        command = self.command('helper')
        self.helper.write_text('#!/bin/sh\nexec ' + shlex.join(command) + '\n')
        self.helper.chmod(0o700)
        self.group = None
        self.process.started.connect(lambda: setattr(self, 'group', int(self.process.processId())))

    def command(self, *args):
        if getattr(sys, 'frozen', False):
            return [sys.executable, '--worker', *args]
        return [sys.executable, '-m', 'location_studio_mac.app', '--worker', *args]

    @property
    def running(self):
        return self.process.state() != QProcess.NotRunning

    def start(self, action, cert='', key='', lat=0, lon=0, duration=20, route='iap2'):
        if self.running: raise ValueError('已有会话运行，请先停止')
        if route not in ('iap2','dvt'): raise ValueError('未知定位路线')
        if action not in ('device', 'probe', 'send','dvt_prepare'): raise ValueError('未知操作')
        if action not in ('device','dvt_prepare'):
            validate(lat, lon, duration)
        if action in ('probe','send') and route=='iap2':
            if not Path(cert).is_file() or not Path(key).is_file():
                raise ValueError('请选择项目目录之外的证书与匹配私钥')
        from PySide6.QtCore import QProcessEnvironment
        env = QProcessEnvironment.systemEnvironment()
        env.insert('ACCESSORY_MFI_CERT_FILE', cert)
        env.insert('ACCESSORY_MFI_KEY_FILE', key)
        self.process.setProcessEnvironment(env)
        # New process group allows cleanup of both worker and authentication helper.
        params = QProcess.UnixProcessParameters()
        params.flags = QProcess.UnixProcessFlag.CreateNewSession
        self.process.setUnixProcessParameters(params)
        dvt = route=='dvt' and action!='device'
        if dvt and action=='send' and duration>180: raise ValueError('DVT 测试最长 180 秒')
        args = [action]
        if action not in ('device','dvt_prepare'):
            args += ['--transport', 'usb', '--auth-helper', str(self.helper), '--duration', str(duration)]
        if action == 'send': args += ['--latitude', str(lat), '--longitude', str(lon)]
        self.buffer = b''
        self.stop_grace=15000 if dvt else 3000
        if action=='dvt_prepare':
            self.process.start(self.command('dvt_prepare','--allow-apple-ticket')[0],self.command('dvt_prepare','--allow-apple-ticket')[1:])
        else:
            profile=resources()/'tools/local-only.sb'
            if dvt:
                args=['dvt_'+action,'--duration',str(duration)]
                if action=='send':args+=['--latitude',str(lat),'--longitude',str(lon)]
                profile=Path(__file__).parent/'assets/dvt-local-only.sb'
            self.process.start('/usr/bin/sandbox-exec', ['-f', str(profile), *self.command(*args)])
        self.guard.start((90 if action=='dvt_prepare' else duration+60 if dvt else duration+30 if action!='device' else 20)*1000)

    def read(self):
        self.buffer += bytes(self.process.readAllStandardOutput())
        while b'\n' in self.buffer:
            line, self.buffer = self.buffer.split(b'\n', 1)
            try:
                event = json.loads(line)
                # Do not expose upstream error detail, which can contain device data.
                if event.get('event') == 'error':
                    event = {'event':'error', 'type':event.get('type','Unknown')}
                self.event.emit(event)
            except (ValueError, TypeError): pass
        if len(self.buffer) > 131072: self.buffer = b''

    def stop(self):
        if not self.running: return
        self.group = int(self.process.processId())
        try: os.killpg(self.group, signal.SIGINT)
        except ProcessLookupError: pass
        self.kill_timer.start(getattr(self,'stop_grace',3000))

    def kill_group(self):
        if self.group:
            try: os.killpg(self.group, signal.SIGKILL)
            except ProcessLookupError: pass
            self.group = None

    def finished(self, code, status):
        self.read(); self.guard.stop()
        # Any orphaned helper from a crashed worker must also be removed.
        self.kill_group()
        self.kill_timer.stop()
        self.event.emit({'event':'process_exit','code':code})
        self.ended.emit()

    def failed(self, error):
        self.event.emit({'event':'process_error','type':str(error)})
        if not self.running:
            self.guard.stop(); self.ended.emit()
