"""跨会话缺陷跟踪。

把同一工件在不同检测会话中记录的缺陷按空间位置归组，观察"同一位置"的缺陷在
多次检测之间的波幅与指示长度变化，作为复检对比的线索。

使用边界（重要）：

- 归组依据只是深度（可选叠加扫查位置）接近，位置接近并不等于物理上是同一条缺陷；
- 记录中没有扫查坐标时只能按深度分组，不同深度的两条缺陷一般不会合并，但同一
  深度附近的独立缺陷仍可能被并入同一组；
- 输出的是趋势线索，不能据此直接得出"缺陷在扩展"的结论，必须结合复检工艺、
  探头参数与人工判读。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# 波幅上升到该幅度以上时，在组说明里给出提示。
AMPLITUDE_ALERT_DELTA = 0.10


def _to_float(value: Any) -> float | None:
    """把可能是 None 的数值转成 float。"""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass
class TrackOccurrence:
    """一条缺陷在某次检测中的出现记录。"""

    session_id: str
    session_started_at: str
    record_uid: int
    detected_at: str
    depth_mm: float
    amplitude: float
    indication_length_mm: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "session_started_at": self.session_started_at,
            "record_uid": self.record_uid,
            "detected_at": self.detected_at,
            "depth_mm": self.depth_mm,
            "amplitude": self.amplitude,
            "indication_length_mm": self.indication_length_mm,
        }


@dataclass
class DefectTrack:
    """一组被判定为位置接近的缺陷记录。"""

    track_id: int
    depth_mm: float
    occurrences: list[TrackOccurrence] = field(default_factory=list)
    session_count: int = 0
    amplitude_change: float | None = None
    length_change: float | None = None
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "track_id": self.track_id,
            "depth_mm": self.depth_mm,
            "session_count": self.session_count,
            "amplitude_change": self.amplitude_change,
            "length_change": self.length_change,
            "note": self.note,
            "occurrences": [item.to_dict() for item in self.occurrences],
        }


@dataclass
class TrackingResult:
    """一次跨会话跟踪的汇总结果。"""

    tracks: list[DefectTrack] = field(default_factory=list)
    cross_session_count: int = 0
    repeated_count: int = 0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tracks": [track.to_dict() for track in self.tracks],
            "cross_session_count": self.cross_session_count,
            "repeated_count": self.repeated_count,
            "notes": list(self.notes),
        }


def track_defects(
    records: list[dict[str, Any]],
    depth_tolerance_mm: float = 5.0,
    min_occurrences: int = 2,
) -> TrackingResult:
    """把缺陷记录按深度归组，输出跨会话重复出现的缺陷。

    参数：
    - records: 缺陷记录字典，需含 depth_mm / amplitude / session_id 等字段；
    - depth_tolerance_mm: 深度归组容差（mm），两条记录深度差不超过该值即认为同组；
    - min_occurrences: 至少出现多少次才输出。

    返回：
    - TrackingResult。
    """
    tolerance = max(float(depth_tolerance_mm), 0.0)
    minimum = max(int(min_occurrences), 1)

    prepared: list[TrackOccurrence] = []
    for record in records:
        depth = _to_float(record.get("depth_mm", record.get("depthMm")))
        if depth is None:
            continue
        amplitude = _to_float(record.get("amplitude")) or 0.0
        prepared.append(
            TrackOccurrence(
                session_id=str(record.get("session_id", record.get("sessionId", ""))),
                session_started_at=str(record.get("session_started_at", "")),
                record_uid=int(record.get("record_uid", record.get("recordUid", 0)) or 0),
                detected_at=str(record.get("detected_at", record.get("timestamp", ""))),
                depth_mm=depth,
                amplitude=amplitude,
                indication_length_mm=_to_float(record.get("indication_length_mm")),
            )
        )

    # 按会话与记录时间排序，保证组内先后顺序就是检测先后顺序。
    prepared.sort(
        key=lambda item: (item.session_started_at, item.detected_at, item.record_uid)
    )

    # 贪心归组：优先并入深度最接近且不超过容差的已有组。
    grouped: list[list[TrackOccurrence]] = []
    group_depths: list[float] = []
    for occurrence in prepared:
        best_index = -1
        best_distance = tolerance + 1.0
        for index, group_depth in enumerate(group_depths):
            distance = abs(group_depth - occurrence.depth_mm)
            if distance <= tolerance and distance < best_distance:
                best_index = index
                best_distance = distance
        if best_index < 0:
            grouped.append([occurrence])
            group_depths.append(occurrence.depth_mm)
        else:
            grouped[best_index].append(occurrence)
            depths = [item.depth_mm for item in grouped[best_index]]
            group_depths[best_index] = sum(depths) / len(depths)

    tracks: list[DefectTrack] = []
    for occurrences in grouped:
        if len(occurrences) < minimum:
            continue
        depths = [item.depth_mm for item in occurrences]
        session_ids = {item.session_id for item in occurrences if item.session_id}
        first = occurrences[0]
        last = occurrences[-1]

        amplitude_change = None
        if len(occurrences) >= 2:
            amplitude_change = last.amplitude - first.amplitude

        length_change = None
        if first.indication_length_mm is not None and last.indication_length_mm is not None:
            length_change = last.indication_length_mm - first.indication_length_mm

        notes: list[str] = []
        if len(session_ids) >= 2:
            notes.append(f"该位置缺陷在 {len(session_ids)} 次检测中重复出现。")
        if amplitude_change is not None and amplitude_change >= AMPLITUDE_ALERT_DELTA:
            notes.append(f"波幅较首次上升 {amplitude_change:+.3f}。")
        if length_change is not None and length_change > 0.0:
            notes.append(f"指示长度较首次增加 {length_change:.1f} mm。")

        tracks.append(
            DefectTrack(
                track_id=len(tracks) + 1,
                depth_mm=sum(depths) / len(depths),
                occurrences=occurrences,
                session_count=len(session_ids),
                amplitude_change=amplitude_change,
                length_change=length_change,
                note=" ".join(notes),
            )
        )

    tracks.sort(key=lambda track: track.depth_mm)
    for index, track in enumerate(tracks, start=1):
        track.track_id = index

    result = TrackingResult(
        tracks=tracks,
        cross_session_count=sum(1 for track in tracks if track.session_count >= 2),
        repeated_count=len(tracks),
    )
    result.notes.append(
        f"按深度 ±{tolerance:.1f} mm 归组；位置接近不等于同一条缺陷，结果仅供复检参考。"
    )
    if not tracks:
        result.notes.append("没有出现两次以上的缺陷记录，暂无可跟踪对象。")
    return result
