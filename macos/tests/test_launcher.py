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
