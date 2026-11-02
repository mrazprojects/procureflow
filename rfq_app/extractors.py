from pathlib import Path
import io


def _image_to_readable_text(image_bytes):
    """Extract OCR words and rebuild image text in visual, row-by-row order."""
    from PIL import Image
    import pytesseract

    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    # Tesseract word coordinates let us reconstruct table rows instead of
    # accepting its default column-by-column reading order.
    data = pytesseract.image_to_data(
        image,
        output_type=pytesseract.Output.DICT,
        config="--psm 6",
    )

    words = []
    for index, raw_word in enumerate(data["text"]):
        word = raw_word.strip()
        if not word:
            continue
        try:
            confidence = float(data["conf"][index])
        except (TypeError, ValueError):
            confidence = -1
        if confidence < 0:
            continue

        top = int(data["top"][index])
        height = int(data["height"][index])
        left = int(data["left"][index])
        words.append({
            "text": word,
            "center_y": top + height / 2,
            "left": left,
        })

    # Cluster words whose vertical centres are close. The tolerance is
    # deliberately small enough to keep separate table rows distinct.
    words.sort(key=lambda item: item["center_y"])
    rows = []
    row_tolerance = max(10, int(image.height * 0.012))

    for word in words:
        if not rows or abs(word["center_y"] - rows[-1]["center_y"]) > row_tolerance:
            rows.append({
                "center_y": word["center_y"],
                "words": [word],
            })
        else:
            rows[-1]["words"].append(word)
            centres = [item["center_y"] for item in rows[-1]["words"]]
            rows[-1]["center_y"] = sum(centres) / len(centres)

    lines = []
    for row in rows:
        row_words = sorted(row["words"], key=lambda item: item["left"])
        lines.append(" ".join(item["text"] for item in row_words))

    return "\n".join(lines).strip()


def extract_text(file):
    name = getattr(file, "name", "upload")
    ext = Path(name).suffix.lower()
    data = file.getvalue() if hasattr(file, "getvalue") else Path(name).read_bytes()

    if ext == ".pdf":
        import pymupdf
        doc = pymupdf.open(stream=data, filetype="pdf")
        return "\n".join(page.get_text("text") for page in doc).strip()

    if ext == ".docx":
        from docx import Document
        doc = Document(io.BytesIO(data))
        parts = [paragraph.text for paragraph in doc.paragraphs if paragraph.text.strip()]
        for table in doc.tables:
            parts.extend(
                " | ".join(cell.text.strip() for cell in row.cells)
                for row in table.rows
            )
        return "\n".join(parts)

    if ext == ".txt":
        return data.decode("utf-8", errors="replace")

    if ext in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}:
        return _image_to_readable_text(data)

    raise ValueError(f"Unsupported document type: {ext}")
