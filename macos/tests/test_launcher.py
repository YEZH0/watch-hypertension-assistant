from location_studio_mac import assistant


def test_recovery_hint_is_visible_and_json_stdout_preserved(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(assistant.subprocess, 'call', lambda args: calls.append(args) or 0)
    assert assistant.main(['stop', '--json']) == 0
    output = capsys.readouterr()
    assert output.out == ''
    assert '定位服务' in output.err and '10 秒' in output.err
    assert '关闭' in output.err and '重新开启' in output.err
    assert calls[0][1:] == ['-m', 'assistant', 'stop', '--json']


def test_missing_shared_wizard_does_not_start(monkeypatch, capsys):
    from types import SimpleNamespace
    monkeypatch.setattr(assistant.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=0, stdout='env start stop'))
    monkeypatch.setattr(assistant.subprocess, 'call', lambda *a, **k: (_ for _ in ()).throw(AssertionError('must not start')))
    assert assistant.main(['wizard']) == 2
    assert '不得自动跳到 start' in capsys.readouterr().err


def test_shared_wizard_delegates_unchanged(monkeypatch):
    from types import SimpleNamespace
    calls = []
    monkeypatch.setattr(assistant.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=0, stdout='  wizard  引导流程\n'))
    monkeypatch.setattr(assistant.subprocess, 'call', lambda args: calls.append(args) or 0)
    assert assistant.main(['--engine-url', 'http://127.0.0.1:8900', 'wizard']) == 0
    assert calls[0][1:] == ['-m', 'assistant', '--engine-url', 'http://127.0.0.1:8900', 'wizard']


def test_interrupt_requests_stop_and_does_not_claim_restoration(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(assistant.subprocess, 'call', lambda *a: (_ for _ in ()).throw(KeyboardInterrupt()))
    monkeypatch.setattr(assistant.subprocess, 'run', lambda args, **kw: calls.append(args))
    assert assistant.main(['start', '--region', 'us']) == 130
    assert calls[0][-1] == 'stop'
    assert 'idle 不等于 GPS 已恢复' in capsys.readouterr().err
