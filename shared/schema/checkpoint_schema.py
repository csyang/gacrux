"""
Shared checkpoint metadata schema for Gacrux.

Used by both Spike A (software) and Spike B (RTL) to describe a checkpoint
in a track-agnostic way. The underlying state blob format differs between
tracks; only this metadata envelope is shared.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CheckpointRecord:
    """Metadata for a single checkpoint.

    Attributes:
        checkpoint_id: Unique identifier (e.g. monotonic index or UUID).
        sequence_index: Position in the ordered checkpoint sequence, used
            directly by the bisection engine.
        timestamp: Wall-clock or simulation-time marker (track-defined).
        state_path: Path/pointer to the actual state blob (pickle file,
            VCS $save snapshot, QuestaSim checkpoint directory, etc.).
        track: Which spike produced this checkpoint ("software" | "rtl").
        predicate_cache: Optional cached result of evaluate_predicate(),
            to avoid re-evaluating an expensive predicate on revisit.
        extra: Track-specific metadata that doesn't need to be shared
            (e.g. cycle count for RTL, step count for software).
    """

    checkpoint_id: str
    sequence_index: int
    timestamp: float
    state_path: str
    track: str
    predicate_cache: Optional[bool] = None
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "checkpoint_id": self.checkpoint_id,
            "sequence_index": self.sequence_index,
            "timestamp": self.timestamp,
            "state_path": self.state_path,
            "track": self.track,
            "predicate_cache": self.predicate_cache,
            "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CheckpointRecord":
        return cls(
            checkpoint_id=data["checkpoint_id"],
            sequence_index=data["sequence_index"],
            timestamp=data["timestamp"],
            state_path=data["state_path"],
            track=data["track"],
            predicate_cache=data.get("predicate_cache"),
            extra=data.get("extra", {}),
        )


# TODO(Phase 1.0): decide on-disk format for a full checkpoint manifest
# (list of CheckpointRecord) — likely a single JSON file per run, indexed
# by sequence_index, alongside the individual state blobs.
