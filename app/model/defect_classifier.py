"""缺陷类型提示（规则法）。

依据超声检测的常规经验，把指示长度、指示高度、深度位置与波幅等特征代入一组
可读的规则，给出若干候选类型及其匹配程度。

使用边界（重要）：

- 这是**规则法提示**，不是自动定性。超声检测中缺陷类型的最终确定必须结合坡口
  形式、探头角度 / 频率、扫查方向、工件工艺（铸 / 锻 / 焊）与人工判读；
- 规则与权重是可读的经验值，不是标准条文；
- 特征缺失（例如未测量指示长度）会明显降低可信度，模块会在 `notes` 中说明。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

# 候选类型标签。
TYPE_POINT = "气孔 / 点状夹渣"
TYPE_SLAG = "条状夹渣"
TYPE_CRACK = "裂纹"
TYPE_FUSION = "未熔合 / 未焊透"
TYPE_LAMINATION = "分层（母材）"
TYPE_UNKNOWN = "类型不明"

# 归一化得分达到该值才作为主要类型。
PRIMARY_SCORE_THRESHOLD = 0.5


@dataclass
class DefectFeatures:
    """参与类型提示的缺陷特征。"""

    depth_mm: float = 0.0
    amplitude: float = 0.0
    indication_length_mm: float | None = None
    indication_height_mm: float | None = None
    wall_thickness_mm: float | None = None


@dataclass
class TypeHint:
    """一个候选类型及其匹配程度。"""

    label: str
    score: float
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"label": self.label, "score": self.score, "reasons": list(self.reasons)}


@dataclass
class ClassificationResult:
    """一次类型提示的结果。"""

    primary: str
    hints: list[TypeHint] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary": self.primary,
            "hints": [hint.to_dict() for hint in self.hints],
            "notes": list(self.notes),
        }

    def short_text(self) -> str:
        """压缩成一行的类型提示文本，供表格与状态栏使用。"""
        if self.primary == TYPE_UNKNOWN or not self.hints:
            return TYPE_UNKNOWN
        best = self.hints[0]
        return f"{self.primary}（匹配度 {best.score * 100:.0f}%）"


# 单条规则：(说明文字, 权重, 判定函数)。
Rule = tuple[str, float, Callable[[DefectFeatures], bool]]


def _flatness(features: DefectFeatures) -> float | None:
    """返回高度 / 长度比值；特征不足时返回 None。"""
    if features.indication_length_mm is None or features.indication_height_mm is None:
        return None
    if features.indication_length_mm <= 1e-9:
        return None
    return features.indication_height_mm / features.indication_length_mm


def _relative_depth(features: DefectFeatures) -> float | None:
    """返回缺陷深度占壁厚的比例；没有壁厚时返回 None。"""
    if features.wall_thickness_mm is None or features.wall_thickness_mm <= 1e-9:
        return None
    return features.depth_mm / features.wall_thickness_mm


def _rules() -> list[tuple[str, list[Rule]]]:
    """返回类型 -> 规则表。规则表集中在此，便于对照经验逐条校核与修改。"""

    def length_at_most(limit_mm: float) -> Callable[[DefectFeatures], bool]:
        return lambda features: (
            features.indication_length_mm is not None
            and features.indication_length_mm <= limit_mm
        )

    def length_at_least(limit_mm: float) -> Callable[[DefectFeatures], bool]:
        return lambda features: (
            features.indication_length_mm is not None
            and features.indication_length_mm >= limit_mm
        )

    def flatness_at_most(limit: float) -> Callable[[DefectFeatures], bool]:
        return lambda features: (
            (ratio := _flatness(features)) is not None and ratio <= limit
        )

    def flatness_at_least(limit: float) -> Callable[[DefectFeatures], bool]:
        return lambda features: (
            (ratio := _flatness(features)) is not None and ratio >= limit
        )

    def amplitude_at_least(limit: float) -> Callable[[DefectFeatures], bool]:
        return lambda features: features.amplitude >= limit

    def amplitude_between(low: float, high: float) -> Callable[[DefectFeatures], bool]:
        return lambda features: low <= features.amplitude <= high

    def relative_depth_below(limit: float) -> Callable[[DefectFeatures], bool]:
        return lambda features: (
            (ratio := _relative_depth(features)) is not None and ratio < limit
        )

    def relative_depth_above(limit: float) -> Callable[[DefectFeatures], bool]:
        return lambda features: (
            (ratio := _relative_depth(features)) is not None and ratio > limit
        )

    def relative_depth_middle(low: float, high: float) -> Callable[[DefectFeatures], bool]:
        return lambda features: (
            (ratio := _relative_depth(features)) is not None and low <= ratio <= high
        )

    return [
        (
            TYPE_POINT,
            [
                ("指示长度不超过 5 mm，呈点状", 0.5, length_at_most(5.0)),
                ("指示高度与长度相当", 0.3, flatness_at_least(0.5)),
                ("波幅中等（0.2~0.8）", 0.2, amplitude_between(0.2, 0.8)),
            ],
        ),
        (
            TYPE_SLAG,
            [
                ("指示长度不小于 8 mm，呈条状", 0.4, length_at_least(8.0)),
                ("指示较为扁平（高度/长度 ≤ 0.3）", 0.4, flatness_at_most(0.3)),
                ("波幅中等（0.2~0.8）", 0.2, amplitude_between(0.2, 0.8)),
            ],
        ),
        (
            TYPE_CRACK,
            [
                ("指示长度不小于 8 mm", 0.3, length_at_least(8.0)),
                ("指示具有高度（高度/长度 ≥ 0.3）", 0.4, flatness_at_least(0.3)),
                ("波幅较高（≥ 0.6）", 0.3, amplitude_at_least(0.6)),
            ],
        ),
        (
            TYPE_FUSION,
            [
                ("指示长度不小于 8 mm", 0.4, length_at_least(8.0)),
                ("位于近表面或近底面", 0.3,
                 lambda features: relative_depth_below(0.25)(features)
                 or relative_depth_above(0.75)(features)),
                ("指示较为扁平（高度/长度 ≤ 0.3）", 0.3, flatness_at_most(0.3)),
            ],
        ),
        (
            TYPE_LAMINATION,
            [
                ("位于壁厚中段（0.3~0.7 倍壁厚）", 0.4, relative_depth_middle(0.3, 0.7)),
                ("指示较为扁平（高度/长度 ≤ 0.3）", 0.3, flatness_at_most(0.3)),
                ("指示很长（≥ 20 mm）", 0.3, length_at_least(20.0)),
            ],
        ),
    ]


def classify_defect(features: DefectFeatures) -> ClassificationResult:
    """按规则表给出类型提示。

    参数：
    - features: 缺陷特征。

    返回：
    - ClassificationResult，`hints` 按匹配度从高到低排列。
    """
    hints: list[TypeHint] = []
    for label, rules in _rules():
        total_weight = sum(weight for _, weight, _ in rules)
        matched_weight = 0.0
        reasons: list[str] = []
        for reason, weight, predicate in rules:
            if predicate(features):
                matched_weight += weight
                reasons.append(reason)
        if matched_weight <= 0.0:
            continue
        hints.append(
            TypeHint(
                label=label,
                score=matched_weight / total_weight if total_weight > 0 else 0.0,
                reasons=reasons,
            )
        )

    hints.sort(key=lambda hint: hint.score, reverse=True)
    primary = TYPE_UNKNOWN
    if hints and hints[0].score >= PRIMARY_SCORE_THRESHOLD:
        primary = hints[0].label

    notes: list[str] = []
    if features.indication_length_mm is None:
        notes.append("未测量指示长度，类型提示可信度下降。")
    if features.indication_height_mm is None:
        notes.append("未测量指示高度，类型提示可信度下降。")
    if features.wall_thickness_mm is None:
        notes.append("未设置工件壁厚，位置类规则未参与判断。")
    notes.append("类型由规则表推断，仅作提示，最终定性须结合工艺、坡口与人工判读。")

    return ClassificationResult(primary=primary, hints=hints, notes=notes)
