"""验收标准与自动评级模块。

把"缺陷特征 → 质量等级 → 合格 / 不合格"的判定逻辑做成可编辑的规则表，
控制器在刷新统计与生成报告时调用。模块本身不解析标准原文，只按加载进来的
规则表计算，因此：

1. 内置标准的判据线（评定线 / 定量线 / 判废线）与长度限值均为**示例占位值**，
   正式使用前必须对照标准原文校核后修改，程序不对标准符合性作保证；
2. 规则表可以整体替换（`register_profile` / `profile_from_dict`），便于将来
   通过界面或配置文件录入真实判据。

判定流程分两步，取较劣者作为缺陷等级：

- 波幅判定：把相对 DAC（或参考回波）的分贝偏移落到 Ⅰ / Ⅱ / Ⅲ / 判废 区，
  再由 `zone_level_map` 映射为质量等级；
- 长度判定：按壁厚分档查 `length_limits`，得到允许的最大指示长度所对应的等级。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# 判定结论常量，避免各处硬编码字符串。
VERDICT_PASS = "合格"
VERDICT_FAIL = "不合格"
VERDICT_UNDETERMINED = "待定"

# 波幅区名称，供界面与报告统一引用。
ZONE_1 = "Ⅰ"
ZONE_2 = "Ⅱ"
ZONE_3 = "Ⅲ"
ZONE_REJECT = "判废"
ZONE_UNKNOWN = "未知"


@dataclass
class LengthLimit:
    """某一壁厚分档下的指示长度限值。

    `max_wall_thickness_mm` 为该分档覆盖的最大壁厚（含），`None` 表示不设上限
    （即兜底分档）；`max_length_mm_by_level` 为"质量等级 -> 该等级允许的最大
    指示长度（mm）"，等级由优到劣排列。
    """

    max_wall_thickness_mm: float | None
    max_length_mm_by_level: dict[str, float] = field(default_factory=dict)


@dataclass
class AcceptanceProfile:
    """一套验收规则。"""

    key: str
    name: str
    levels: list[str] = field(default_factory=lambda: ["Ⅰ", "Ⅱ", "Ⅲ", "Ⅳ"])
    acceptance_level: str = "Ⅱ"
    # 三条判据线相对 DAC / 参考回波的分贝偏移。
    zone_evaluation_db: float = -4.0
    zone_quantification_db: float = 2.0
    zone_rejection_db: float = 10.0
    # 波幅区 -> 质量等级。
    zone_level_map: dict[str, str] = field(default_factory=dict)
    length_limits: list[LengthLimit] = field(default_factory=list)
    note: str = ""

    def level_rank(self, level: str) -> int:
        """返回等级由优到劣的序号；未知等级视为最劣。"""
        try:
            return self.levels.index(level)
        except ValueError:
            return len(self.levels)

    def rank_to_level(self, rank: int) -> str:
        """把序号还原成等级名，越界时返回最劣等级。"""
        if 0 <= rank < len(self.levels):
            return self.levels[rank]
        return self.levels[-1]


@dataclass
class DefectEvaluationInput:
    """参与判定的一条缺陷特征。"""

    uid: int = 0
    depth_mm: float = 0.0
    amplitude: float = 0.0
    db_above_dac: float | None = None
    indication_length_mm: float | None = None
    wall_thickness_mm: float | None = None


@dataclass
class DefectEvaluation:
    """单条缺陷的判定结果。"""

    uid: int
    level: str
    verdict: str
    amplitude_zone: str
    db_above_dac: float | None
    indication_length_mm: float | None
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "uid": self.uid,
            "level": self.level,
            "verdict": self.verdict,
            "amplitude_zone": self.amplitude_zone,
            "db_above_dac": self.db_above_dac,
            "indication_length_mm": self.indication_length_mm,
            "reasons": list(self.reasons),
        }


@dataclass
class AcceptanceSummary:
    """整份记录的判定汇总。"""

    profile_key: str
    profile_name: str
    acceptance_level: str
    overall_verdict: str
    worst_level: str | None
    defect_count: int
    rejected_count: int
    evaluations: list[DefectEvaluation] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_key": self.profile_key,
            "profile_name": self.profile_name,
            "acceptance_level": self.acceptance_level,
            "overall_verdict": self.overall_verdict,
            "worst_level": self.worst_level,
            "defect_count": self.defect_count,
            "rejected_count": self.rejected_count,
            "evaluations": [item.to_dict() for item in self.evaluations],
            "notes": list(self.notes),
        }


def _amplitude_zone(db_above_dac: float | None, profile: AcceptanceProfile) -> str:
    """把分贝偏移映射到波幅区。"""
    if db_above_dac is None:
        return ZONE_UNKNOWN
    if db_above_dac >= profile.zone_rejection_db:
        return ZONE_REJECT
    if db_above_dac >= profile.zone_quantification_db:
        return ZONE_3
    if db_above_dac >= profile.zone_evaluation_db:
        return ZONE_2
    return ZONE_1


def _length_limit_for_thickness(
    wall_thickness_mm: float | None,
    profile: AcceptanceProfile,
) -> dict[str, float]:
    """按壁厚选取长度分档；没有壁厚信息时使用兜底分档。"""
    if not profile.length_limits:
        return {}
    if wall_thickness_mm is not None:
        for limit in sorted(
            (item for item in profile.length_limits if item.max_wall_thickness_mm is not None),
            key=lambda item: float(item.max_wall_thickness_mm),  # type: ignore[arg-type]
        ):
            if wall_thickness_mm <= float(limit.max_wall_thickness_mm):  # type: ignore[arg-type]
                return limit.max_length_mm_by_level
    for limit in profile.length_limits:
        if limit.max_wall_thickness_mm is None:
            return limit.max_length_mm_by_level
    # 没有兜底分档时退回最后一个分档，保证判定有依据。
    return profile.length_limits[-1].max_length_mm_by_level


def _level_for_length(
    indication_length_mm: float,
    wall_thickness_mm: float | None,
    profile: AcceptanceProfile,
) -> str | None:
    """由指示长度得到长度侧等级。"""
    limits = _length_limit_for_thickness(wall_thickness_mm, profile)
    if not limits:
        return None
    for level in profile.levels:
        allowed = limits.get(level)
        if allowed is None:
            continue
        if indication_length_mm <= allowed:
            return level
    return profile.levels[-1]


def evaluate_defect(
    data: DefectEvaluationInput,
    profile: AcceptanceProfile,
) -> DefectEvaluation:
    """对单条缺陷按给定规则判定等级与合格性。"""
    reasons: list[str] = []

    zone = _amplitude_zone(data.db_above_dac, profile)
    if zone == ZONE_UNKNOWN:
        reasons.append("缺少 DAC / 参考回波，波幅等级未参与判定。")
        amplitude_level: str | None = None
    else:
        amplitude_level = profile.zone_level_map.get(zone, profile.levels[-1])
        db_text = "——" if data.db_above_dac is None else f"{data.db_above_dac:+.1f} dB"
        reasons.append(
            f"波幅位于{zone}区（相对参考 {db_text}，判据线 "
            f"{profile.zone_evaluation_db:+.1f}/{profile.zone_quantification_db:+.1f}/"
            f"{profile.zone_rejection_db:+.1f} dB），对应{amplitude_level}级。"
        )

    if data.indication_length_mm is None:
        reasons.append("未测量指示长度，长度等级未参与判定。")
        length_level: str | None = None
    else:
        length_level = _level_for_length(
            data.indication_length_mm,
            data.wall_thickness_mm,
            profile,
        )
        if length_level is None:
            reasons.append("规则表未提供长度限值，长度等级未参与判定。")
        else:
            reasons.append(
                f"指示长度 {data.indication_length_mm:.1f} mm，对应{length_level}级。"
            )

    if amplitude_level is None and length_level is None:
        return DefectEvaluation(
            uid=data.uid,
            level=profile.levels[0],
            verdict=VERDICT_UNDETERMINED,
            amplitude_zone=zone,
            db_above_dac=data.db_above_dac,
            indication_length_mm=data.indication_length_mm,
            reasons=reasons,
        )

    candidates = [item for item in (amplitude_level, length_level) if item is not None]
    worst_rank = max(profile.level_rank(item) for item in candidates)
    level = profile.rank_to_level(worst_rank)
    verdict = (
        VERDICT_PASS
        if worst_rank <= profile.level_rank(profile.acceptance_level)
        else VERDICT_FAIL
    )
    if len(candidates) == 2 and amplitude_level != length_level:
        reasons.append(f"波幅与长度结果不一致，取较劣者{level}级。")
    reasons.append(f"按 {profile.name} 验收等级 {profile.acceptance_level} 判定：{verdict}。")

    return DefectEvaluation(
        uid=data.uid,
        level=level,
        verdict=verdict,
        amplitude_zone=zone,
        db_above_dac=data.db_above_dac,
        indication_length_mm=data.indication_length_mm,
        reasons=reasons,
    )


def evaluate_records(
    inputs: list[DefectEvaluationInput],
    profile: AcceptanceProfile,
) -> AcceptanceSummary:
    """对一批缺陷记录做整体判定。"""
    evaluations = [evaluate_defect(item, profile) for item in inputs]
    if not evaluations:
        return AcceptanceSummary(
            profile_key=profile.key,
            profile_name=profile.name,
            acceptance_level=profile.acceptance_level,
            overall_verdict=VERDICT_PASS,
            worst_level=None,
            defect_count=0,
            rejected_count=0,
            evaluations=[],
            notes=["未发现缺陷记录，判为合格。"],
        )

    rejected = [item for item in evaluations if item.verdict == VERDICT_FAIL]
    undetermined = [item for item in evaluations if item.verdict == VERDICT_UNDETERMINED]
    worst_rank = max(profile.level_rank(item.level) for item in evaluations if item.verdict != VERDICT_UNDETERMINED) \
        if any(item.verdict != VERDICT_UNDETERMINED for item in evaluations) else -1

    if rejected:
        overall = VERDICT_FAIL
    elif undetermined:
        overall = VERDICT_UNDETERMINED
    else:
        overall = VERDICT_PASS

    notes: list[str] = []
    if undetermined:
        notes.append(f"{len(undetermined)} 条记录特征不足，结论待定。")
    if profile.note:
        notes.append(profile.note)

    return AcceptanceSummary(
        profile_key=profile.key,
        profile_name=profile.name,
        acceptance_level=profile.acceptance_level,
        overall_verdict=overall,
        worst_level=profile.rank_to_level(worst_rank) if worst_rank >= 0 else None,
        defect_count=len(evaluations),
        rejected_count=len(rejected),
        evaluations=evaluations,
        notes=notes,
    )


# ── 内置规则表（示例值，须按标准原文校核） ─────────────────────────────────────

_PLACEHOLDER_NOTE = "判据线与长度限值为示例占位值，正式使用前必须对照标准原文校核后修改。"

_BUILTIN_PROFILES: dict[str, AcceptanceProfile] = {
    "GB/T 11345": AcceptanceProfile(
        key="GB/T 11345",
        name="GB/T 11345-2013 焊缝超声检测",
        levels=["Ⅰ", "Ⅱ", "Ⅲ", "Ⅳ"],
        acceptance_level="Ⅱ",
        zone_evaluation_db=-4.0,
        zone_quantification_db=2.0,
        zone_rejection_db=10.0,
        zone_level_map={"Ⅰ": "Ⅰ", "Ⅱ": "Ⅱ", "Ⅲ": "Ⅲ", ZONE_REJECT: "Ⅳ"},
        length_limits=[
            LengthLimit(
                max_wall_thickness_mm=25.0,
                max_length_mm_by_level={"Ⅰ": 5.0, "Ⅱ": 10.0, "Ⅲ": 20.0, "Ⅳ": float("inf")},
            ),
            LengthLimit(
                max_wall_thickness_mm=None,
                max_length_mm_by_level={"Ⅰ": 10.0, "Ⅱ": 20.0, "Ⅲ": 40.0, "Ⅳ": float("inf")},
            ),
        ],
        note=_PLACEHOLDER_NOTE,
    ),
    "NB/T 47013.3": AcceptanceProfile(
        key="NB/T 47013.3",
        name="NB/T 47013.3-2015 承压设备超声检测",
        levels=["Ⅰ", "Ⅱ", "Ⅲ", "Ⅳ"],
        acceptance_level="Ⅱ",
        zone_evaluation_db=-2.0,
        zone_quantification_db=4.0,
        zone_rejection_db=12.0,
        zone_level_map={"Ⅰ": "Ⅰ", "Ⅱ": "Ⅱ", "Ⅲ": "Ⅲ", ZONE_REJECT: "Ⅳ"},
        length_limits=[
            LengthLimit(
                max_wall_thickness_mm=25.0,
                max_length_mm_by_level={"Ⅰ": 6.0, "Ⅱ": 12.0, "Ⅲ": 24.0, "Ⅳ": float("inf")},
            ),
            LengthLimit(
                max_wall_thickness_mm=None,
                max_length_mm_by_level={"Ⅰ": 12.0, "Ⅱ": 24.0, "Ⅲ": 48.0, "Ⅳ": float("inf")},
            ),
        ],
        note=_PLACEHOLDER_NOTE,
    ),
    "通用": AcceptanceProfile(
        key="通用",
        name="通用（宽松）判定",
        levels=["Ⅰ", "Ⅱ", "Ⅲ", "Ⅳ"],
        acceptance_level="Ⅲ",
        zone_evaluation_db=-6.0,
        zone_quantification_db=0.0,
        zone_rejection_db=12.0,
        zone_level_map={"Ⅰ": "Ⅰ", "Ⅱ": "Ⅱ", "Ⅲ": "Ⅲ", ZONE_REJECT: "Ⅳ"},
        length_limits=[
            LengthLimit(
                max_wall_thickness_mm=None,
                max_length_mm_by_level={"Ⅰ": 10.0, "Ⅱ": 20.0, "Ⅲ": 50.0, "Ⅳ": float("inf")},
            ),
        ],
        note="通用判定仅用于演示与占位，正式报告请选用对应标准。",
    ),
}


def default_profile_key() -> str:
    """返回默认规则表键名。"""
    return next(iter(_BUILTIN_PROFILES))


def list_profile_keys() -> list[str]:
    """列出全部规则表键名。"""
    return list(_BUILTIN_PROFILES.keys())


def get_profile(key: str | None) -> AcceptanceProfile:
    """按键名取规则表；未知键名回退到默认规则表。"""
    if key and key in _BUILTIN_PROFILES:
        return _BUILTIN_PROFILES[key]
    return _BUILTIN_PROFILES[default_profile_key()]


def register_profile(profile: AcceptanceProfile) -> None:
    """注册或替换一套规则表。"""
    _BUILTIN_PROFILES[profile.key] = profile


def profile_to_dict(profile: AcceptanceProfile) -> dict[str, Any]:
    """序列化规则表，便于导出与编辑。"""
    return {
        "key": profile.key,
        "name": profile.name,
        "levels": list(profile.levels),
        "acceptance_level": profile.acceptance_level,
        "zone_evaluation_db": profile.zone_evaluation_db,
        "zone_quantification_db": profile.zone_quantification_db,
        "zone_rejection_db": profile.zone_rejection_db,
        "zone_level_map": dict(profile.zone_level_map),
        "length_limits": [
            {
                "max_wall_thickness_mm": limit.max_wall_thickness_mm,
                "max_length_mm_by_level": dict(limit.max_length_mm_by_level),
            }
            for limit in profile.length_limits
        ],
        "note": profile.note,
    }


def profile_from_dict(data: dict[str, Any]) -> AcceptanceProfile:
    """从字典还原规则表。"""
    limits = [
        LengthLimit(
            max_wall_thickness_mm=item.get("max_wall_thickness_mm"),
            max_length_mm_by_level={
                str(level): float(value)
                for level, value in dict(item.get("max_length_mm_by_level", {})).items()
            },
        )
        for item in data.get("length_limits", [])
    ]
    return AcceptanceProfile(
        key=str(data["key"]),
        name=str(data.get("name", data["key"])),
        levels=[str(level) for level in data.get("levels", ["Ⅰ", "Ⅱ", "Ⅲ", "Ⅳ"])],
        acceptance_level=str(data.get("acceptance_level", "Ⅱ")),
        zone_evaluation_db=float(data.get("zone_evaluation_db", -4.0)),
        zone_quantification_db=float(data.get("zone_quantification_db", 2.0)),
        zone_rejection_db=float(data.get("zone_rejection_db", 10.0)),
        zone_level_map={
            str(zone): str(level)
            for zone, level in dict(data.get("zone_level_map", {})).items()
        },
        length_limits=limits,
        note=str(data.get("note", "")),
    )
