"""Command-line entry point for the GPU worker."""

from __future__ import annotations

import sys

import uvicorn

from gpu_worker.app import create_app
from gpu_worker.settings import Settings


def main() -> None:
    """Start uvicorn with settings loaded from the environment."""

    settings = Settings.from_env()
    if not settings.token:
        print(
            "warning: VF_GPU_TOKEN is not set; every non-health endpoint will return 503",
            file=sys.stderr,
        )
    app = create_app(settings)
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
