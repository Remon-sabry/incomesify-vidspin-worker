# Incomesify VidSpin — RunPod Serverless FFmpeg worker

CPU-based FFmpeg worker for the VidSpin WordPress plugin. It supports both simple continuous clips and a multi-scene timeline.

## Build and deploy
The Dockerfile runs `rp_handler.py`. GitHub Actions builds and pushes `ghcr.io/remon-sabry/incomesify-vidspin-worker:latest` when the worker source changes. After a successful image build, update/redeploy the RunPod endpoint to pull the new image.

## Simple clip input
```json
{
  "input": {
    "source_url": "HTTPS_SOURCE_VIDEO_URL",
    "upload_url": "ONE_TIME_WORKER_UPLOAD_URL",
    "start": 12.5,
    "duration": 45,
    "width": 1080,
    "height": 1920
  }
}
```

## Multi-scene timeline input
The WordPress plugin creates the source and scene asset URLs, then submits a timeline manifest:
```json
{
  "input": {
    "source_url": "HTTPS_SOURCE_VIDEO_URL",
    "upload_url": "ONE_TIME_WORKER_UPLOAD_URL",
    "timeline": [
      {
        "source_start": 12.5,
        "duration": 8,
        "layout": "center",
        "background_volume": 0.2,
        "broll_url": "OPTIONAL_BROLL_VIDEO_URL",
        "voiceover_url": "OPTIONAL_VOICE_AUDIO_URL",
        "voiceover_seek": 0,
        "ass_url": "OPTIONAL_ASS_CAPTIONS_URL"
      }
    ]
  }
}
```

Each timeline scene can use source footage, optional B-roll, optional narration, and optional ASS captions. Supported layouts are `center`, `fit`, and `split`. The worker renders each scene and concatenates the result into one MP4. It limits jobs to 30 scenes and 180 seconds for the simple clip path; each scene is capped at 40 seconds.

## Security
The worker accepts short-lived source/asset URLs and a one-time output upload URL. Keep the RunPod API key on the WordPress server. Do not place Cloudflare R2 access keys in job payloads or in the worker image.
