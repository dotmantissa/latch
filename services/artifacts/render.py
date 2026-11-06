"""Fixed offline PDF renderer, with no files or network after font/codec initialization."""

import importlib.util
import io
import json
import sys
import textwrap
from pathlib import Path


def setup():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    root = Path(__file__).absolute().parents[2]
    pdfmetrics.registerFont(TTFont("Latch", str(root / "assets/fonts/Manrope.ttf")))
    pdfmetrics.registerFont(
        TTFont("LatchHeading", str(root / "assets/fonts/DMSerifDisplay-Regular.ttf"))
    )
    # Load fixed ReportLab encodings/compression/font subsets before removing file authority.
    warm = canvas.Canvas(io.BytesIO(), invariant=1)
    for name in ("Latch", "LatchHeading"):
        warm.setFont(name, 11)
        warm.drawString(30, 30, "Warmup 0123 and punctuation")
    warm.save()
    spec = importlib.util.spec_from_file_location("decoder", Path(__file__).with_name("decode.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.restrict()
    return canvas, pdfmetrics


def main():
    canvas, metrics = setup()
    raw = sys.stdin.buffer.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError("RECEIPT_RENDER_LIMIT")
    record = json.loads(raw)
    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=(595, 842), invariant=1, pageCompression=1)
    pdf.setTitle("Latch internal decision record")
    pdf.setAuthor("Latch")
    y = 795

    def line(value, heading=False):
        nonlocal y
        value = str(value).replace("\r", " ").replace("\n", " ")
        for part in textwrap.wrap(value, width=85) or [""]:
            if y < 60:
                pdf.showPage()
                y = 795
            pdf.setFillColorRGB(23 / 255, 23 / 255, 23 / 255)
            font = "LatchHeading" if heading else "Latch"
            if any(ord(char) not in metrics.getFont(font).face.charToGlyph for char in part):
                raise ValueError("RECEIPT_FONT_UNSUPPORTED")
            pdf.setFont(font, 15 if heading else 10)
            pdf.drawString(40, y, part)
            y -= 22 if heading else 15

    # Same fixed geometry as assets/brand/mark-light.svg, without SVG parsing or file access.
    pdf.saveState()
    pdf.translate(36, 817)
    pdf.scale(0.5, -0.5)
    pdf.setFillColorRGB(23 / 255, 23 / 255, 23 / 255)
    for points in (
        ((12, 12), (22, 12), (22, 44), (36, 44), (36, 54), (12, 54)),
        ((44, 18), (56, 18), (56, 42), (44, 42), (44, 34), (48, 34), (48, 26), (44, 26)),
    ):
        path = pdf.beginPath()
        path.moveTo(*points[0])
        for point in points[1:]:
            path.lineTo(*point)
        path.close()
        pdf.drawPath(path, fill=1, stroke=0)
    pdf.roundRect(21, 26, 29, 8, 1, fill=1, stroke=0)
    pdf.restoreState()
    pdf.setFont("Latch", 18)
    pdf.drawString(77, 795, "Latch")
    y = 760
    line("Internal decision record", True)
    line(record["scope"])
    line("Record " + record["id"])
    line("Committed " + record["committed_at"])
    line("Request version " + str(record["request_version"]))
    worksheet = record["worksheet"]
    line(worksheet["name"], True)
    line("Budget USD " + f"{worksheet['budget_cents'] / 100:.2f}")
    line("Required by " + worksheet["required_by"] + " / " + worksheet["timezone"])
    for item in worksheet["items"]:
        line(str(item["required_units"]) + " units / " + item["specification"])
    approved = record["approved_packet"]
    line("Approval " + record["approval_id"])
    line("Approval hash " + record["approval_hash"])
    for source in approved["comparison"]["sources"]:
        line(source["label"], True)
        known_lines = any(
            item.get("extended_cents") is not None for item in source["basket"]["lines"]
        )
        line(
            "Quoted subtotal "
            + (
                f"USD {source['basket']['quoted_subtotal_cents'] / 100:.2f}"
                if known_lines
                else "unresolved"
            )
        )
        total = source["basket"]["complete_total_cents"]
        line("Complete total " + ("unresolved" if total is None else f"USD {total / 100:.2f}"))
        for field in source["reviewed_fields"]:
            original = field["original"]
            line(
                (original["item_key"] or "Terms")
                + " / "
                + original["kind"]
                + " / "
                + json.dumps(field["value"], ensure_ascii=False)
                + " / "
                + field["state"]
            )
            review = field.get("latest_review")
            if review:
                line(
                    "Reviewed by "
                    + review["reviewer"]["display_name"]
                    + " / "
                    + review["created_at"]
                )
                for span in review["decision"]["spans"]:
                    line("Source quote: " + span["quote"])
                if review["decision"]["reason"]:
                    line("Reason: " + review["decision"]["reason"])
    line("Fresh source index", True)
    for source in record["fresh_sources"]:
        for page in source["pages"]:
            line(page["source_url"])
            line("Captured " + page["started_at"] + " to " + page["completed_at"])
            line("Raster SHA256 " + page["raster_hash"])
    pdf.save()
    value = output.getvalue()
    if not value.startswith(b"%PDF-") or len(value) > 2 * 1024 * 1024:
        raise ValueError("RECEIPT_RENDER_LIMIT")
    sys.stdout.buffer.write(value)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit(1) from None
