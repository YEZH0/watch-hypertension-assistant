"""GPL-3.0-only. Mac launcher: show recovery guidance, delegate to public CLI."""
import subprocess
import sys
from .restoration import RESTORE_HINT


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    # stderr keeps the delegated CLI's --json stdout machine-readable.
    print('Watch Hypertension Assistant — macOS', file=sys.stderr, flush=True)
    print(RESTORE_HINT, file=sys.stderr, flush=True)
    return subprocess.call([sys.executable, '-m', 'assistant', *args])


if __name__ == '__main__':
    raise SystemExit(main())
