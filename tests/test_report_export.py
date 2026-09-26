"""Phase 2 HTML and PDF export tests."""

from __future__ import annotations

import hashlib

from app.common.report_exporter import ReportExporter
from app.common.report_generator import ReportConfig, ReportGenerator


def test_generated_html_contains_content_hash() -> None:
    html = ReportGenerator().generate_html_report(
        config=ReportConfig(workpiece_name="哈希测试"),
        detection_time="2026-09-26 12:00:00",
        decision_result="合格",
        overview_image_data_uri="",
        defect_records=[],
        defect_snapshots=[],
    )

    assert "报告内容哈希" in html
    assert "__REPORT_HASH__" not in html


def test_export_html_and_pdf_records_hashes(tmp_path, qapp) -> None:
    exporter = ReportExporter()
    html_path = tmp_path / "report.html"
    pdf_path = tmp_path / "report.pdf"

    html_hash = exporter.export_html("<html><body>测试报告</body></html>", html_path)
    pdf_hash = exporter.export_pdf("<html><body>测试报告</body></html>", pdf_path)

    assert html_path.read_text(encoding="utf-8") == "<html><body>测试报告</body></html>"
    assert html_hash == hashlib.sha256(html_path.read_bytes()).hexdigest()
    assert pdf_path.read_bytes().startswith(b"%PDF")
    assert pdf_hash == hashlib.sha256(pdf_path.read_bytes()).hexdigest()
