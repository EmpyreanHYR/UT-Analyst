"""Report file export helpers."""

from __future__ import annotations

import hashlib
from pathlib import Path

from PyQt5.QtGui import QPageSize, QTextDocument
from PyQt5.QtPrintSupport import QPrinter


class ReportExporter:
    """Write report HTML and render the same HTML to PDF."""

    @staticmethod
    def _sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def export_html(self, html: str, output_path: str | Path) -> str:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8")
        return self._sha256(path)

    def export_pdf(self, html: str, output_path: str | Path) -> str:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        document = QTextDocument()
        document.setHtml(html)

        printer = QPrinter(QPrinter.HighResolution)
        printer.setOutputFormat(QPrinter.PdfFormat)
        printer.setOutputFileName(str(path))
        printer.setPageSize(QPageSize(QPageSize.A4))
        document.print_(printer)

        if not path.exists() or path.stat().st_size == 0:
            raise RuntimeError("PDF报告生成失败")
        return self._sha256(path)
