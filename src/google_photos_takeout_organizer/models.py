from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class Code(StrEnum):
    INVALID_ZIP = "INVALID_ZIP"; ZIP_PATH_TRAVERSAL = "ZIP_PATH_TRAVERSAL"
    INVALID_JSON = "INVALID_JSON"; AMBIGUOUS_SIDECAR = "AMBIGUOUS_SIDECAR"
    MEDIA_WITHOUT_JSON = "MEDIA_WITHOUT_JSON"; JSON_ORPHAN = "JSON_ORPHAN"
    CORRUPT_MEDIA = "CORRUPT_MEDIA"; UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    NO_DATE = "NO_DATE"; DATE_CONFLICT = "DATE_CONFLICT"; EXACT_DUPLICATE = "EXACT_DUPLICATE"
    OUTPUT_COLLISION = "OUTPUT_COLLISION"; COPY_FAILED = "COPY_FAILED"; HASH_MISMATCH = "HASH_MISMATCH"


@dataclass
class MediaRecord:
    id: str; archive_id: str; source_path: str; relative_path: str; original_filename: str
    extension: str; size: int; media_type: str
    sha256: str | None = None; width: int | None = None; height: int | None = None
    json_path: str | None = None; json_status: str = "MEDIA_WITHOUT_JSON"; exif_status: str = "NOT_FOUND"
    json_date: str | None = None; exif_date: str | None = None; filename_date: str | None = None
    folder_date: str | None = None; filesystem_date: str | None = None; resolved_date: str | None = None
    date_precision: str = "UNKNOWN"; date_source: str = "UNKNOWN"; date_confidence: str = "UNKNOWN"
    album_names: list[str] = field(default_factory=list); duplicate_group_id: str | None = None
    duplicate_status: str = "UNIQUE"; is_primary: bool = True; planned_output_path: str | None = None
    output_filename: str | None = None; export_status: str = "PLANNED"
    warnings: list[str] = field(default_factory=list); errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]: return asdict(self)
    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "MediaRecord": return cls(**value)


@dataclass
class DuplicateGroup:
    group_id: str; sha256: str; members: list[str]; primary: str; duplicates: list[str]
    album_names: list[str] = field(default_factory=list); resolved_date: str | None = None
    date_source: str = "UNKNOWN"; date_confidence: str = "UNKNOWN"; metadata_sources: list[str] = field(default_factory=list)
    def to_dict(self) -> dict[str, Any]: return asdict(self)
    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "DuplicateGroup": return cls(**value)
