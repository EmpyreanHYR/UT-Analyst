"""report_generator 模块的单元测试。"""

from __future__ import annotations

import pytest

from app.common.report_generator import ReportGenerator, ReportConfig


class TestReportGeneratorBasic:
    """验证报告生成器的基本功能。"""

    def setup_method(self) -> None:
        """每个测试前创建报告生成器实例。"""
        self.generator = ReportGenerator()

    def test_get_available_standards(self) -> None:
        """应返回可用的报告标准列表。"""
        standards = self.generator.get_available_standards()

        assert isinstance(standards, list)
        assert len(standards) > 0
        assert "通用" in standards

    def test_generate_html_report_basic(self) -> None:
        """应能生成基本的HTML报告。"""
        config = ReportConfig(
            workpiece_name="测试工件",
            standard_key="通用",
        )

        html = self.generator.generate_html_report(
            config=config,
            detection_time="2024-01-01 10:00:00",
            decision_result="合格",
            overview_image_data_uri="data:image/png;base64,abc123",
            defect_records=[],
            defect_snapshots=[],
        )

        assert isinstance(html, str)
        assert len(html) > 0
        assert "测试工件" in html
        assert "合格" in html

    def test_generate_html_report_with_defects(self) -> None:
        """应能生成包含缺陷记录的HTML报告。"""
        config = ReportConfig(workpiece_name="测试工件")

        defect_snapshots = [
            {
                "recordUid": 1,
                "depthMm": 50.0,
                "amplitude": 0.8,
                "imageDataUri": "data:image/png;base64,abc123",
            },
            {
                "recordUid": 2,
                "depthMm": 70.0,
                "amplitude": 0.6,
                "imageDataUri": "data:image/png;base64,def456",
            },
        ]

        html = self.generator.generate_html_report(
            config=config,
            detection_time="2024-01-01 10:00:00",
            decision_result="不合格",
            overview_image_data_uri="data:image/png;base64,overview",
            defect_records=[],
            defect_snapshots=defect_snapshots,
        )

        assert "不合格" in html
        assert "缺陷 #1" in html
        assert "缺陷 #2" in html
        assert "50.00 mm" in html or "50.0" in html

    def test_generate_html_report_with_parameters(self) -> None:
        """应能生成包含检测参数的HTML报告。"""
        config = ReportConfig(workpiece_name="测试工件")

        parameters = {
            "samplingRateHz": 100_000_000.0,
            "pulseFrequencyHz": 2_500_000.0,
            "gainDb": 20.0,
            "scanDepthMm": 120.0,
            "soundVelocityMps": 5900.0,
            "thresholdLevel": 0.55,
        }

        html = self.generator.generate_html_report(
            config=config,
            detection_time="2024-01-01 10:00:00",
            decision_result="合格",
            overview_image_data_uri="data:image/png;base64,overview",
            defect_records=[],
            defect_snapshots=[],
            parameters=parameters,
        )

        assert "检测参数" in html
        assert "采样率" in html
        assert "探头频率" in html

    def test_generate_html_report_with_company_info(self) -> None:
        """应能生成包含公司信息的HTML报告。"""
        config = ReportConfig(
            workpiece_name="测试工件",
            company_name="测试公司",
            project_name="测试项目",
            operator_name="张三",
            inspector_name="李四",
        )

        html = self.generator.generate_html_report(
            config=config,
            detection_time="2024-01-01 10:00:00",
            decision_result="合格",
            overview_image_data_uri="data:image/png;base64,overview",
            defect_records=[],
            defect_snapshots=[],
        )

        assert "测试公司" in html
        assert "测试项目" in html
        assert "张三" in html
        assert "李四" in html

    def test_generate_html_report_with_notes(self) -> None:
        """应能生成包含备注的HTML报告。"""
        config = ReportConfig(
            workpiece_name="测试工件",
            notes="这是一条测试备注",
        )

        html = self.generator.generate_html_report(
            config=config,
            detection_time="2024-01-01 10:00:00",
            decision_result="合格",
            overview_image_data_uri="data:image/png;base64,overview",
            defect_records=[],
            defect_snapshots=[],
        )

        assert "这是一条测试备注" in html

    def test_generate_html_report_decision_colors(self) -> None:
        """判定结果应使用正确的颜色。"""
        config = ReportConfig(workpiece_name="测试工件")

        # 测试合格结果（绿色）
        html_pass = self.generator.generate_html_report(
            config=config,
            detection_time="2024-01-01 10:00:00",
            decision_result="合格",
            overview_image_data_uri="",
            defect_records=[],
            defect_snapshots=[],
        )
        assert "#27ae60" in html_pass  # 绿色

        # 测试不合格结果（红色）
        html_fail = self.generator.generate_html_report(
            config=config,
            detection_time="2024-01-01 10:00:00",
            decision_result="不合格",
            overview_image_data_uri="",
            defect_records=[],
            defect_snapshots=[],
        )
        assert "#e74c3c" in html_fail  # 红色


class TestReportConfig:
    """验证报告配置类。"""

    def test_default_config(self) -> None:
        """默认配置应有正确的默认值。"""
        config = ReportConfig()

        assert config.standard_key == "通用"
        assert config.workpiece_name == "工件-001"
        assert config.operator_name == ""
        assert config.inspector_name == ""

    def test_custom_config(self) -> None:
        """自定义配置应正确保存值。"""
        config = ReportConfig(
            standard_key="NB/T 47013",
            workpiece_name="自定义工件",
            operator_name="张三",
            inspector_name="李四",
            company_name="测试公司",
            project_name="测试项目",
            test_location="测试地点",
            notes="测试备注",
        )

        assert config.standard_key == "NB/T 47013"
        assert config.workpiece_name == "自定义工件"
        assert config.operator_name == "张三"
        assert config.inspector_name == "李四"
        assert config.company_name == "测试公司"
        assert config.project_name == "测试项目"
        assert config.test_location == "测试地点"
        assert config.notes == "测试备注"