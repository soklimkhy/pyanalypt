import base64
import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

_PAGE_W, _PAGE_H = A4
_MARGIN = 2 * cm
_CONTENT_W = _PAGE_W - 2 * _MARGIN


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "ReportTitle",
            parent=base["Title"],
            fontSize=20,
            spaceAfter=6,
            textColor=colors.HexColor("#1a1a2e"),
        ),
        "description": ParagraphStyle(
            "ReportDesc",
            parent=base["Normal"],
            fontSize=10,
            textColor=colors.HexColor("#555555"),
            spaceAfter=16,
        ),
        "chart_type": ParagraphStyle(
            "ChartType",
            parent=base["Normal"],
            fontSize=8,
            textColor=colors.HexColor("#888888"),
            spaceBefore=4,
            spaceAfter=2,
        ),
        "annotation": ParagraphStyle(
            "Annotation",
            parent=base["Normal"],
            fontSize=10,
            leading=15,
            textColor=colors.HexColor("#333333"),
            spaceBefore=6,
            spaceAfter=12,
        ),
        "no_content": ParagraphStyle(
            "NoContent",
            parent=base["Normal"],
            fontSize=9,
            textColor=colors.HexColor("#aaaaaa"),
            spaceAfter=8,
        ),
    }


def _decode_image(b64_string):
    """
    Decode a base64 PNG string (with or without data URI prefix) into a
    reportlab Image flowable sized to fill the content width.
    """
    if not b64_string:
        return None
    try:
        if "," in b64_string:
            b64_string = b64_string.split(",", 1)[1]
        data = base64.b64decode(b64_string)
        img_buf = io.BytesIO(data)

        # Determine natural dimensions so we can preserve aspect ratio.
        from PIL import Image as PILImage
        pil = PILImage.open(img_buf)
        nat_w, nat_h = pil.size
        img_buf.seek(0)

        scale = _CONTENT_W / nat_w
        return Image(img_buf, width=_CONTENT_W, height=nat_h * scale)
    except Exception:
        return None


def generate_report_pdf(report):
    """
    Build a PDF from a Report instance and return a BytesIO buffer
    positioned at the start.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=_MARGIN,
        rightMargin=_MARGIN,
        topMargin=_MARGIN,
        bottomMargin=_MARGIN,
        title=report.title,
    )

    s = _styles()
    story = []

    # --- Header ---
    story.append(Paragraph(report.title, s["title"]))
    if report.description:
        story.append(Paragraph(report.description, s["description"]))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#dddddd"), spaceAfter=16))

    items = list(report.items.order_by("order", "created_at"))

    if not items:
        story.append(Paragraph("This report has no items yet.", s["no_content"]))
    else:
        for i, item in enumerate(items):
            # Chart type label
            if item.chart_type and item.chart_type != "text":
                story.append(Paragraph(item.chart_type.upper() + " CHART", s["chart_type"]))

            # Chart image
            img = _decode_image(item.chart_image)
            if img:
                story.append(img)
            elif item.chart_type and item.chart_type != "text":
                story.append(Paragraph("[Chart image not available]", s["no_content"]))

            # Annotation
            if item.annotation:
                story.append(Paragraph(item.annotation, s["annotation"]))

            # Divider between items (skip after last)
            if i < len(items) - 1:
                story.append(Spacer(1, 0.3 * cm))
                story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#eeeeee"), spaceAfter=10))

    doc.build(story)
    buffer.seek(0)
    return buffer
