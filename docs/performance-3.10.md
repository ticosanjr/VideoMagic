# Performance profile (3.10)

## Worker lanes

The worker now separates:

- one exclusive GPU lane: ASR, forced alignment, matte, face tracking, NVENC,
  Short render;
- a bounded CPU pool: scene analysis, blur audit, acoustic events;
- upload/download and artifact I/O remain in FastAPI request threads.

CPU capabilities no longer reserve VRAM. A scene analysis can run while the GPU
is busy with a render, without competing for the GPU lane.

## Job metrics

`/api/overview` exposes `runner.metrics()` with CPU worker count, current jobs,
recent jobs, queue wait, elapsed time, status, and errors. `/health` exposes
uptime, current job, last request, encoder, NVENC error, and LAN URLs.

## Inputs and artifacts

- Input artifacts are hardlinked into the job directory when the filesystem
  allows, falling back to copy.
- Artifacts are content-addressed and deduplicated by SHA-256.
- Shared mount remains the preferred transport for large files; HTTP resumable
  upload is the fallback.

## NVENC

- Final encode: `h264_nvenc`, p5, VBR CQ 19, spatial/temporal AQ, lookahead 20.
- Micro-clips use NVENC p4/CQ20 when the worker reports NVENC; otherwise
  libx264 in the local fallback.
- The client chooses NVENC only from worker health, never on assumption.
- NVENC error text is exposed in health and the dashboard.

## ASR and CPU

- faster-whisper model stays resident.
- `VF_GPU_ASR_CPU_THREADS` and `VF_GPU_ASR_NUM_WORKERS` tune CPU work.
- `VF_GPU_CPU_WORKERS` bounds parallel CPU capabilities.

## Windows

Install/repair now:

- sets the high-performance power plan;
- adds Defender exclusions for the worker root, venv, and logs when admin;
- configures firewall for all profiles;
- enables discovery and LAN-open mode;
- records `VF_GPU_LOG_FILE` and `VF_GPU_CPU_WORKERS`.

## Targets

- scene detection: <=45 s per source hour;
- Short 60 s on RTX 3060: <=20 s;
- queue wait: <10 s;
- unexpected local fallback: 0 when the worker is healthy.

Physical RTX numbers must be confirmed on the Windows machine; local CI is not a
GPU speed certification.
