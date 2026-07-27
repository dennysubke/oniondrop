import os
from waitress import serve
from .web import create_app

app = create_app()
serve(
    app,
    host=os.environ.get("ONIONDROP_HOST", "0.0.0.0"),
    port=int(os.environ.get("ONIONDROP_PORT", "8080")),
    threads=int(os.environ.get("ONIONDROP_THREADS", "8")),
)
