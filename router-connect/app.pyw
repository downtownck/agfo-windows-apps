# -*- coding: utf-8 -*-
"""AGFO Router Connect - giris noktasi."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if '--selftest' in sys.argv:
    from router_selftest import run
    sys.exit(run(sys.argv))

from router_app import main  # noqa: E402

if __name__ == '__main__':
    main()
