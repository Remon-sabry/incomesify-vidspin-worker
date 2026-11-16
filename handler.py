import os
import subprocess
import tempfile
import requests
import runpod
from urllib.parse import urlparse

FFMPEG = os.getenv("FFMPEG_BIN", "/usr/bin/ffmpeg")
PRESETS = ("ultrafast", "superfast", "veryfast", "faster", "fast", "medium")


def download(url, path, max_bytes=2_000_000_000):
    if not isinstance(url, str) or not url.startswith(("https://", "http://")):
        raise ValueError("Asset URL must be HTTP or HTTPS")
    total = 0
    with requests.get(url, stream=True, timeout=(20, 900)) as resp:
        resp.raise_for_status()
        with open(path, "wb") as f:
            for chunk in resp.iter_content(1024 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError("Downloaded asset exceeds the worker size limit")
                f.write(chunk)
    if total < 100:
        raise ValueError("Downloaded asset is empty")
    return total


def run_ffmpeg(args, timeout=1800):
    proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if proc.returncode:
        raise RuntimeError((proc.stderr or "FFmpeg failed")[-3500:])


def safe_ass_filter(path):
    # The generated ASS file is local to the isolated worker directory.
    return "ass='" + path.replace("\\", "/").replace(":", r"\\:").replace("'", r"\\'") + "'"


def render_timeline(inp, td, source, out):
    scenes = inp.get("timeline")
    if not isinstance(scenes, list) or not scenes or len(scenes) > 30:
        raise ValueError("timeline must contain between 1 and 30 scenes")
    preset = inp.get("preset", "veryfast")
    if preset not in PRESETS:
        preset = "veryfast"
    crf = max(18, min(30, int(inp.get("crf", 23))))
    scene_files = []
    total_duration = 0.0

    for idx, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            raise ValueError("Each timeline scene must be an object")
        duration = max(0.8, min(40.0, float(scene.get("duration", 4))))
        start = max(0.0, float(scene.get("source_start", 0)))
        mode = scene.get("layout", "center")
        if mode not in ("center", "fit", "split"):
            mode = "center"
        bg_volume = max(0.0, min(1.0, float(scene.get("background_volume", 0.22))))
        args = [FFMPEG, "-hide_banner", "-y", "-ss", str(start), "-t", str(duration), "-i", source]
        input_index = 1
        broll_index = None
        voice_index = None

        broll_url = scene.get("broll_url")
        if broll_url:
            broll_path = os.path.join(td, f"broll-{idx}.mp4")
            download(broll_url, broll_path, 800_000_000)
            args += ["-stream_loop", "-1", "-t", str(duration), "-i", broll_path]
            broll_index = input_index
            input_index += 1

        voice_url = scene.get("voiceover_url")
        if voice_url:
            voice_path = os.path.join(td, f"voice-{idx}.audio")
            download(voice_url, voice_path, 100_000_000)
            voice_seek = max(0.0, float(scene.get("voiceover_seek", 0)))
            if voice_seek:
                args += ["-ss", str(voice_seek)]
            args += ["-i", voice_path]
            voice_index = input_index
            input_index += 1

        video_index = broll_index if broll_index is not None else 0
        if mode == "fit" and broll_index is None:
            vf = (
                f"[{video_index}:v]split=2[bg{idx}][fg{idx}];"
                f"[bg{idx}]scale=1080:1920:force_original_aspect_ratio=increase,"
                f"crop=1080:1920,boxblur=40:6,eq=brightness=-0.1[blur{idx}];"
                f"[fg{idx}]scale=1080:-2[front{idx}];"
                f"[blur{idx}][front{idx}]overlay=(W-w)/2:(H-h)/2,fps=30"
            )
        elif mode == "split" and broll_index is None:
            vf = (
                f"[{video_index}:v]split=2[topin{idx}][botin{idx}];"
                f"[topin{idx}]scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960[top{idx}];"
                f"[botin{idx}]scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960[bot{idx}];"
                f"[top{idx}][bot{idx}]vstack=inputs=2,fps=30"
            )
        else:
            vf = f"[{video_index}:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30"

        ass_url = scene.get("ass_url")
        if ass_url:
            ass_path = os.path.join(td, f"captions-{idx}.ass")
            download(ass_url, ass_path, 5_000_000)
            vf += "," + safe_ass_filter(ass_path)
        vf += f"[v{idx}]"

        audio_fmt = "aformat=sample_rates=44100:channel_layouts=stereo"
        if voice_index is not None:
            af = (
                f"[0:a]{audio_fmt},volume={bg_volume},apad[bg{idx}];"
                f"[{voice_index}:a]{audio_fmt},apad[vo{idx}];"
                f"[bg{idx}][vo{idx}]amix=inputs=2:duration=longest:normalize=0,"
                f"atrim=duration={duration}[a{idx}]"
            )
        else:
            af = f"[0:a]{audio_fmt},apad,atrim=duration={duration}[a{idx}]"

        scene_out = os.path.join(td, f"scene-{idx:02d}.mp4")
        args += [
            "-filter_complex", vf + ";" + af,
            "-map", f"[v{idx}]", "-map", f"[a{idx}]",
            "-t", str(duration), "-r", "30",
            "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
            "-ar", "44100", "-ac", "2", scene_out
        ]
        run_ffmpeg(args, 1800)
        scene_files.append(scene_out)
        total_duration += duration

    concat_list = os.path.join(td, "concat.txt")
    with open(concat_list, "w", encoding="utf-8") as f:
        for path in scene_files:
            f.write("file '" + path.replace("'", "'\\''") + "'\n")
    run_ffmpeg([
        FFMPEG, "-hide_banner", "-y", "-f", "concat", "-safe", "0",
        "-i", concat_list, "-c", "copy", "-movflags", "+faststart", out
    ], 1800)
    return total_duration, len(scene_files)


def handler(job):
    inp = job.get("input") or {}
    source_url, upload_url = inp.get("source_url"), inp.get("upload_url")
    if not source_url or not upload_url:
        return {"status": "FAILED", "error": "source_url and upload_url are required"}
    try:
        with tempfile.TemporaryDirectory(prefix="vidspin-") as td:
            src = os.path.join(td, "source.bin")
            out = os.path.join(td, "render.mp4")
            download(source_url, src)
            if inp.get("timeline"):
                duration, scene_count = render_timeline(inp, td, src, out)
                render_mode = "timeline"
            else:
                start = max(0.0, float(inp.get("start", 0)))
                duration = max(1.0, min(180.0, float(inp.get("duration", 45))))
                width = max(360, min(2160, int(inp.get("width", 1080))))
                height = max(640, min(3840, int(inp.get("height", 1920))))
                preset = inp.get("preset", "veryfast")
                if preset not in PRESETS:
                    preset = "veryfast"
                crf = max(18, min(30, int(inp.get("crf", 23))))
                vf = inp.get("video_filter")
                if vf is not None and (not isinstance(vf, str) or len(vf) > 12000):
                    return {"status": "FAILED", "error": "Invalid video_filter"}
                cmd = [FFMPEG, "-hide_banner", "-y", "-ss", str(start), "-t", str(duration), "-i", src]
                cmd += ["-vf", vf or f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1"]
                cmd += ["-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", out]
                run_ffmpeg(cmd, 1800)
                scene_count = 1
                render_mode = "clip"

            size = os.path.getsize(out)
            if size < 1024:
                raise RuntimeError("Rendered MP4 is unexpectedly small")
            with open(out, "rb") as f:
                put = requests.put(upload_url, data=f, headers={"Content-Type": "video/mp4"}, timeout=(30, 900))
            put.raise_for_status()
            return {"status": "COMPLETED", "bytes": size, "content_type": "video/mp4",
                    "duration": duration, "scene_count": scene_count, "render_mode": render_mode,
                    "output_key": inp.get("output_key", "")}
    except requests.RequestException as e:
        return {"status": "FAILED", "error": f"Storage transfer failed: {str(e)[:500]}"}
    except subprocess.TimeoutExpired:
        return {"status": "FAILED", "error": "FFmpeg rendering exceeded the 30-minute worker limit"}
    except Exception as e:
        return {"status": "FAILED", "error": str(e)[:1500]}


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
