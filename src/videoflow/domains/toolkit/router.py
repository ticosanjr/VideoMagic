"""Thin adapter around `vf_shared.compute.ComputeRouter` with health-based fallback."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from .errors import RemoteResultError, RemoteUnavailableError


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, dict):
        for key in ("ok", "available", "healthy", "enabled"):
            if key in value:
                return bool(value[key])
        status = str(value.get("status", "")).lower()
        return status in {"ok", "ready", "healthy", "available"}
    if isinstance(value, str):
        return value.lower() in {"ok", "ready", "healthy", "available", "true"}
    return bool(value)


def _remote_decision(decision: Any) -> bool:
    if isinstance(decision, dict):
        mode = decision.get("mode") or decision.get("placement")
        if mode is not None:
            return str(mode).lower() == "remote"
        return _truthy(decision)
    mode = getattr(decision, "mode", None)
    if mode is not None:
        return str(mode).lower() == "remote"
    return _truthy(decision)


class RouterBridge:
    """Normalize the small part of the compute router these tools need."""

    def __init__(self, router: object | None = None) -> None:
        self._router = router
        self._loaded = router is not None

    def _resolve(self) -> object | None:
        if self._loaded:
            return self._router
        self._loaded = True
        try:
            from vf_shared.compute import ComputeRouter
        except Exception:
            self._router = None
            return None
        try:
            self._router = ComputeRouter.from_env()
        except Exception:
            self._router = None
        return self._router

    def health(self, capability: str) -> bool:
        """Return whether the router would place this capability remotely."""

        router = self._resolve()
        if router is None:
            return False

        decide = getattr(router, "decide", None)
        if callable(decide):
            try:
                return _remote_decision(decide(capability))
            except Exception:
                return False

        for attribute in ("health", "available", "supports", "can"):
            probe = getattr(router, attribute, None)
            if not callable(probe):
                continue
            try:
                return _truthy(probe(capability))
            except TypeError:
                try:
                    return _truthy(probe())
                except Exception:
                    return False
            except Exception:
                return False
        return False

    def submit(self, capability: str, payload: dict[str, Any]) -> Any:
        """Submit a capability job and return a path, bytes, or router result."""

        router = self._resolve()
        if router is None:
            raise RemoteUnavailableError(
                f"no compute router is available for capability {capability!r}",
                details={"capability": capability},
            )
        for attribute in ("submit", "run", "execute", "dispatch"):
            submit = getattr(router, attribute, None)
            if not callable(submit):
                continue
            try:
                return submit(capability, payload)
            except TypeError:
                try:
                    return submit(capability=capability, payload=payload)
                except TypeError as exc:
                    raise RemoteUnavailableError(
                        f"compute router cannot submit capability {capability!r}",
                        details={"capability": capability},
                    ) from exc
        return self._submit_via_client(router, capability, payload)

    def _submit_via_client(
        self,
        router: object,
        capability: str,
        payload: dict[str, Any],
    ) -> dict[str, str]:
        try:
            client = router.client  # type: ignore[attr-defined]
        except Exception as exc:
            raise RemoteUnavailableError(
                f"compute router has no client for capability {capability!r}",
                details={"capability": capability},
            ) from exc

        try:
            job_id = client.submit(capability, params=payload)
            status = client.wait(job_id)
        except Exception as exc:
            raise RemoteUnavailableError(
                f"remote capability {capability!r} failed: {exc}",
                details={"capability": capability},
            ) from exc

        if not getattr(status, "ok", False):
            raise RemoteUnavailableError(
                f"remote capability {capability!r} job {job_id} did not succeed",
                details={
                    "capability": capability,
                    "job_id": job_id,
                    "state": str(getattr(status, "state", "")),
                    "error": str(getattr(status, "error", "") or ""),
                },
            )

        artifacts = [str(item) for item in getattr(status, "artifacts", []) or []]
        if not artifacts:
            raise RemoteResultError(
                f"remote capability {capability!r} returned no artifacts",
                details={"capability": capability, "job_id": job_id},
            )
        target = Path(tempfile.mkdtemp(prefix="vf-remote-")) / Path(artifacts[0]).name
        try:
            client.download(job_id, artifacts[0], target)
        except Exception as exc:
            raise RemoteUnavailableError(
                f"remote artifact download failed for {capability!r}: {exc}",
                details={"capability": capability, "job_id": job_id},
            ) from exc
        return {"path": str(target), "job_id": job_id}
