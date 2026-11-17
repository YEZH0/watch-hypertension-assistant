"""Keep the independent Mac suite out of an ancestor project's pytest run.

Run Mac tests from macos/ with its own locked environment, as macos.yml does.
No Windows/root test settings or dependency requirements are changed here.
"""
from pathlib import Path

MAC_ROOT = Path(__file__).resolve().parent


def pytest_ignore_collect(collection_path, config):
    root = Path(config.rootpath).resolve()
    path = Path(collection_path).resolve()
    ancestor_run = root != MAC_ROOT and MAC_ROOT.is_relative_to(root)
    if ancestor_run and path.is_relative_to(MAC_ROOT):
        return True
    return None
