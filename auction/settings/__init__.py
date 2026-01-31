from __future__ import absolute_import

import os
from dotenv import load_dotenv

# .env file load
load_dotenv()

env = os.getenv("DJANGO_SETTINGS", "dev")


if env.endswith("dev"):
    from .dev import *
else:
    from .prod import *
