"""Rack module protocol. Engines are not implemented in the scaffold."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from videoflow.application.cache import module_hash, params_from_model


class RackModule:
    """Shared fingerprinting. ``execute`` stays unimplemented until the engine lands."""

    id: str = "base"
    version: str = "0.1.0"
    requires: tuple[str, ...] = ()

    def config_model(self) -> type[BaseModel]:
        raise NotImplementedError(f"{self.id} has no config model")

    def fingerprint(
        self,
        *,
        enabled: bool,
        params: BaseModel | dict[str, Any],
        upstream_hash: str,
        media_fingerprint: str,
        model_artifact_digest: str = "none",
        prompt_template_version: str = "none",
    ) -> str:
        payload = params_from_model(params) if isinstance(params, BaseModel) else dict(params)
        return module_hash(
            module=self.id,
            module_version=self.version,
            enabled=enabled,
            params=payload,
            upstream_hash=upstream_hash,
            media_fingerprint=media_fingerprint,
            model_artifact_digest=model_artifact_digest,
            prompt_template_version=prompt_template_version,
        )

    def execute(self, context: object) -> object:
        raise NotImplementedError(f"{self.id} is specified but not implemented in this scaffold")
