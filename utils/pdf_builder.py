from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


def build_storybook_pdf(pdf_path: str, scenes: list) -> None:
    c = canvas.Canvas(pdf_path, pagesize=A4)
    page_width, page_height = A4

    for idx, scene in enumerate(scenes, start=1):
        title = scene["title"]
        story_text = scene["story_text"]
        image_path = scene["image_path"]

        c.setFont("Helvetica-Bold", 20)
        c.drawString(50, page_height - 60, f"Page {idx}: {title}")

        img = ImageReader(image_path)
        max_width = page_width - 100
        max_height = 320
        img_width, img_height = img.getSize()
        scale = min(max_width / img_width, max_height / img_height)
        draw_width = img_width * scale
        draw_height = img_height * scale

        img_x = (page_width - draw_width) / 2
        img_y = page_height - 420
        c.drawImage(img, img_x, img_y, width=draw_width, height=draw_height, preserveAspectRatio=True)

        c.setFont("Helvetica", 12)
        text_obj = c.beginText(50, img_y - 30)
        text_obj.setLeading(16)

        words = story_text.split()
        current_line = []
        max_chars = 90
        for word in words:
            test_line = " ".join(current_line + [word])
            if len(test_line) <= max_chars:
                current_line.append(word)
            else:
                text_obj.textLine(" ".join(current_line))
                current_line = [word]
        if current_line:
            text_obj.textLine(" ".join(current_line))

        c.drawText(text_obj)
        c.showPage()

    c.save()
