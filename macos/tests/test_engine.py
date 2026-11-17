import math
import os
import sys
import time
from pathlib import Path
import pytest
from PySide6.QtWidgets import QApplication
from location_studio_mac.engine import Engine, State, validate

@pytest.fixture(scope='session')
def app():
    return QApplication.instance() or QApplication([])

@pytest.mark.parametrize('args',[(math.nan,0,20),(0,math.inf,20),(91,0,20),(0,-181,20),(0,0,0),(0,0,3601)])
def test_invalid(args):
    with pytest.raises(ValueError): validate(*args)

def test_coordinates():
    assert validate('40.7128','-74.0060',180)==(40.7128,-74.006,180)

def test_ack_is_not_phone_verification():
    state=State()
    for event in ({'event':'identification_accepted'},{'event':'authentication_succeeded'},
                  {'event':'location_requested','sentences':[1,2]},
                  {'event':'location_link_acknowledged','count':50},
                  {'event':'finished','phone_location_verified':True}): state.consume(event)
    assert state.authenticated and state.subscribed and state.acks==50
    assert not state.map_verified and not state.restored
    state.consume({'event':'location_stopped'})
    assert not state.subscribed


def wait(app, predicate, seconds=8):
    end=time.monotonic()+seconds
    while time.monotonic()<end and not predicate():
        app.processEvents(); time.sleep(.01)
    assert predicate()


def test_worker_lifecycle_and_redaction(app,tmp_path):
    worker=tmp_path/'peer.py'
    worker.write_text('import json,time\nprint(json.dumps({"event":"authentication_succeeded"}),flush=True)\nprint(json.dumps({"event":"error","type":"Test","detail":"secret-device-id"}),flush=True)\ntime.sleep(60)\n')
    engine=Engine(); engine.command=lambda *args:[sys.executable,str(worker)]
    events=[]; engine.event.connect(events.append)
    engine.start('device')
    wait(app,lambda:any(x.get('event')=='error' for x in events))
    assert 'secret-device-id' not in str(events)
    with pytest.raises(ValueError): engine.start('device')
    engine.stop(); wait(app,lambda:not engine.running)
    assert any(x.get('event')=='process_exit' for x in events)


def test_gui_offline(app):
    from location_studio_mac.app import Window
    window=Window(); window.city.setCurrentText('东京 · Tokyo')
    assert float(window.lon.text())==139.6503
    assert not window.map_button.isEnabled()
    assert not window.restore.isEnabled()
    window.close()


def test_watchdog_cleans_authentication_child(app,tmp_path):
    pidfile=tmp_path/'child.pid'
    worker=tmp_path/'tree.py'
    worker.write_text('import subprocess,sys,time\nfrom pathlib import Path\np=subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"])\nPath('+repr(str(pidfile))+').write_text(str(p.pid))\ntime.sleep(60)\n')
    engine=Engine();engine.command=lambda *args:[sys.executable,str(worker)]
    engine.start('device');wait(app,pidfile.exists)
    child=int(pidfile.read_text());engine.guard.start(20)
    wait(app,lambda:not engine.running)
    def gone():
        import subprocess
        result=subprocess.run(['ps','-p',str(child),'-o','stat='],capture_output=True,text=True)
        return result.returncode!=0 or result.stdout.strip().startswith('Z')
    wait(app,gone)


def test_ui_coordinate_zoom_and_duration_controls(app):
    from location_studio_mac.app import Window
    w=Window()
    w.quick_buttons[2].click()
    assert float(w.lon.text())==139.6503
    w.duration_buttons[0][0].click()
    assert w.duration.value()==60
    w.duration.setValue(120)
    assert not any(button.isChecked() for button,_ in w.duration_buttons)
    w.lat.setText('invalid');w.update_target()
    assert '坐标无效' in w.target_label.text()
    w.set_coordinates(40.7128,-74.006)
    w.grid.change_zoom(2)
    assert w.grid.zoom==2
    point=w.grid.point(-74.006,40.7128)
    west,north,width,height=w.grid.bounds()
    assert abs(west+point.x()/w.grid.width()*width+74.006)<1e-8
    assert abs(north-point.y()/w.grid.height()*height-40.7128)<1e-8
    w.close()


def test_gui_defaults_to_dvt_without_mfi(app,monkeypatch):
    from location_studio_mac.app import Window
    from PySide6.QtWidgets import QMessageBox
    w=Window();assert w.route.currentData()=='dvt'
    w.cert.clear();w.key.clear();calls=[]
    monkeypatch.setattr(QMessageBox,'question',lambda *a:QMessageBox.Yes)
    monkeypatch.setattr(w.engine,'start',lambda *a,**kw:calls.append((a,kw)))
    w.launch('send')
    assert calls[0][1]['route']=='dvt'
    assert calls[0][0][0]=='send' and w.needs_restore
    w.needs_restore=False;w.close()


def test_dvt_command_uses_loopback_sandbox_without_mfi(app,monkeypatch):
    engine=Engine();calls=[]
    monkeypatch.setattr(engine.process,'start',lambda *a:calls.append(a))
    engine.start('send',lat=40.7128,lon=-74.006,duration=60,route='dvt')
    command=' '.join(str(x) for x in calls[0])
    assert 'dvt-local-only.sb' in command and 'dvt_send' in command
    assert '--auth-helper' not in command
    assert engine.stop_grace>=10000
    engine.guard.stop()
