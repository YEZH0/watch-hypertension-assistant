"""GPL-3.0-only. Forward the shared CLI without defining another workflow."""
import subprocess
import sys
from .restoration import RESTORE_HINT


def supports_wizard():
    help_result = subprocess.run(
        [sys.executable, '-m', 'assistant', '--help'],
        capture_output=True, text=True, timeout=10,
    )
    return help_result.returncode == 0 and 'wizard' in help_result.stdout.split()


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    print('Watch Hypertension Assistant — macOS', file=sys.stderr, flush=True)
    print(RESTORE_HINT, file=sys.stderr, flush=True)
    try:
        if not args or 'wizard' in args:
            if not supports_wizard():
                print('公共 wizard/统一阶段契约尚未安装，未发送定位请求。请由 Agent 按 '
                      'agent/macos-install-prompt.md 的 0–8 阶段逐项等待用户确认；'
                      '不得自动跳到 start。', file=sys.stderr)
                return 2
            if not args:
                args = ['wizard']
        return subprocess.call([sys.executable, '-m', 'assistant', *args])
    except (KeyboardInterrupt, Exception) as error:
        # No protocol work here: delegate cleanup to the existing HTTP client.
        print('操作中断；正在请求停止。' + RESTORE_HINT, file=sys.stderr)
        try:
            subprocess.run([sys.executable, '-m', 'assistant', 'stop'],
                           timeout=30, check=False)
        except (Exception, KeyboardInterrupt):
            print('未能确认停止，请关闭桥接并人工核验真实定位。', file=sys.stderr)
        return 130 if isinstance(error, KeyboardInterrupt) else 1


if __name__ == '__main__':
    raise SystemExit(main())
