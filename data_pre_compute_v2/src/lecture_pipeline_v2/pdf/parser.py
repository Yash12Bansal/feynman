"""PDF parsing: text extraction, image extraction, OCR fallback.

Ported from v1 verbatim; only import paths changed.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path

import fitz
from PIL import Image

from ..config import PDFConfig


@dataclass
class PageContent:
    page_number: int
    text: str
    image_count: int = 0
    _image_refs: list[int] = field(default_factory=list, repr=False)
    _doc_path: str = field(default="", repr=False)


@dataclass
class PDFContent:
    pages: list[PageContent]
    toc_raw: list[tuple[int, str, int]]
    total_pages: int
    metadata: dict
    _doc_path: str = field(default="", repr=False)

    def get_text_for_range(self, start_page: int, end_page: int) -> str:
        texts = []
        for page in self.pages:
            if start_page <= page.page_number <= end_page:
                texts.append(page.text)
        return "\n\n".join(texts)

    def get_pages_for_range(self, start_page: int, end_page: int) -> list[PageContent]:
        return [p for p in self.pages if start_page <= p.page_number <= end_page]

    def extract_images_for_page(self, page: PageContent) -> list[tuple[bytes, str]]:
        if not page._image_refs or not self._doc_path:
            return []
        doc = fitz.open(self._doc_path)
        images = []
        try:
            for xref in page._image_refs:
                base_image = doc.extract_image(xref)
                if base_image and base_image.get("image"):
                    ext = base_image.get("ext", "png")
                    images.append((base_image["image"], ext))
        finally:
            doc.close()
        return images

    def extract_images_to_dir(
        self, output_dir: str | Path, start_page: int, end_page: int, dpi: int = 200
    ) -> list[Path]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        saved: list[Path] = []
        pages = self.get_pages_for_range(start_page, end_page)

        for page in pages:
            images = self.extract_images_for_page(page)
            for idx, (img_bytes, ext) in enumerate(images, 1):
                filename = f"page_{page.page_number}_img_{idx}.{ext}"
                img_path = output_dir / filename
                img_path.write_bytes(img_bytes)
                saved.append(img_path)

        if not self._doc_path:
            return saved

        doc = fitz.open(self._doc_path)
        try:
            for page_content in pages:
                page_idx = page_content.page_number - 1
                if page_idx < 0 or page_idx >= len(doc):
                    continue
                page = doc[page_idx]
                pix = page.get_pixmap(dpi=dpi)
                filename = f"page_{page_content.page_number}.png"
                img_path = output_dir / filename
                pix.save(str(img_path))
                saved.append(img_path)
        finally:
            doc.close()

        return saved


class PDFParser:
    def __init__(self, config: PDFConfig | None = None):
        self.config = config or PDFConfig()

    def parse(
        self,
        pdf_path: str | Path,
        page_range: tuple[int, int] | None = None,
    ) -> PDFContent:
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        doc = fitz.open(str(pdf_path))

        toc_raw = doc.get_toc()
        metadata = doc.metadata or {}
        total_pages = len(doc)

        if page_range:
            start, end = page_range
            start = max(1, start)
            end = min(total_pages, end)
        else:
            start, end = 1, total_pages

        pages = []
        for page_idx in range(total_pages):
            page_num = page_idx + 1

            if start <= page_num <= end:
                page = doc[page_idx]
                page_content = self._extract_page(doc, page, page_num, str(pdf_path))
                pages.append(page_content)
            elif not page_range:
                page = doc[page_idx]
                text = page.get_text("text").strip()
                pages.append(PageContent(page_number=page_num, text=text))

        doc.close()

        return PDFContent(
            pages=pages,
            toc_raw=[(lvl, title, pno) for lvl, title, pno in toc_raw],
            total_pages=total_pages,
            metadata=metadata,
            _doc_path=str(pdf_path),
        )

    def _extract_page(
        self, doc: fitz.Document, page: fitz.Page, page_number: int, doc_path: str
    ) -> PageContent:
        text = page.get_text("text").strip()

        if len(text) < self.config.ocr_threshold:
            text = self._ocr_page(page)

        image_refs = []
        try:
            image_list = page.get_images(full=True)
            image_refs = [img_info[0] for img_info in image_list]
        except Exception:
            pass

        return PageContent(
            page_number=page_number,
            text=text,
            image_count=len(image_refs),
            _image_refs=image_refs,
            _doc_path=doc_path,
        )

    def _ocr_page(self, page: fitz.Page) -> str:
        try:
            tp = page.get_textpage_ocr(language=self.config.ocr_language, full=True)
            return tp.extractText().strip()
        except Exception:
            return self._ocr_page_fallback(page)

    def _ocr_page_fallback(self, page: fitz.Page) -> str:
        try:
            import pytesseract

            pix = page.get_pixmap(dpi=self.config.image_dpi)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            return pytesseract.image_to_string(img, lang=self.config.ocr_language).strip()
        except Exception:
            return ""
