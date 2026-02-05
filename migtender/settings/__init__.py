from __future__ import absolute_import

import os
import sys

from dotenv import load_dotenv

# .env file load
load_dotenv()

env = os.getenv("DJANGO_SETTINGS", "dev")

# Detect test runs (manage.py test, pytest, etc.)
is_tests = (
    "test" in sys.argv or "PYTEST_CURRENT_TEST" in os.environ or env.endswith("test")
)

if is_tests:
    from .test import *  # noqa
elif env.endswith("prod"):
    from .prod import *  # noqa
else:
    from .dev import *  # noqa
