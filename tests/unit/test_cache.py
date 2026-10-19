import inspect
from decimal import Decimal
from enum import Enum

import pytest
from pydantic import BaseModel

from videoflow.application.cache import canonicalize, module_hash, params_from_model
from videoflow.domain.config import ZoomsConfig


class _Color(Enum):
    RED = "red"


class _Params(BaseModel):
    scale: float
    mode: str


def test_hash_ignores_key_order_and_quantizes_floats() -> None:
    left = module_hash(
        module="zooms",
        module_version="0.1.0",
        enabled=True,
        params={"scale": 1.15, "mode": "alternate_cuts"},
        upstream_hash="abc",
        media_fingerprint="pcm",
    )
    right = module_hash(
        module="zooms",
        module_version="0.1.0",
        enabled=True,
        params={"mode": "alternate_cuts", "scale": 1.1500000004},
        upstream_hash="abc",
        media_fingerprint="pcm",
    )
    assert left == right
    assert "mtime" not in inspect.signature(module_hash).parameters


def test_identity_changes_when_a_hash_input_changes() -> None:
    base = dict(
        module="zooms",
        module_version="0.1.0",
        enabled=True,
        params={"scale": 1.15},
        upstream_hash="abc",
        media_fingerprint="pcm",
        model_artifact_digest="none",
        prompt_template_version="none",
    )
    original = module_hash(**base)
    assert module_hash(**{**base, "enabled": False}) != original
    assert module_hash(**{**base, "module_version": "0.2.0"}) != original
    assert module_hash(**{**base, "upstream_hash": "def"}) != original
    assert module_hash(**{**base, "model_artifact_digest": "whisper"}) != original
    assert module_hash(**{**base, "prompt_template_version": "retake-v2"}) != original


def test_canonicalize_types() -> None:
    assert canonicalize(True) is True
    assert canonicalize(1) == 1
    assert canonicalize(None) is None
    assert canonicalize("pt") == "pt"
    assert canonicalize(_Color.RED) == "red"
    assert canonicalize(Decimal("-0.0000001")) == "0.000000"
    assert canonicalize(-0.0) == "0.000000"
    assert canonicalize([1, {"b": 1, "a": 2}]) == [1, {"a": 2, "b": 1}]
    with pytest.raises(ValueError):
        canonicalize(float("nan"))
    with pytest.raises(TypeError):
        canonicalize({1: "nope"})
    with pytest.raises(TypeError):
        canonicalize(object())


def test_params_from_model_round_trip_into_the_hash() -> None:
    dumped = params_from_model(ZoomsConfig())
    assert dumped["punch_in_scale"] == 1.15
    direct = module_hash(
        module="zooms",
        module_version="0.1.0",
        enabled=True,
        params=dumped,
        upstream_hash="up",
        media_fingerprint="media",
    )
    wrapped = module_hash(
        module="zooms",
        module_version="0.1.0",
        enabled=True,
        params=params_from_model(_Params(scale=1.15, mode="alternate_cuts")),
        upstream_hash="up",
        media_fingerprint="media",
    )
    assert direct != wrapped
