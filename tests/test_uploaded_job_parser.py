import io
import zipfile

from app.parser import parse_uploaded_file


def test_parse_uploaded_txt():
    text = parse_uploaded_file("质量工程师，熟悉8D与FMEA".encode(), "岗位.txt")
    assert "质量工程师" in text
    assert "FMEA" in text


def test_parse_uploaded_docx_xml():
    document_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body><w:p><w:r><w:t>质量工程师</w:t></w:r></w:p>
      <w:p><w:r><w:t>本科，3年以上，熟悉ISO 9001</w:t></w:r></w:p></w:body>
    </w:document>"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", document_xml)
    text = parse_uploaded_file(buffer.getvalue(), "岗位.docx")
    assert "质量工程师" in text
    assert "ISO 9001" in text


def test_reject_unsupported_upload():
    try:
        parse_uploaded_file(b"data", "岗位.xls")
    except ValueError as exc:
        assert "暂不支持" in str(exc)
    else:
        raise AssertionError("unsupported file should fail")
