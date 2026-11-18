from location_studio_mac import doctor


def test_non_macos_does_not_report_ready(monkeypatch):
    monkeypatch.setattr(doctor.platform, 'system', lambda:'Linux')
    monkeypatch.setattr(doctor.shutil, 'which', lambda name:None)
    result = doctor.inspect_environment()
    assert not result['ready']
    assert result['device_authorization'] == 'unknown_pending_user_verification'
    assert 'serial' not in str(result)
