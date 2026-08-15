"""上传文件的轻量文本解析器，供岗位创建与录用前核验页面复用。"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path


def parse_uploaded_file(content: bytes, file_name: str) -> str:
    suffix = Path(file_name or "").suffix.lower()
    if suffix in {".txt", ".md"}:
        for encoding in ("utf-8", "utf-8-sig", "gb18030"):
            try:
                return content.decode(encoding).strip()
            except UnicodeDecodeError:
                continue
        raise ValueError("文本编码无法识别，请另存为 UTF-8 后重试。")

    if suffix == ".docx":
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                xml = archive.read("word/document.xml").decode("utf-8")
        except (zipfile.BadZipFile, KeyError, UnicodeDecodeError) as exc:
            raise ValueError("Word 文件无法解析，请确认文件未损坏。") from exc
        xml = re.sub(r"</w:p>", "\n", xml)
        xml = re.sub(r"<[^>]+>", "", xml)
        return _unescape_xml(xml).strip()

    if suffix == ".pdf":
        errors = []
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(content))
            text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
            if text:
                return text
        except Exception as exc:
            errors.append(exc)

        # 本地开发环境可能没有 pypdf，优先复用已安装的 PyMuPDF。
        try:
            import pymupdf
            with pymupdf.open(stream=content, filetype="pdf") as document:
                text = "\n".join(page.get_text("text") for page in document).strip()
            if text:
                return text
        except Exception as exc:
            errors.append(exc)
        raise ValueError("PDF 未提取到文字；如为扫描件，请改用岗位截图上传。") from errors[-1]

    if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        return _ocr_image(content)

    raise ValueError("暂不支持该文件类型，请上传截图、PDF、DOCX、TXT 或 Markdown。")


def _ocr_image(content: bytes) -> str:
    """使用轻量本地 OCR 识别岗位截图；组件不可用时给出可操作提示。"""
    try:
        import numpy as np
        from PIL import Image
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as exc:
        raise ValueError("当前环境缺少截图识别组件，请重新运行 dev.sh 安装依赖。") from exc

    try:
        image = np.asarray(Image.open(io.BytesIO(content)).convert("RGB"))
        result, _ = RapidOCR()(image)
    except Exception as exc:
        raise ValueError("岗位截图无法识别，请换一张更清晰、文字更完整的图片。") from exc
    lines = [str(item[1]).strip() for item in (result or []) if len(item) > 1 and str(item[1]).strip()]
    text = "\n".join(lines).strip()
    if not text:
        raise ValueError("岗位截图中未识别到文字，请上传清晰截图或岗位文档。")
    return text


def _unescape_xml(text: str) -> str:
    return (text.replace("&amp;", "&").replace("&lt;", "<")
            .replace("&gt;", ">").replace("&quot;", '"')
            .replace("&apos;", "'"))
