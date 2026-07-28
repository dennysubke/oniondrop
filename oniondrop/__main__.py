from __future__ import annotations

import os

from waitress import serve

from .web import create_app


def env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


if __name__ == "__main__":
    serve(
        create_app(),
        host=os.environ.get("ONIONDROP_HOST", "0.0.0.0"),
        port=env_int("ONIONDROP_PORT", 8080, 1, 65535),
        threads=env_int("ONIONDROP_THREADS", 8, 4, 128),
        channel_timeout=300,
    )
