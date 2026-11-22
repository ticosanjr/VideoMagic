"""Routing failures raised by the standalone compute layer."""

from __future__ import annotations


class WorkerOfflineError(RuntimeError):
    """A remote-only operation could not reach the GPU worker.

    The application layer subclasses this with its typed ``VideoFlowError`` so
    HTTP and MCP callers receive ``code=\"gpu_worker_offline\"`` without making
    ``vf_shared`` depend on ``videoflow``.
    """

    code = "gpu_worker_offline"


__all__ = ["WorkerOfflineError"]
