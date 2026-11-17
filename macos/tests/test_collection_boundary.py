from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace


def test_mac_collection_boundary():
    mac = Path(__file__).resolve().parents[1]
    spec = spec_from_file_location('mac_boundary', mac / 'conftest.py')
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    ancestor = SimpleNamespace(rootpath=mac.parent)
    for path in (mac/'tests', mac/'scripts', mac/'vendor'):
        assert module.pytest_ignore_collect(path, ancestor) is True
    assert module.pytest_ignore_collect(mac.parent/'tests', ancestor) is None
    assert module.pytest_ignore_collect(mac/'tests', SimpleNamespace(rootpath=mac)) is None
    assert module.pytest_ignore_collect(mac/'vendor', SimpleNamespace(rootpath=mac/'vendor')) is None
