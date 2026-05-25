"""All artifact IO lives here (Review fix #4). Stages never touch disk.

Paths are namespaced by post id and coverage slug, so a `--limit` slice can
never collide with a full run; loads also assert the coverage matches.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import TypeVar

import tomli_w
from pydantic import BaseModel

from .api import RawApiPost, RawApiReply, RawPost
from .models import AudioManifest, Coverage, Lines, Script, Story, VoiceMap

M = TypeVar("M", bound=BaseModel)


class Storage:
    def __init__(self, post_id: int, coverage: Coverage, root: Path = Path("data")):
        self.post_id = post_id
        self.coverage = coverage
        self.base = Path(root) / str(post_id)
        self.dir = self.base / coverage.slug()
        # Clips are content-hashed, so the cache is shared across coverages: a
        # bigger run reuses clips already synthesized for a smaller one.
        self.audio_dir = self.base / "audio"
        self.output_path = self.dir / "output.mp3"

    # --- raw fetch cache ---
    @property
    def raw_post_path(self) -> Path:
        return self.dir / "01_raw" / "post.json"

    def raw_page_path(self, page: int) -> Path:
        return self.dir / "01_raw" / "replies" / f"page_{page:04d}.json"

    # --- generic json artifacts ---
    @staticmethod
    def _save(path: Path, model: BaseModel) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(model.model_dump_json(indent=2))

    @staticmethod
    def _load(path: Path, cls: type[M]) -> M:
        return cls.model_validate_json(path.read_text())

    def _load_checked(self, path: Path, cls: type[M]) -> M:
        obj = self._load(path, cls)
        if obj.coverage != self.coverage:  # type: ignore[attr-defined]
            raise ValueError(
                f"{path} has coverage {obj.coverage} but this run is {self.coverage}."  # type: ignore[attr-defined]
            )
        return obj

    def save_raw_post(self, post: RawApiPost) -> None:
        self._save(self.raw_post_path, post)

    def load_raw_post(self) -> RawApiPost:
        return self._load(self.raw_post_path, RawApiPost)

    def save_raw_page(self, page: int, replies: list[RawApiReply]) -> None:
        path = self.raw_page_path(page)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_dump_list(replies))

    def load_raw_page(self, page: int) -> list[RawApiReply]:
        return [RawApiReply.model_validate(r) for r in json.loads(self.raw_page_path(page).read_text())]

    def save(self, obj: RawPost | Story | Script | Lines | AudioManifest) -> None:
        self._save(self._path_for(type(obj)), obj)

    def load_raw(self) -> RawPost:
        return self._load_checked(self._path_for(RawPost), RawPost)

    def load_manifest(self) -> AudioManifest:
        return self._load_checked(self._path_for(AudioManifest), AudioManifest)

    def load_story(self) -> Story:
        return self._load_checked(self._path_for(Story), Story)

    def load_script(self) -> Script:
        return self._load_checked(self._path_for(Script), Script)

    def load_lines(self) -> Lines:
        return self._load_checked(self._path_for(Lines), Lines)

    def _path_for(self, cls: type) -> Path:
        return {
            RawPost: self.dir / "01_raw" / "raw_post.json",
            Story: self.dir / "02_story.json",
            Script: self.dir / "03_script.json",
            Lines: self.dir / "04_lines.json",
            AudioManifest: self.dir / "05_manifest.json",
        }[cls]

    # --- voices.toml (shared across coverages, hand-editable) ---
    @property
    def voices_path(self) -> Path:
        return self.base / "voices.toml"

    def load_voicemap(self) -> VoiceMap | None:
        if not self.voices_path.exists():
            return None
        return VoiceMap.model_validate(tomllib.loads(self.voices_path.read_text()))

    def save_voicemap(self, voicemap: VoiceMap) -> None:
        self.voices_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"voices": voicemap.model_dump(exclude_none=True)["voices"]}
        self.voices_path.write_text(tomli_w.dumps(data))


def _dump_list(replies: list[RawApiReply]) -> str:
    return json.dumps([r.model_dump() for r in replies], indent=2, ensure_ascii=False)
