"""上传文件的轻量文本解析器，供录用前核验页面复用。"""

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
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ValueError("当前环境缺少 PDF 解析组件，请重新运行 dev.sh 安装依赖。") from exc
        try:
            reader = PdfReader(io.BytesIO(content))
            return "\n".join((page.extract_text() or "") for page in reader.pages).strip()
        except Exception as exc:
            raise ValueError("PDF 无法提取文字，请上传文本型 PDF 或 Word 文件。") from exc

    raise ValueError("暂不支持该文件类型，请上传 PDF、DOCX、TXT 或 Markdown。")


def _unescape_xml(text: str) -> str:
    return (text.replace("&amp;", "&").replace("&lt;", "<")
            .replace("&gt;", ">").replace("&quot;", '"')
            .replace("&apos;", "'"))
