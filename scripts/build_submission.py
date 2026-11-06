#!/usr/bin/env python3
"""Generate original branded cover and shareable slides from actual verification evidence."""

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/submission"
STONE = "#F4F0E8"
INK = "#2C2825"
RED = "#7A2838"
MUTED = "#61584F"


def mark(draw, x, y, scale, color):
    draw.polygon(
        [
            (x + 12 * scale, y + 12 * scale),
            (x + 22 * scale, y + 12 * scale),
            (x + 22 * scale, y + 44 * scale),
            (x + 36 * scale, y + 44 * scale),
            (x + 36 * scale, y + 54 * scale),
            (x + 12 * scale, y + 54 * scale),
        ],
        fill=color,
    )
    draw.polygon(
        [
            (x + 44 * scale, y + 18 * scale),
            (x + 56 * scale, y + 18 * scale),
            (x + 56 * scale, y + 42 * scale),
            (x + 44 * scale, y + 42 * scale),
            (x + 44 * scale, y + 34 * scale),
            (x + 48 * scale, y + 34 * scale),
            (x + 48 * scale, y + 26 * scale),
            (x + 44 * scale, y + 26 * scale),
        ],
        fill=color,
    )
    draw.rounded_rectangle(
        (x + 21 * scale, y + 26 * scale, x + 50 * scale, y + 34 * scale), radius=scale, fill=color
    )


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    def font(n):
        return ImageFont.truetype(str(ROOT / "assets/fonts/Manrope.ttf"), n)
    def serif(n):
        return ImageFont.truetype(str(ROOT / "assets/fonts/DMSerifDisplay-Regular.ttf"), n)
    im = Image.new("RGB", (1600, 900), STONE)
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 26, 900), fill=RED)
    mark(d, 91, 74, 2.3, RED)
    d.text((250, 108), "Latch", font=serif(76), fill=INK)
    d.text((120, 290), "Check the terms.", font=serif(92), fill=INK)
    d.text((120, 406), "Keep the decision yours.", font=serif(92), fill=INK)
    d.line((120, 582, 1480, 582), fill=RED, width=3)
    d.text((120, 630), "Public supplier evidence. Contained execution.", font=font(34), fill=MUTED)
    d.text((120, 754), "Vultr Agent Rush  /  Blast Radius Zero", font=font(29), fill=RED)
    im.save(OUT / "cover.png")
    pdfmetrics.registerFont(TTFont("Manrope", str(ROOT / "assets/fonts/Manrope.ttf")))
    pdfmetrics.registerFont(
        TTFont("DMSerif", str(ROOT / "assets/fonts/DMSerifDisplay-Regular.ttf"))
    )
    c = canvas.Canvas(str(OUT / "slides.pdf"), pagesize=(960, 540), invariant=1)
    c.setTitle("Latch | Blast Radius Zero")
    c.setAuthor("dotmantissa")

    def page(n, title, kicker="Latch / Vultr Agent Rush"):
        c.setFillColor(HexColor(STONE))
        c.rect(0, 0, 960, 540, fill=1, stroke=0)
        c.setFillColor(HexColor(RED))
        c.rect(0, 0, 12, 540, fill=1, stroke=0)
        c.setFont("Manrope", 12)
        c.drawString(58, 490, kicker)
        c.setFillColor(HexColor(INK))
        c.setFont("DMSerif", 35)
        c.drawString(58, 427, title)
        c.setFillColor(HexColor(MUTED))
        c.setFont("Manrope", 11)
        c.drawString(58, 28, "Check the terms. Keep the decision yours.")
        c.drawRightString(902, 28, f"{n:02}")

    def lines(rows, y=347, size=21):
        c.setFillColor(HexColor(INK))
        c.setFont("Manrope", size)
        for line in rows:
            c.drawString(58, y, line)
            y -= 40

    page(1, "A quote can miss the whole kit.")
    lines(
        [
            "A visible price does not establish shipping, arrival or exclusions.",
            "Latch puts required items beside attributable supplier evidence.",
            "Unknown terms stay unknown until a person can resolve them.",
        ],
        size=20,
    )
    c.showPage()
    page(2, "Vultr plans. The sandbox executes.")
    lines(
        [
            "Goal and public descriptions → bounded model plan",
            "Admitted pages → Playwright in a disposable gVisor container",
            "Captured text + screenshots → extraction and vision checks",
            "Provisional fields → individual review and comparison",
        ],
        size=20,
    )
    c.setFillColor(HexColor(RED))
    c.setFont("Manrope", 14)
    c.drawString(58, 110, "Vultr control VM + separate worker VM + Serverless Inference")
    c.drawString(58, 80, "Neon durable records / Caddy HTTPS / encrypted artifact volume")
    c.showPage()
    page(3, "Containment is enforced outside the model.")
    evidence = json.loads((ROOT / "var/submission/containment.json").read_text())
    capture = next(r for r in evidence["reports"] if r["mode"] == "capture")
    lines(
        [
            "Actual Vultr worker check: " + capture["at"][:19].replace("T", " ") + " UTC",
            "Metadata, private, loopback and direct public access: denied",
            "Host SSH and DNS sockets: denied",
            "Host watchdog terminated the task; cleanup confirmed",
        ],
        size=18,
    )
    c.setFillColor(HexColor(MUTED))
    c.setFont("Manrope", 14)
    c.drawString(58, 115, "Nonroot Chromium + gVisor + seccomp + exact public proxy policy")
    c.drawString(58, 83, "The worker receives no model, database or deployment credentials.")
    c.showPage()
    page(4, "The public demo keeps uncertainty visible.")
    lines(
        [
            "Real source: Ubiquiti U6+ public product page",
            "Demonstration requirements: USD 200, deadline seven days away",
            "Incomplete quote terms and product image abstention block approval.",
            "No supplier order or human buyer acceptance is claimed.",
        ],
        size=19,
    )
    c.showPage()
    page(5, "Approval is bound to evidence and time.")
    lines(
        [
            "Immutable request versions and exact source quote attribution",
            "Integer comparisons; feasible offers only",
            "Recent password verification; approval expiry and revocation",
            "Fresh all-source recheck and database commit guards",
            "Immutable internal receipt; authorized JSON / PDF / ZIP",
        ],
        size=18,
    )
    c.showPage()
    page(6, "Try the bounded live demonstration.")
    lines(
        [
            "Open Latch → Try a private demo → U6+ source demonstration",
            "Read the public disclosure, then start an actual inspection.",
            "Review source evidence and save the current comparison.",
        ],
        size=19,
    )
    c.setFillColor(HexColor(RED))
    c.setFont("Manrope", 16)
    c.drawString(58, 185, "https://latch.64.177.55.57.sslip.io")
    c.drawString(58, 145, "https://github.com/dotmantissa/latch")
    c.setFillColor(HexColor(MUTED))
    c.setFont("Manrope", 13)
    c.drawString(58, 94, "Two inspections per demo / MIT project code / original brand")
    c.showPage()
    c.save()
    print("Generated original cover.png and six-page slides.pdf.")


if __name__ == "__main__":
    main()
