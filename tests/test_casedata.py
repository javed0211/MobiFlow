"""Tests for external case data files."""

from __future__ import annotations

from pathlib import Path

import pytest

from mobiflow.casedata import flatten_data, load_data_file, resolve_data_path
from mobiflow.cases import parse_case_text


def test_flatten_nested():
    flat = flatten_data({"search_query": "Einstein", "user": {"name": "demo"}})
    assert flat["SEARCH_QUERY"] == "Einstein"
    assert flat["USER_NAME"] == "demo"


def test_resolve_relative_to_case_and_repo(tmp_path: Path):
    repo = tmp_path / "repo"
    cases = repo / "cases"
    data = repo / "data"
    cases.mkdir(parents=True)
    data.mkdir()
    (data / "login.json").write_text('{"USERNAME": "a"}', encoding="utf-8")
    case_file = cases / "login.txt"
    case_file.write_text("task: x\n", encoding="utf-8")

    resolved = resolve_data_path(
        "data/login.json",
        case_path=case_file,
        repo=repo,
    )
    assert resolved.name == "login.json"

    abs_path = resolve_data_path(str(resolved))
    assert abs_path == resolved.resolve()


def test_load_json_yaml_env(tmp_path: Path):
    j = tmp_path / "d.json"
    j.write_text('{"Q": "cats", "nested": {"x": 1}}', encoding="utf-8")
    raw, flat = load_data_file(j)
    assert raw["Q"] == "cats"
    assert flat["Q"] == "cats"
    assert flat["NESTED_X"] == "1"

    y = tmp_path / "d.yaml"
    y.write_text("SEARCH_QUERY: dogs\n", encoding="utf-8")
    _, flat_y = load_data_file(y)
    assert flat_y["SEARCH_QUERY"] == "dogs"

    e = tmp_path / "creds.env"
    e.write_text("PASSWORD=secret\n# comment\nUSER=u1\n", encoding="utf-8")
    _, flat_e = load_data_file(e)
    assert flat_e["PASSWORD"] == "secret"
    assert flat_e["USER"] == "u1"


def test_case_data_path_and_load(tmp_path: Path):
    data = tmp_path / "wiki.json"
    data.write_text('{"search_query": "Albert Einstein"}', encoding="utf-8")
    case = parse_case_text(
        f"""
appId: org.wikipedia
platform: ios
data: {data}
task: Search for ${{SEARCH_QUERY}}
"""
    )
    case.source_path = tmp_path / "case.txt"
    assert case.data_path == str(data)
    path, raw, flat = case.load_data(repo=tmp_path)
    assert path == data.resolve()
    assert flat["SEARCH_QUERY"] == "Albert Einstein"
    assert flat["DATA_PATH"] == str(path)
    block = case.explore_task(data_block="SEARCH_QUERY=Albert Einstein")
    assert "SEARCH_QUERY" in block


def test_missing_data_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        resolve_data_path("missing.json", repo=tmp_path)
