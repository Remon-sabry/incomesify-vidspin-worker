# Incomesify VidSpin — Runpod Serverless FFmpeg worker

Initial CPU-based FFmpeg worker scaffold for a Runpod Serverless Queue endpoint.

**Not production-ready or yet connected to the VidSpin WordPress plugin.** It currently accepts one source video URL and one short-lived R2 presigned PUT URL, renders a vertical MP4, and uploads the result. It does not yet support the complete VidSpin timeline, multiple scene assets, separate caption files, voiceover, or full Studio settings.

## Build
Runpod can build this repository from GitHub. The Dockerfile is at the repository root.

## Job input
```json
{
  "input": {
    "source_url": "SHORT_LIVED_SIGNED_GET_URL",
    "upload_url": "SHORT_LIVED_SIGNED_PUT_URL",
    "output_key": "vidspin/user-id/project-id/short-id.mp4",
    "start": 12.5,
    "duration": 45,
    "width": 1080,
    "height": 1920,
    "preset": "veryfast",
    "crf": 23,
    "video_filter": "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1"
  }
}
```

## Initial endpoint
- Queue endpoint
- CPU worker; no GPU required for this initial implementation
- Start with one active worker and zero idle workers
- Keep max workers low until load-tested

## Security
Never put R2 access keys in job payloads or worker environment variables. WordPress should create short-lived, object-specific presigned GET/PUT URLs. Keep the Runpod API key server-side.
