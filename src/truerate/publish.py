from __future__ import annotations

import json
from pathlib import Path

DEFAULT_CHUNK_TARGET_BYTES = 16 * 1024 * 1024
_MAX_SINGLE_CHUNK_BYTES = 90 * 1024 * 1024


def _json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _atomic_write(path: Path, text: str) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(text, encoding="utf-8")
    temp.replace(path)


def write_sharded_site_payload(
    payload: dict,
    manifest_path: Path,
    *,
    target_bytes: int = DEFAULT_CHUNK_TARGET_BYTES,
) -> list[Path]:
    """Write a small manifest plus bounded series chunks for GitHub Pages."""
    if target_bytes <= 0:
        raise ValueError("target_bytes must be positive")

    directory = manifest_path.parent
    directory.mkdir(parents=True, exist_ok=True)

    for stale in directory.glob("site-series-*.json"):
        stale.unlink()

    series = payload.get("series") or {}
    chunks: list[dict] = []
    current: dict = {}
    current_bytes = len('{"series":{}}'.encode("utf-8"))

    for pair in sorted(series):
        pair_entry = {pair: series[pair]}
        pair_bytes = len(_json_text(pair_entry).encode("utf-8")) + 1

        if pair_bytes > _MAX_SINGLE_CHUNK_BYTES:
            raise ValueError(
                f"Series payload for {pair} is too large for a safe GitHub file: "
                f"{pair_bytes} bytes"
            )

        if current and current_bytes + pair_bytes > target_bytes:
            chunks.append(current)
            current = {}
            current_bytes = len('{"series":{}}'.encode("utf-8"))

        current[pair] = series[pair]
        current_bytes += pair_bytes

    if current or not chunks:
        chunks.append(current)

    chunk_paths: list[Path] = []
    chunk_names: list[str] = []
    for index, chunk in enumerate(chunks):
        name = f"site-series-{index:03d}.json"
        path = directory / name
        text = _json_text({"series": chunk})
        encoded_size = len(text.encode("utf-8"))
        if encoded_size > _MAX_SINGLE_CHUNK_BYTES:
            raise ValueError(
                f"Generated chunk {name} exceeds the safe GitHub file size: "
                f"{encoded_size} bytes"
            )
        _atomic_write(path, text)
        chunk_paths.append(path)
        chunk_names.append(name)

    manifest = {key: value for key, value in payload.items() if key != "series"}
    manifest["series"] = {}
    manifest["series_chunks"] = chunk_names
    _atomic_write(manifest_path, _json_text(manifest))
    return chunk_paths
