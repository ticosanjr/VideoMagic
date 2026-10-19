"""``videoflow-api`` — loopback FastAPI plus the MCP HTTP mount."""

from __future__ import annotations

import uvicorn

from videoflow.domain.constants import DEFAULT_API_HOST, DEFAULT_API_PORT


def main() -> None:
    uvicorn.run(
        "videoflow.api.app:create_http_app",
        factory=True,
        host=DEFAULT_API_HOST,
        port=DEFAULT_API_PORT,
    )


if __name__ == "__main__":
    main()
