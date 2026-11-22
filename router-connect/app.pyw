# -*- coding: utf-8 -*-
"""AGFO Router Connect - giris noktasi."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if len(sys.argv) >= 3 and sys.argv[1] == '--apply-update':
    from router_update import apply_update_main
    _pid = 0
    if '--wait-pid' in sys.argv:
        try:
            _pid = int(sys.argv[sys.argv.index('--wait-pid') + 1])
        except (ValueError, IndexError):
            _pid = 0
    sys.exit(apply_update_main(sys.argv[2], _pid, '--minimized' in sys.argv))

if '--selftest' in sys.argv:
    from router_selftest import run
    sys.exit(run(sys.argv))

from router_app import main  # noqa: E402

if __name__ == '__main__':
    main()
