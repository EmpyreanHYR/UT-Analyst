"""defect_analyzer 模块的单元测试。"""

from __future__ import annotations

import numpy as np
import pytest

from app.model.defect_analyzer import DefectAnalyzer, DefectRecord


class TestDefectAnalyzerBasic:
    """验证缺陷分析器的基本功能。"""

    def setup_method(self) -> None:
        """每个测试前创建分析器实例。"""
        self.analyzer = DefectAnalyzer()

    def test_empty_statistics(self) -> None:
        """空记录的统计应返回零值。"""
        stats = self.analyzer.get_statistics()

        assert stats.total_count == 0
        assert stats.depth_min_mm == 0.0
        assert stats.depth_max_mm == 0.0
        assert stats.depth_mean_mm == 0.0
        assert stats.amplitude_mean == 0.0

    def test_add_record(self) -> None:
        """添加记录应增加记录数量。"""
        record = DefectRecord(uid=1, depth_mm=50.0, amplitude=0.8)
        self.analyzer.add_record(record)

        assert len(self.analyzer.defect_records) == 1

    def test_clear_records(self) -> None:
        """清空记录应删除所有记录。"""
        record1 = DefectRecord(uid=1, depth_mm=50.0, amplitude=0.8)
        record2 = DefectRecord(uid=2, depth_mm=60.0, amplitude=0.6)
        self.analyzer.add_record(record1)
        self.analyzer.add_record(record2)

        self.analyzer.clear_records()

        assert len(self.analyzer.defect_records) == 0


class TestDefectAnalyzerStatistics:
    """验证缺陷统计功能。"""

    def setup_method(self) -> None:
        """每个测试前创建分析器实例并添加测试数据。"""
        self.analyzer = DefectAnalyzer()

        # 添加测试记录
        records = [
            DefectRecord(uid=1, depth_mm=30.0, amplitude=0.7),
            DefectRecord(uid=2, depth_mm=50.0, amplitude=0.8),
            DefectRecord(uid=3, depth_mm=70.0, amplitude=0.6),
            DefectRecord(uid=4, depth_mm=40.0, amplitude=0.9),
        ]
        for record in records:
            self.analyzer.add_record(record)

    def test_total_count(self) -> None:
        """统计总数应正确。"""
        stats = self.analyzer.get_statistics()
        assert stats.total_count == 4

    def test_depth_range(self) -> None:
        """深度范围应正确。"""
        stats = self.analyzer.get_statistics()
        assert stats.depth_min_mm == 30.0
        assert stats.depth_max_mm == 70.0

    def test_depth_mean(self) -> None:
        """平均深度应正确。"""
        stats = self.analyzer.get_statistics()
        expected_mean = (30.0 + 50.0 + 70.0 + 40.0) / 4.0
        assert stats.depth_mean_mm == pytest.approx(expected_mean, abs=0.1)

    def test_amplitude_mean(self) -> None:
        """平均波幅应正确。"""
        stats = self.analyzer.get_statistics()
        expected_mean = (0.7 + 0.8 + 0.6 + 0.9) / 4.0
        assert stats.amplitude_mean == pytest.approx(expected_mean, abs=0.01)

    def test_depth_distribution(self) -> None:
        """深度分布应包含数据。"""
        stats = self.analyzer.get_statistics()
        assert len(stats.depth_distribution) > 0

    def test_amplitude_distribution(self) -> None:
        """波幅分布应包含数据。"""
        stats = self.analyzer.get_statistics()
        assert len(stats.amplitude_distribution) > 0


class TestDefectAnalyzerTrend:
    """验证缺陷趋势分析功能。"""

    def setup_method(self) -> None:
        """每个测试前创建分析器实例并添加测试数据。"""
        self.analyzer = DefectAnalyzer()

        # 添加带时间戳的测试记录
        records = [
            DefectRecord(uid=1, depth_mm=30.0, amplitude=0.7, timestamp="2024-01-01 10:00:00"),
            DefectRecord(uid=2, depth_mm=50.0, amplitude=0.8, timestamp="2024-01-01 10:01:00"),
            DefectRecord(uid=3, depth_mm=70.0, amplitude=0.6, timestamp="2024-01-01 10:02:00"),
        ]
        for record in records:
            self.analyzer.add_record(record)

    def test_depth_trend(self) -> None:
        """深度趋势应返回正确的时间戳和深度。"""
        timestamps, depths = self.analyzer.get_depth_trend()

        assert len(timestamps) == 3
        assert len(depths) == 3
        assert depths == [30.0, 50.0, 70.0]


class TestDefectAnalyzerDAC:
    """验证DAC曲线生成功能。"""

    def test_generate_dac_curve(self) -> None:
        """DAC曲线应返回正确形状的数组。"""
        depths, amplitudes = DefectAnalyzer.generate_dac_curve(
            depth_range_mm=(0, 200),
            reference_depth_mm=50.0,
            reference_amplitude=1.0,
        )

        assert len(depths) == 200
        assert len(amplitudes) == 200
        assert depths[0] == pytest.approx(0.0, abs=0.1)
        assert depths[-1] == pytest.approx(200.0, abs=0.1)

    def test_dac_curve_amplitude_decreases_with_depth(self) -> None:
        """DAC曲线波幅应随深度增加而减小。"""
        depths, amplitudes = DefectAnalyzer.generate_dac_curve(
            depth_range_mm=(10, 200),
            reference_depth_mm=50.0,
            reference_amplitude=1.0,
        )

        # 在参考深度之后，波幅应该减小
        ref_index = np.argmin(np.abs(depths - 50.0))
        for i in range(ref_index + 1, len(amplitudes)):
            assert amplitudes[i] <= amplitudes[ref_index] + 0.1  # 允许小误差

    def test_check_defect_against_dac(self) -> None:
        """缺陷DAC检查应正确判定。"""
        analyzer = DefectAnalyzer()

        # 创建简单的DAC曲线
        dac_depths = np.array([0, 50, 100, 150, 200], dtype=np.float32)
        dac_amplitudes = np.array([1.0, 1.0, 0.8, 0.6, 0.4], dtype=np.float32)

        # 测试低于DAC的缺陷
        result = analyzer.check_defect_against_dac(50.0, 0.5, dac_depths, dac_amplitudes)
        assert result["in_range"] == True
        assert result["exceeded"] == False

        # 测试超过DAC的缺陷
        result = analyzer.check_defect_against_dac(50.0, 1.2, dac_depths, dac_amplitudes)
        assert result["in_range"] == True
        assert result["exceeded"] == True

    def test_check_defect_out_of_range(self) -> None:
        """超出DAC范围的缺陷应正确处理。"""
        analyzer = DefectAnalyzer()

        dac_depths = np.array([0, 50, 100], dtype=np.float32)
        dac_amplitudes = np.array([1.0, 1.0, 0.8], dtype=np.float32)

        # 测试超出范围的缺陷
        result = analyzer.check_defect_against_dac(150.0, 0.5, dac_depths, dac_amplitudes)
        assert result["in_range"] == False