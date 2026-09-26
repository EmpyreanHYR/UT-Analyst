"""检测报告生成模块，支持HTML和PDF格式导出、标准模板和定制化。"""

from __future__ import annotations

import logging
import base64
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("ut_analyst.report_generator")


# ── 标准模板库 ──────────────────────────────────────────────────────────────────

REPORT_STANDARDS = {
    "通用": {
        "name": "通用检测报告",
        "reference_standard": "GB/T 2970-2016",
        "acceptance_level": "按设计要求",
    },
    "NB/T 47013": {
        "name": "承压设备无损检测报告",
        "reference_standard": "NB/T 47013.3-2015",
        "acceptance_level": "I级/II级",
    },
    "GB/T 11345": {
        "name": "焊缝超声检测报告",
        "reference_standard": "GB/T 11345-2013",
        "acceptance_level": "按焊缝质量等级",
    },
    "ASME": {
        "name": "ASME Code Examination Report",
        "reference_standard": "ASME Section V Article 4",
        "acceptance_level": "Per ASME Sec. VIII",
    },
}


class ReportConfig:
    """报告配置。"""

    def __init__(
        self,
        standard_key: str = "通用",
        workpiece_name: str = "工件-001",
        operator_name: str = "",
        inspector_name: str = "",
        company_name: str = "",
        project_name: str = "",
        test_location: str = "",
        notes: str = "",
    ) -> None:
        self.standard_key = standard_key
        self.workpiece_name = workpiece_name
        self.operator_name = operator_name
        self.inspector_name = inspector_name
        self.company_name = company_name
        self.project_name = project_name
        self.test_location = test_location
        self.notes = notes


class ReportGenerator:
    """
    检测报告生成器。

    功能：
    1. HTML格式报告生成（含内联CSS）
    2. PDF格式报告导出（基于Qt打印功能）
    3. 多标准模板支持
    4. 报告定制化（Logo、公司信息、检测人员等）
    """

    def __init__(self) -> None:
        """初始化报告生成器。"""
        self.report_standards = REPORT_STANDARDS

    def get_available_standards(self) -> list[str]:
        """获取可用的报告标准列表。"""
        return list(self.report_standards.keys())

    def generate_html_report(
        self,
        config: ReportConfig,
        detection_time: str,
        decision_result: str,
        overview_image_data_uri: str,
        defect_records: list[dict[str, Any]],
        defect_snapshots: list[dict[str, Any]],
        parameters: dict[str, Any] | None = None,
        signed_by: str | None = None,
        signed_at: str | None = None,
    ) -> str:
        """
        生成HTML格式检测报告。

        参数：
        - config: 报告配置
        - detection_time: 检测时间
        - decision_result: 判定结果（"合格"/"不合格"）
        - overview_image_data_uri: 总览图base64数据
        - defect_records: 缺陷记录列表
        - defect_snapshots: 缺陷截图列表
        - parameters: 检测参数（可选）

        返回：
        - html: HTML报告字符串
        """
        standard_info = self.report_standards.get(config.standard_key, self.report_standards["通用"])

        decision_color = "#e74c3c" if decision_result == "不合格" else "#27ae60"
        defect_count = len(defect_snapshots)

        # 公司信息头部
        company_header = ""
        if config.company_name:
            company_header = f"""
            <div style="text-align:center; margin-bottom:15px;">
                <h2 style="color:#2c3e50; margin:0;">{config.company_name}</h2>
                {f'<p style="color:#7f8c8d; margin:2px 0;">{config.project_name}</p>' if config.project_name else ''}
            </div>
            <hr style="border:1px solid #3498db;">"""

        # 检测人员信息
        personnel_html = ""
        if config.operator_name or config.inspector_name:
            personnel_html = f"""
            <div style="margin:10px 0;">
                <table style="width:100%; border-collapse:collapse;">
                    <tr>
                        <td style="padding:4px 8px; border:1px solid #ddd; background:#f8f9fa; width:120px;">操作人员</td>
                        <td style="padding:4px 8px; border:1px solid #ddd;">{config.operator_name or '——'}</td>
                        <td style="padding:4px 8px; border:1px solid #ddd; background:#f8f9fa; width:120px;">审核人员</td>
                        <td style="padding:4px 8px; border:1px solid #ddd;">{config.inspector_name or '——'}</td>
                    </tr>
                </table>
            </div>"""

        # 检测参数表
        parameters_html = ""
        if parameters:
            rows = ""
            param_labels = {
                "samplingRateHz": "采样率",
                "pulseFrequencyHz": "探头频率",
                "gainDb": "增益",
                "scanDepthMm": "扫查深度",
                "soundVelocityMps": "声速",
                "thresholdLevel": "阈值电平",
            }
            for key, label in param_labels.items():
                val = parameters.get(key, "")
                if val != "":
                    unit_map = {
                        "samplingRateHz": "Hz",
                        "pulseFrequencyHz": "Hz",
                        "gainDb": "dB",
                        "scanDepthMm": "mm",
                        "soundVelocityMps": "m/s",
                        "thresholdLevel": "",
                    }
                    unit = unit_map.get(key, "")
                    if key in ("samplingRateHz", "pulseFrequencyHz"):
                        val = f"{float(val)/1e6:.2f} MHz"
                    elif key == "soundVelocityMps":
                        val = f"{float(val):.0f} {unit}"
                    elif key == "gainDb":
                        val = f"{float(val):.1f} {unit}"
                    elif key == "scanDepthMm":
                        val = f"{float(val):.1f} {unit}"
                    else:
                        val = str(val)
                    rows += f"""
                    <tr>
                        <td style="padding:4px 8px; border:1px solid #ddd; background:#f8f9fa;">{label}</td>
                        <td style="padding:4px 8px; border:1px solid #ddd;">{val}</td>
                    </tr>"""

            if rows:
                parameters_html = f"""
                <h3 style="color:#2c3e50; border-bottom:2px solid #3498db; padding-bottom:5px;">检测参数</h3>
                <table style="width:100%; border-collapse:collapse; margin:10px 0;">
                    {rows}
                </table>"""

        # 缺陷记录卡片
        defect_cards_html = ""
        for idx, snap in enumerate(defect_snapshots):
            card_img = ""
            if "imageDataUri" in snap and snap["imageDataUri"]:
                card_img = f'<img src="{snap["imageDataUri"]}" style="max-width:100%; border-radius:4px; margin-top:8px;">'
            defect_cards_html += f"""
            <div style="border:1px solid #ddd; border-radius:6px; padding:12px; margin:8px 0; background:#fafbfc;">
                <h4 style="margin:0 0 8px 0; color:#e74c3c;">缺陷 #{idx + 1}</h4>
                <table style="width:100%; border-collapse:collapse;">
                    <tr>
                        <td style="padding:3px 8px; border:1px solid #eee; background:#f5f5f5; width:100px;">深度</td>
                        <td style="padding:3px 8px; border:1px solid #eee;">{snap.get('depthMm', '——'):.2f} mm</td>
                        <td style="padding:3px 8px; border:1px solid #eee; background:#f5f5f5; width:100px;">波幅</td>
                        <td style="padding:3px 8px; border:1px solid #eee;">{snap.get('amplitude', 0) * 100:.1f}%</td>
                    </tr>
                </table>
                {card_img}
            </div>"""

        # 整体报告HTML
        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>超声检测报告 - {config.workpiece_name}</title>
    <style>
        body {{ font-family: 'Microsoft YaHei', 'SimHei', Arial, sans-serif; margin: 20px; color: #2c3e50; background: #fff; }}
        h1 {{ text-align: center; color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }}
        h3 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 5px; }}
        .decision {{ font-size: 28px; font-weight: bold; color: {decision_color}; text-align: center; padding: 15px; border: 3px solid {decision_color}; border-radius: 8px; margin: 20px 0; }}
        .overview-img {{ text-align: center; margin: 15px 0; }}
        .overview-img img {{ max-width: 100%; border: 1px solid #ddd; border-radius: 6px; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 6px 10px; border: 1px solid #ddd; }}
        th {{ background: #ecf0f1; font-weight: 600; }}
        .footer {{ text-align: center; color: #95a5a6; font-size: 12px; margin-top: 30px; padding-top: 10px; border-top: 1px solid #ddd; }}
    </style>
</head>
<body>
    {company_header}
    <h1>超声检测报告</h1>
    <p style="text-align:center; color:#7f8c8d;">参考标准：{standard_info['reference_standard']} | 验收等级：{standard_info['acceptance_level']}</p>

    <table style="margin:15px 0;">
        <tr>
            <td style="background:#ecf0f1; width:120px; font-weight:600;">工件名称</td>
            <td>{config.workpiece_name}</td>
            <td style="background:#ecf0f1; width:120px; font-weight:600;">检测时间</td>
            <td>{detection_time}</td>
        </tr>
        <tr>
            <td style="background:#ecf0f1; font-weight:600;">检测地点</td>
            <td>{config.test_location or '——'}</td>
            <td style="background:#ecf0f1; font-weight:600;">缺陷数量</td>
            <td>{defect_count}</td>
        </tr>
    </table>
    {personnel_html}
    {parameters_html}
    {f'<p style="color:#2c3e50;"><strong>报告签名：</strong>{signed_by} | {signed_at}</p>' if signed_by else ''}
    <div class="decision">判定结果：{decision_result}</div>

    <h3>波形总览</h3>
    <div class="overview-img">
        <img src="{overview_image_data_uri}" alt="波形总览">
    </div>

    <h3>缺陷详情（共 {defect_count} 项）</h3>
    {defect_cards_html if defect_cards_html else '<p style="color:#27ae60; font-size:16px;">✅ 未发现缺陷记录。</p>'}

    {f'<h3>备注</h3><p>{config.notes}</p>' if config.notes else ''}

    <div class="footer">
        <p>由超声波智能辅助检测系统 UT-Analyst V1.0 生成 | {detection_time}</p>
        <p>报告内容哈希: __REPORT_HASH__</p>
    </div>
</body>
</html>"""

        content_hash = hashlib.sha256(html.encode("utf-8")).hexdigest()
        return html.replace("__REPORT_HASH__", content_hash)
