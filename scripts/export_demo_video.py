#!/usr/bin/env python3
"""Export the actual recorded browser walkthrough with timestamped containment evidence."""

import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/submission"
RUN = ROOT / "var/submission/public-demo"


def main():
    report = json.loads((ROOT / "var/submission/containment.json").read_text())
    capture = next(r for r in report["reports"] if r["mode"] == "capture")
    timeout = next(r for r in report["reports"] if r["mode"] == "timeout")
    im = Image.new("RGB", (1600, 900), "#F4F0E8")
    d = ImageDraw.Draw(im)

    def font(n):
        return ImageFont.truetype(str(ROOT / "assets/fonts/Manrope.ttf"), n)

    d.rectangle((0, 0, 24, 900), fill="#7A2838")
    d.text((80, 65), "Actual Vultr sandbox containment check", font=font(45), fill="#2C2825")
    d.text(
        (80, 148),
        capture["at"][:19].replace("T", " ") + " UTC · recorded observation",
        font=font(25),
        fill="#61584F",
    )
    y = 242
    for name, status in capture["network_observations"].items():
        d.text((80, y), name.replace("_", " "), font=font(31), fill="#2C2825")
        d.text((750, y), status.replace("_", " "), font=font(31), fill="#7A2838")
        y += 58
    assert (
        timeout["timeout_observed"] and timeout["cleanup_observed"] and capture["cleanup_observed"]
    )
    d.text(
        (80, 756),
        "Host watchdog: task terminated. Container cleanup confirmed.",
        font=font(27),
        fill="#7A2838",
    )
    im.save(ROOT / "var/submission/containment-card.png")
    ff = (ROOT / "var/submission/ffmpeg-path").read_text().strip()
    inputs = [
        (OUT / "cover.png", 4),
        (RUN / "demo.webm", None),
        (RUN / "review.png", 5),
        (RUN / "comparison.png", 5),
        (RUN / "containment.png", 5),
        (ROOT / "var/submission/containment-card.png", 7),
    ]
    cmd = [ff, "-y", "-hide_banner", "-loglevel", "warning", "-filter_complex_threads", "1"]
    for path, seconds in inputs:
        if seconds:
            cmd += ["-loop", "1", "-t", str(seconds)]
        cmd += ["-i", str(path)]
    filters = []
    for i in range(len(inputs)):
        filters.append(
            f"[{i}:v]scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0xf4f0e8,setsar=1,fps=25,format=yuv420p,setpts=PTS-STARTPTS[v{i}]"
        )
    filters.append(
        "".join(f"[v{i}]" for i in range(len(inputs)))
        + f"concat=n={len(inputs)}:v=1:a=0[out]"
    )
    cmd += [
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[out]",
        "-c:v",
        "libx264",
        "-threads",
        "2",
        "-preset",
        "fast",
        "-crf",
        "22",
        "-movflags",
        "+faststart",
        str(OUT / "demo.mp4"),
    ]
    subprocess.run(cmd, check=True)
    print("Exported actual recorded demo.mp4 with timestamped containment observations.")


if __name__ == "__main__":
    main()
