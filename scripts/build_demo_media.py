"""Encode genuine browser footage; captions and timing edits do not alter app results."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def timestamp(seconds):
    ms = round(seconds * 1000)
    hours, rest = divmod(ms, 3600000)
    minutes, rest = divmod(rest, 60000)
    seconds, ms = divmod(rest, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{ms:03}"


def build(ffmpeg, source, timeline):
    data = json.loads(timeline.read_text(encoding="utf-8"))
    if not data["complete"]:
        raise ValueError("Only a successfully completed recording can be published")
    work = Path("work/recording")
    stages = data["stages"]
    captions = []
    for index, row in enumerate(stages):
        end = stages[index + 1]["seconds"] if index + 1 < len(stages) else 180
        captions.append(
            f"{index + 1}\n{timestamp(row['seconds'])} --> {timestamp(min(end, 180))}\n"
            + row["label"]
            + "\nFictional demo account / student simulator\n"
        )
    (work / "captions.srt").write_text("\n".join(captions), encoding="utf-8")
    video = Path("output/video/GigBid_Demo.mp4")
    video.parent.mkdir(parents=True, exist_ok=True)

    def encode(args):
        subprocess.run(
            [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y", "-i", str(source), *args],
            check=True,
        )

    encode(
        [
            "-vf",
            "tpad=stop_mode=clone:stop_duration=10,"
            "subtitles=work/recording/captions.srt:force_style='FontName=Segoe UI,"
            "FontSize=17,Outline=2,MarginV=16'",
            "-t",
            "180",
            "-an",
            "-c:v",
            "libx264",
            "-crf",
            "25",
            "-preset",
            "fast",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(video),
        ]
    )
    selected = [stages[i]["seconds"] for i in [0, 3, 5, 6, 8, 9]]
    selection = "+".join(f"between(t,{start:.3f},{start + 5:.3f})" for start in selected)
    gif = Path("docs/images/demo.gif")
    encode(
        [
            "-filter_complex",
            f"[0:v]select='{selection}',setpts=N/FRAME_RATE/TB,"
            "fps=10,scale=800:-1:flags=lanczos,split[a][b];"
            "[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer",
            "-t",
            "30",
            "-loop",
            "0",
            str(gif),
        ]
    )
    encode(
        [
            "-vf",
            "fps=1/15,scale=480:-1,tile=3x4",
            "-frames:v",
            "1",
            str(work / "contact-sheet.png"),
        ]
    )
    result = {
        "kind": "Real browser recording; hosted models with synthetic persona/client",
        "video_seconds": 180,
        "gif_seconds": 30,
        "edits": "Video captioned and padded at end; GIF selects six five-second excerpts.",
        "stages": stages,
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "files": {
            str(p): {
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                "bytes": p.stat().st_size,
            }
            for p in [video, gif]
        },
    }
    Path("evals/results/demo-recording.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print("Demo video and GIF encoded; inspect the contact sheet before publication.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ffmpeg", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--timeline", type=Path, required=True)
    args = parser.parse_args()
    build(args.ffmpeg, args.input, args.timeline)
