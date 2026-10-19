# ADR-0008 — CPU-first defaults

Status: accepted. Date: 2026-10-19.

## Context

The brief defaults every neural module to CUDA and float16. Most editors do not
have an NVIDIA GPU, and CI has none. A default that fails on a laptop is a bad
default, and tests that need a GPU do not run.

## Decision

- New projects use `device=cpu`, `compute_type=int8`, `model_size=small`.
- CUDA and float16 are opt-in per project or preset.
- The quality preset may select `large-v3` with a documented CPU-time warning.
- Tests use fakes and synthetic media; no model download is required.
- A GPU is an accelerator, not a prerequisite.

## Consequences

- A clean install can run the suite and a short clip on CPU.
- Transcription is slower. The cache and the `small` model keep it usable.
- The operator manual documents the CUDA install and the expected speedup.
- Presets can override the default without changing the product default.

## Alternatives rejected

- CUDA default with CPU fallback: silent degradation and confusing failures.
- GPU-only: excludes most users and blocks CI.
- `large-v3` default: minutes per minute of audio on CPU.
