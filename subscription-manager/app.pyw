# -*- coding: utf-8 -*-
"""AGFO Subscription Manager - giris noktasi."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from subscription_app import main  # noqa: E402

if __name__ == '__main__':
    main()
