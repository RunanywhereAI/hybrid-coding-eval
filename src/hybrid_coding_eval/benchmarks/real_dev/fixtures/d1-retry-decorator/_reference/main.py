"""Wire the retry policy onto ``client.fetch_json``.

The decorator is attached at import time. Re-assigning on
``client.fetch_json`` means downstream callers see the wrapped form.
"""

from __future__ import annotations

import client
from retry import retry

client.fetch_json = retry(
    retry_on=(client.HttpServerError,),
    max_attempts=3,
    base_delay=0.1,
)(client.fetch_json)
