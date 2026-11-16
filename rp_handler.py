import os
import subprocess
import tempfile
import requests
import runpod

FFMPEG = os.getenv("FFMPEG_BIN", "/usr/bin/ffmpeg")

def handler(job):
    inp = job.get("input") or {}
    source_url, upload_url = inp.get("source_url"), inp.get("upload_url")
    if not source_url or not upload_url:
        return {"status": "FAILED", "error": "source_url and upload_url are required"}
    start = max(0.0, float(inp.get("start", 0)))
    duration = max(1.0, min(180.0, float(inp.get("duration", 45))))
    width = max(360, min(2160, int(inp.get("width", 1080))))
    height = max(640, min(3840, int(inp.get("height", 1920))))
    preset = inp.get("preset", "veryfast")
    if preset not in ("ultrafast", "superfast", "veryfast", "faster", "fast", "medium"):
        preset = "veryfast"
    crf = max(18, min(30, int(inp.get("crf", 23))))
    vf = inp.get("video_filter")
    if vf is not None and (not isinstance(vf, str) or len(vf) > 12000):
        return {"status": "FAILED", "error": "Invalid video_filter"}
    with tempfile.TemporaryDirectory(prefix="vidspin-") as td:
        src, out = os.path.join(td, "source.bin"), os.path.join(td, "render.mp4")
        try:
            with requests.get(source_url, stream=True, timeout=(20, 600)) as resp:
                resp.raise_for_status()
                with open(src, "wb") as f:
                    for chunk in resp.iter_content(1024 * 1024):
                        if chunk: f.write(chunk)
            cmd = [FFMPEG, "-hide_banner", "-y", "-ss", str(start), "-t", str(duration), "-i", src]
            cmd += ["-vf", vf or f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1"]
            cmd += ["-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", out]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
            if proc.returncode or not os.path.exists(out):
                return {"status": "FAILED", "error": proc.stderr[-2500:] or "FFmpeg failed"}
            size = os.path.getsize(out)
            if size < 1024: return {"status": "FAILED", "error": "Rendered MP4 is unexpectedly small"}
            with open(out, "rb") as f:
                put = requests.put(upload_url, data=f, headers={"Content-Type": "video/mp4"}, timeout=(30, 900))
            put.raise_for_status()
            return {"status": "COMPLETED", "bytes": size, "content_type": "video/mp4",
                    "duration": duration, "output_key": inp.get("output_key", "")}
        except requests.RequestException as e:
            return {"status": "FAILED", "error": f"Storage transfer failed: {str(e)[:500]}"}
        except subprocess.TimeoutExpired:
            return {"status": "FAILED", "error": "FFmpeg rendering exceeded the 30-minute worker limit"}
        except Exception as e:
            return {"status": "FAILED", "error": str(e)[:1000]}


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
