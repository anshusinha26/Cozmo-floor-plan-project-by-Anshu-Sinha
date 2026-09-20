"""Input manifest and config hashing: the provenance half of reproducibility."""

from __future__ import annotations

import hashlib

import pytest

from cozmo.io.manifest import (
    build_input_manifest,
    config_sha256,
    library_versions,
    load_config,
    sha256_file,
)


def test_sha256_file_matches_hashlib(tmp_path):
    f = tmp_path / "a.bin"
    f.write_bytes(b"hello")
    assert sha256_file(f) == hashlib.sha256(b"hello").hexdigest()


def test_manifest_lists_every_file_sorted_with_relative_paths(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "b.jpg").write_bytes(b"b")
    (tmp_path / "a.jpg").write_bytes(b"a")
    (tmp_path / "sub" / "c.txt").write_bytes(b"c")
    man = build_input_manifest(tmp_path)
    assert [f["path"] for f in man["files"]] == ["a.jpg", "b.jpg", "sub/c.txt"]
    assert man["files"][0]["sha256"] == hashlib.sha256(b"a").hexdigest()
    assert man["files"][0]["size_bytes"] == 1
    assert len(man["sha256"]) == 64


def test_manifest_hash_depends_on_content_not_location(tmp_path):
    d1 = tmp_path / "one"
    d2 = tmp_path / "two"
    d1.mkdir()
    d2.mkdir()
    (d1 / "x.mp4").write_bytes(b"video")
    (d2 / "x.mp4").write_bytes(b"video")
    assert build_input_manifest(d1)["sha256"] == build_input_manifest(d2)["sha256"]
    (d2 / "x.mp4").write_bytes(b"video2")
    assert build_input_manifest(d1)["sha256"] != build_input_manifest(d2)["sha256"]


def test_manifest_accepts_single_file(tmp_path):
    f = tmp_path / "clip.mp4"
    f.write_bytes(b"v")
    man = build_input_manifest(f)
    assert [x["path"] for x in man["files"]] == ["clip.mp4"]


def test_manifest_rejects_missing_or_empty_input(tmp_path):
    with pytest.raises(FileNotFoundError):
        build_input_manifest(tmp_path / "nope")
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ValueError, match="no files"):
        build_input_manifest(empty)


def test_config_hash_is_over_resolved_content(tmp_path):
    a = tmp_path / "a.yaml"
    b = tmp_path / "b.yaml"
    a.write_text("gates:\n  x: 1\n  y: 2\n")
    b.write_text("gates: {y: 2, x: 1}\n")
    assert config_sha256(load_config(a)) == config_sha256(load_config(b))
    assert config_sha256({"gates": {"x": 1}}) != config_sha256({"gates": {"x": 2}})


def test_library_versions_cover_declared_dependencies():
    v = library_versions()
    for name in ["pydantic", "numpy", "shapely", "typer", "pyyaml", "jsonschema", "matplotlib"]:
        assert name in v and v[name]
