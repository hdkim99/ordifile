# Copyright 2026 hdkim99
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import hashlib
import json
import stat
import sys
import threading
import zipfile
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import cast

import pytest

PROJECT_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
import fetch_external_fixture as fetch  # noqa: E402

Route = tuple[int, dict[str, str], bytes]


@pytest.fixture(autouse=True)
def _synthetic_fetch_tests_do_not_inherit_runner_ci(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep synthetic local-server tests separate from the explicit CI-policy test."""

    monkeypatch.delenv("CI", raising=False)


class _RouteServer(ThreadingHTTPServer):
    routes: dict[str, Route]
    request_count: int


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        server = cast(_RouteServer, self.server)
        server.request_count += 1
        status, headers, content = server.routes.get(self.path, (404, {}, b""))
        self.send_response(status)
        for name, value in headers.items():
            self.send_header(name, value)
        if "Content-Length" not in headers:
            self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format: str, *args: object) -> None:
        return


@contextmanager
def _server(routes: dict[str, Route]) -> Iterator[tuple[str, _RouteServer]]:
    server = _RouteServer(("127.0.0.1", 0), _Handler)
    server.routes = routes
    server.request_count = 0
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", server
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def _zip_bytes(tmp_path: Path, entries: dict[str, bytes], *, compressed: bool = False) -> bytes:
    archive_path = tmp_path / f"archive-{len(tuple(tmp_path.glob('archive-*')))}.zip"
    compression = zipfile.ZIP_DEFLATED if compressed else zipfile.ZIP_STORED
    with zipfile.ZipFile(archive_path, "w", compression=compression) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return archive_path.read_bytes()


def _write_raw_zip_member(
    archive: zipfile.ZipFile,
    name: str,
    content: bytes,
) -> None:
    info = zipfile.ZipInfo(name)
    info.orig_filename = name
    info.filename = name
    archive.writestr(info, content)


def _tree_sha(tmp_path: Path, entries: dict[str, bytes]) -> str:
    root = tmp_path / f"tree-{len(tuple(tmp_path.glob('tree-*')))}"
    for name, content in entries.items():
        target = root.joinpath(*name.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    return fetch.canonical_tree_digest(root, entries)


def _manifest_data(
    *,
    url: str,
    content: bytes,
    selected: tuple[str, ...],
    tree_sha256: str | None,
    archive_type: str = "zip",
    artifact_filename: str | None = None,
    ci_eligible: bool = False,
) -> dict[str, object]:
    default_filename = {"zip": "archive.zip", "7z": "archive.7z", "file": "FID1A.CH"}
    return {
        "schema_version": 1,
        "fixture_id": "external_fixture",
        "url": url,
        "allowed_hosts": ["127.0.0.1"],
        "artifact_filename": artifact_filename or default_filename[archive_type],
        "sha256": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
        "archive_type": archive_type,
        "selected_files": list(selected),
        "tree_sha256": tree_sha256,
        "source_page_url": "https://example.test/source",
        "license_name": "Synthetic test permission",
        "license_id": "Synthetic-Test-Permission",
        "license_url": "https://example.test/license",
        "license_acknowledged": True,
        "redistribution": "permitted",
        "attribution": "Synthetic test fixture; no external data.",
        "privacy_review": "no_personal_data_observed",
        "validated_with": [
            {"reader": "synthetic_reader", "version": "1.0.0", "result": "accepted"}
        ],
        "grade": "ACCEPT_REDISTRIBUTABLE",
        "ci_eligible": ci_eligible,
    }


def _fixture_manifest(
    archive: Path,
    *,
    selected: tuple[str, ...],
    tree_sha256: str | None,
    archive_type: str = "zip",
    artifact_filename: str | None = None,
) -> fetch.FixtureManifest:
    data = _manifest_data(
        url=f"https://example.test/{artifact_filename or archive.name}",
        content=archive.read_bytes(),
        selected=selected,
        tree_sha256=tree_sha256,
        archive_type=archive_type,
        artifact_filename=artifact_filename or archive.name,
    )
    data["allowed_hosts"] = ["example.test"]
    manifest_path = archive.with_suffix(f"{archive.suffix}.manifest.json")
    _write_manifest(manifest_path, data)
    return fetch.load_manifest(manifest_path)


def _write_manifest(path: Path, data: dict[str, object]) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_committed_bsee_manifest_is_strict_and_not_default_ci() -> None:
    manifest = fetch.load_manifest(
        PROJECT_ROOT / "docs" / "research" / "external-fixture-manifest.json"
    )

    assert manifest.fixture_id == "bsee-g6151510-fid1a-v181"
    assert manifest.artifact_filename == "BSEE-G6151510-FID1A.CH"
    assert manifest.archive_type == "file"
    assert manifest.size_bytes == 298_146
    assert manifest.sha256 == ("9abeb86b09d54c10e81f46648804acc0319b6e1d014cee54034eae91331f97ef")
    assert manifest.grade == "ACCEPT_REDISTRIBUTABLE"
    assert manifest.ci_eligible is False


def test_manifest_is_strict_https_and_enforces_documented_size_modes(tmp_path: Path) -> None:
    assert fetch.DEFAULT_DOWNLOAD_LIMIT == 256 * 1024 * 1024
    assert fetch.LARGE_DOWNLOAD_LIMIT == 2 * 1024 * 1024 * 1024
    assert fetch.DEFAULT_UNCOMPRESSED_LIMIT == 2 * 1024 * 1024 * 1024
    assert fetch.LARGE_UNCOMPRESSED_LIMIT == 8 * 1024 * 1024 * 1024
    assert fetch.DEFAULT_MEMBER_LIMIT == 10_000
    assert fetch.LARGE_MEMBER_LIMIT == 100_000
    assert fetch.MAX_COMPRESSION_RATIO == 100
    base = _manifest_data(
        url="https://example.test/archive.zip",
        content=b"x",
        selected=("fixture.raw",),
        tree_sha256="0" * 64,
    )
    base["allowed_hosts"] = ["example.test"]
    path = _write_manifest(tmp_path / "manifest.json", base)
    assert fetch.load_manifest(path).fixture_id == "external_fixture"

    unknown = dict(base, unexpected=True)
    _write_manifest(path, unknown)
    with pytest.raises(fetch.FixtureFetchError, match="exactly"):
        fetch.load_manifest(path)

    insecure = dict(base, url="http://example.test/archive.zip")
    _write_manifest(path, insecure)
    with pytest.raises(fetch.FixtureFetchError, match="HTTPS"):
        fetch.load_manifest(path)

    large = dict(base, size_bytes=fetch.DEFAULT_DOWNLOAD_LIMIT + 1)
    _write_manifest(path, large)
    with pytest.raises(fetch.FixtureFetchError, match="size_bytes"):
        fetch.load_manifest(path)
    assert (
        fetch.load_manifest(path, allow_large=True).size_bytes == fetch.DEFAULT_DOWNLOAD_LIMIT + 1
    )

    path.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
    with pytest.raises(fetch.FixtureFetchError, match="repeats JSON key"):
        fetch.load_manifest(path)
    path.write_text('{"schema_version":NaN}', encoding="utf-8")
    with pytest.raises(fetch.FixtureFetchError, match="non-JSON number"):
        fetch.load_manifest(path)

    inconsistent = dict(base, redistribution="unknown")
    _write_manifest(path, inconsistent)
    with pytest.raises(fetch.FixtureFetchError, match="ACCEPT_REDISTRIBUTABLE"):
        fetch.load_manifest(path)

    ineligible = dict(
        base,
        grade="ACCEPT_EXTERNAL_ONLY",
        redistribution="unknown",
        ci_eligible=True,
    )
    _write_manifest(path, ineligible)
    with pytest.raises(fetch.FixtureFetchError, match="ci_eligible"):
        fetch.load_manifest(path)

    invalid_license_id = dict(base, license_id="not a stable ID!")
    _write_manifest(path, invalid_license_id)
    with pytest.raises(fetch.FixtureFetchError, match="license_id"):
        fetch.load_manifest(path)


def test_fetch_requires_exact_caller_license_acceptance_before_network(tmp_path: Path) -> None:
    content = b"must not be requested"
    with _server({"/fixture.bin": (200, {}, content)}) as (base_url, server):
        data = _manifest_data(
            url=f"{base_url}/fixture.bin",
            content=content,
            selected=(),
            tree_sha256=None,
            archive_type="file",
            artifact_filename="fixture.bin",
        )
        manifest_path = _write_manifest(tmp_path / "manifest.json", data)
        with pytest.raises(fetch.FixtureFetchError, match="--accept-license"):
            fetch.fetch_fixture(
                manifest_path,
                tmp_path / "cache",
                accepted_license="a different license",
                _allow_insecure_http=True,
            )

    assert server.request_count == 0
    assert not (tmp_path / "cache").exists()


def test_cli_displays_review_fields_before_requiring_acceptance(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = _manifest_data(
        url="https://example.test/FID1A.CH",
        content=b"fixture",
        selected=(),
        tree_sha256=None,
        archive_type="file",
        artifact_filename="FID1A.CH",
    )
    data["allowed_hosts"] = ["example.test"]
    manifest_path = _write_manifest(tmp_path / "manifest.json", data)

    assert fetch.main([str(manifest_path), "--cache-dir", str(tmp_path / "cache")]) == 1
    output = capsys.readouterr()

    assert "source: https://example.test/source" in output.out
    assert "license: Synthetic test permission (Synthetic-Test-Permission)" in output.out
    assert "license URL: https://example.test/license" in output.out
    assert "attribution: Synthetic test fixture; no external data." in output.out
    assert "--accept-license" in output.err
    assert not (tmp_path / "cache").exists()


@pytest.mark.parametrize("archive_type", ("file", "7z"))
def test_cli_reports_non_extraction_reason_for_each_download_only_type(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    archive_type: str,
) -> None:
    suffix = "CH" if archive_type == "file" else "7z"
    content = b"fixture"
    data = _manifest_data(
        url=f"https://example.test/artifact.{suffix}",
        content=content,
        selected=(),
        tree_sha256=None,
        archive_type=archive_type,
        artifact_filename=f"artifact.{suffix}",
    )
    data["allowed_hosts"] = ["example.test"]
    manifest_path = _write_manifest(tmp_path / "manifest.json", data)
    archive = tmp_path / f"cached.{suffix}"
    archive.write_bytes(content)

    def fake_fetch_fixture(
        manifest_path: Path,
        cache_dir: Path,
        *,
        accepted_license: str,
        allow_large: bool = False,
        allow_ci: bool = False,
        _allow_insecure_http: bool = False,
    ) -> fetch.FetchResult:
        del manifest_path, cache_dir, accepted_license, allow_large, allow_ci
        del _allow_insecure_http
        return fetch.FetchResult(archive, None, None, archive_type)

    monkeypatch.setattr(fetch, "fetch_fixture", fake_fetch_fixture)
    assert (
        fetch.main(
            [
                str(manifest_path),
                "--cache-dir",
                str(tmp_path / "cache"),
                "--accept-license",
                "Synthetic-Test-Permission",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out

    assert f"automatic extraction: disabled for {archive_type}" in output


@pytest.mark.parametrize(
    "selected",
    (
        ("../escape.raw",),
        ("C:/escape.raw",),
        ("folder\\escape.raw",),
        ("/escape.raw",),
        ("CON.raw",),
        (f"{'a' * 256}.raw",),
    ),
)
def test_manifest_rejects_escaping_selected_paths(
    tmp_path: Path, selected: tuple[str, ...]
) -> None:
    data = _manifest_data(
        url="https://example.test/archive.zip",
        content=b"x",
        selected=selected,
        tree_sha256="0" * 64,
    )
    data["allowed_hosts"] = ["example.test"]
    path = _write_manifest(tmp_path / "manifest.json", data)
    with pytest.raises(fetch.FixtureFetchError, match="safe relative"):
        fetch.load_manifest(path)


def test_local_redirect_download_extracts_only_selection_and_reuses_cache(tmp_path: Path) -> None:
    selected_content = {"folder/fixture.raw": b"scientific fixture bytes"}
    archive = _zip_bytes(
        tmp_path,
        {**selected_content, "folder/not-selected.txt": b"not selected"},
    )
    tree_sha = _tree_sha(tmp_path, selected_content)
    routes: dict[str, Route] = {
        "/redirect": (302, {"Location": "/archive.zip"}, b""),
        "/archive.zip": (200, {}, archive),
    }
    with _server(routes) as (base_url, server):
        data = _manifest_data(
            url=f"{base_url}/redirect",
            content=archive,
            selected=tuple(selected_content),
            tree_sha256=tree_sha,
        )
        manifest_path = _write_manifest(tmp_path / "manifest.json", data)
        first = fetch.fetch_fixture(
            manifest_path,
            tmp_path / "cache",
            accepted_license="Synthetic test permission",
            _allow_insecure_http=True,
        )
        first_count = server.request_count
        second = fetch.fetch_fixture(
            manifest_path,
            tmp_path / "cache",
            accepted_license="Synthetic-Test-Permission",
            _allow_insecure_http=True,
        )

    assert first == second
    assert server.request_count == first_count
    assert first.extracted is not None
    assert (first.extracted / "folder" / "fixture.raw").read_bytes() == selected_content[
        "folder/fixture.raw"
    ]
    assert not (first.extracted / "folder" / "not-selected.txt").exists()
    assert fetch.canonical_tree_digest(first.extracted, selected_content) == tree_sha
    assert not list((tmp_path / "cache").rglob("*.part"))


def test_concurrent_direct_manifests_with_same_identity_keep_distinct_hashes(
    tmp_path: Path,
) -> None:
    first_content = b"first direct scientific fixture"
    second_content = b"second direct scientific fixture"
    routes: dict[str, Route] = {
        "/first/FID1A.CH": (200, {}, first_content),
        "/second/FID1A.CH": (200, {}, second_content),
    }
    with _server(routes) as (base_url, _server_instance):
        manifests: list[Path] = []
        for label, content in (("first", first_content), ("second", second_content)):
            data = _manifest_data(
                url=f"{base_url}/{label}/FID1A.CH",
                content=content,
                selected=(),
                tree_sha256=None,
                archive_type="file",
                artifact_filename="FID1A.CH",
            )
            manifests.append(_write_manifest(tmp_path / f"{label}.json", data))
        barrier = threading.Barrier(3)

        def acquire(manifest_path: Path) -> fetch.FetchResult:
            barrier.wait()
            return fetch.fetch_fixture(
                manifest_path,
                tmp_path / "cache",
                accepted_license="Synthetic-Test-Permission",
                _allow_insecure_http=True,
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(acquire, manifest) for manifest in manifests]
            barrier.wait()
            results = [future.result() for future in futures]

    assert results[0].archive != results[1].archive
    for result, expected in zip(results, (first_content, second_content), strict=True):
        expected_sha = hashlib.sha256(expected).hexdigest()
        assert result.archive.parent.name == expected_sha
        assert result.archive.read_bytes() == expected
        assert hashlib.sha256(result.archive.read_bytes()).hexdigest() == expected_sha


def test_concurrent_zip_manifests_keep_distinct_archives_and_trees(tmp_path: Path) -> None:
    selected_name = "fixture.raw"
    first_entries = {selected_name: b"first ZIP fixture"}
    second_entries = {selected_name: b"second ZIP fixture"}
    first_archive = _zip_bytes(tmp_path, first_entries)
    second_archive = _zip_bytes(tmp_path, second_entries)
    routes: dict[str, Route] = {
        "/first/archive.zip": (200, {}, first_archive),
        "/second/archive.zip": (200, {}, second_archive),
    }
    with _server(routes) as (base_url, _server_instance):
        declarations = (
            ("first", first_archive, first_entries),
            ("second", second_archive, second_entries),
        )
        manifests: list[Path] = []
        tree_hashes: list[str] = []
        for label, archive, entries in declarations:
            tree_hash = _tree_sha(tmp_path, entries)
            tree_hashes.append(tree_hash)
            data = _manifest_data(
                url=f"{base_url}/{label}/archive.zip",
                content=archive,
                selected=(selected_name,),
                tree_sha256=tree_hash,
                archive_type="zip",
                artifact_filename="archive.zip",
            )
            manifests.append(_write_manifest(tmp_path / f"{label}.json", data))
        barrier = threading.Barrier(3)

        def acquire(manifest_path: Path) -> fetch.FetchResult:
            barrier.wait()
            return fetch.fetch_fixture(
                manifest_path,
                tmp_path / "cache",
                accepted_license="Synthetic-Test-Permission",
                _allow_insecure_http=True,
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(acquire, manifest) for manifest in manifests]
            barrier.wait()
            results = [future.result() for future in futures]

    assert results[0].archive != results[1].archive
    for result, (_, archive, entries), tree_hash in zip(
        results, declarations, tree_hashes, strict=True
    ):
        archive_sha = hashlib.sha256(archive).hexdigest()
        assert result.archive.parent.name == archive_sha
        assert hashlib.sha256(result.archive.read_bytes()).hexdigest() == archive_sha
        assert result.extracted is not None
        assert result.extracted.name == f"external_fixture-{tree_hash}"
        assert (result.extracted / selected_name).read_bytes() == entries[selected_name]


def test_redirect_to_non_allowlisted_host_is_rejected_and_partial_removed(tmp_path: Path) -> None:
    content = b"not reached"
    with _server({"/redirect": (302, {"Location": "http://localhost/elsewhere"}, b"")}) as (
        base_url,
        _server_instance,
    ):
        data = _manifest_data(
            url=f"{base_url}/redirect",
            content=content,
            selected=("fixture.raw",),
            tree_sha256="0" * 64,
        )
        manifest_path = _write_manifest(tmp_path / "manifest.json", data)
        with pytest.raises(fetch.FixtureFetchError, match="not allowlisted"):
            fetch.fetch_fixture(
                manifest_path,
                tmp_path / "cache",
                accepted_license="Synthetic-Test-Permission",
                _allow_insecure_http=True,
            )

    assert not list((tmp_path / "cache").rglob("*.part"))


def test_download_byte_cap_hash_and_content_length_fail_closed(tmp_path: Path) -> None:
    body = b"abcdef"
    routes: dict[str, Route] = {"/archive.zip": (200, {}, body)}
    with _server(routes) as (base_url, _server_instance):
        data = _manifest_data(
            url=f"{base_url}/archive.zip",
            content=body,
            selected=("fixture.raw",),
            tree_sha256="0" * 64,
        )
        data["size_bytes"] = len(body) - 1
        manifest_path = _write_manifest(tmp_path / "size.json", data)
        manifest = fetch.load_manifest(manifest_path, _allow_insecure_http=True)
        with pytest.raises(fetch.FixtureFetchError, match="Content-Length"):
            fetch.download_fixture_archive(
                manifest,
                tmp_path / "cache-size",
                _allow_insecure_http=True,
            )

        data["size_bytes"] = len(body)
        data["sha256"] = "0" * 64
        manifest_path = _write_manifest(tmp_path / "sha.json", data)
        manifest = fetch.load_manifest(manifest_path, _allow_insecure_http=True)
        with pytest.raises(fetch.FixtureFetchError, match="SHA-256"):
            fetch.download_fixture_archive(
                manifest,
                tmp_path / "cache-sha",
                _allow_insecure_http=True,
            )

    assert not list(tmp_path.rglob("*.part"))


@pytest.mark.parametrize(
    "names",
    (
        ("../escape",),
        ("C:/escape",),
        ("A.raw", "a.raw"),
        ("e\N{COMBINING ACUTE ACCENT}.raw", "\N{LATIN SMALL LETTER E WITH ACUTE}.raw"),
        ("file", "file/child"),
        ("CON.txt",),
        ("trailing.",),
    ),
    ids=(
        "traversal",
        "drive",
        "casefold",
        "unicode",
        "prefix-conflict",
        "reserved",
        "trailing-dot",
    ),
)
def test_zip_inventory_rejects_unsafe_and_duplicate_names(
    tmp_path: Path, names: tuple[str, ...]
) -> None:
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as output:
        for name in names:
            output.writestr(name, b"x")

    with pytest.raises(fetch.FixtureFetchError):
        fetch.inspect_zip_archive(archive)


def test_zip_inventory_rejects_raw_backslash_member_on_every_platform(tmp_path: Path) -> None:
    archive = tmp_path / "raw-backslash.zip"
    with zipfile.ZipFile(archive, "w") as output:
        _write_raw_zip_member(output, "folder\\escape.raw", b"raw backslash bytes")

    with zipfile.ZipFile(archive) as opened:
        info = opened.infolist()[0]
        assert info.orig_filename == "folder\\escape.raw"
    with pytest.raises(fetch.FixtureFetchError, match="canonical safe relative ZIP path"):
        fetch.inspect_zip_archive(archive)


@pytest.mark.parametrize(
    ("canonical", "alias"),
    (
        ("folder/item.raw", "folder//item.raw"),
        ("folder/item.raw", "folder/./item.raw"),
        ("folder/", "FOLDER"),
    ),
    ids=("double-slash", "dot", "directory-slash"),
)
def test_zip_inventory_rejects_lexical_aliases_with_different_bytes(
    tmp_path: Path,
    canonical: str,
    alias: str,
) -> None:
    archive = tmp_path / "aliases.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr(canonical, b"canonical bytes")
        output.writestr(alias, b"different alias bytes")

    with pytest.raises(fetch.FixtureFetchError, match="safe relative|duplicate"):
        fetch.inspect_zip_archive(archive)


def test_zip_inventory_rejects_raw_nul_member_name(tmp_path: Path) -> None:
    archive = tmp_path / "nul.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("safe_hidden", b"x")
    raw = archive.read_bytes().replace(b"safe_hidden", b"safe\x00hidden")
    archive.write_bytes(raw)

    with pytest.raises(fetch.FixtureFetchError, match="NUL"):
        fetch.inspect_zip_archive(archive)


def test_zip_inventory_rejects_symlink_encryption_bomb_and_limits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    symlink = tmp_path / "symlink.zip"
    info = zipfile.ZipInfo("link")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(symlink, "w") as output:
        output.writestr(info, b"target")
    with pytest.raises(fetch.FixtureFetchError, match="regular files"):
        fetch.inspect_zip_archive(symlink)

    encrypted = tmp_path / "encrypted.zip"
    encrypted.write_bytes(_zip_bytes(tmp_path, {"fixture.raw": b"x"}))
    raw = bytearray(encrypted.read_bytes())
    for signature, offset in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
        index = raw.index(signature)
        flags = int.from_bytes(raw[index + offset : index + offset + 2], "little") | 1
        raw[index + offset : index + offset + 2] = flags.to_bytes(2, "little")
    encrypted.write_bytes(raw)
    with pytest.raises(fetch.FixtureFetchError, match="encrypted"):
        fetch.inspect_zip_archive(encrypted)

    bomb = tmp_path / "bomb.zip"
    bomb.write_bytes(_zip_bytes(tmp_path, {"fixture.raw": b"0" * 100_000}, compressed=True))
    with pytest.raises(fetch.FixtureFetchError, match="compression ratio"):
        fetch.inspect_zip_archive(bomb)

    limited = tmp_path / "limited.zip"
    limited.write_bytes(_zip_bytes(tmp_path, {"a": b"1", "b": b"2"}))
    monkeypatch.setattr(fetch, "DEFAULT_MEMBER_LIMIT", 1)
    with pytest.raises(fetch.FixtureFetchError, match="member count"):
        fetch.inspect_zip_archive(limited)

    monkeypatch.setattr(fetch, "DEFAULT_MEMBER_LIMIT", 10_000)
    monkeypatch.setattr(fetch, "DEFAULT_UNCOMPRESSED_LIMIT", 1)
    with pytest.raises(fetch.FixtureFetchError, match="uncompressed size"):
        fetch.inspect_zip_archive(limited)


def test_selection_requires_exact_regular_member_spelling(tmp_path: Path) -> None:
    archive = tmp_path / "selection.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("Folder/", b"")
        output.writestr("Folder/Fixture.raw", b"x")
    wrong_case = _fixture_manifest(
        archive,
        selected=("folder/fixture.raw",),
        tree_sha256="0" * 64,
    )
    with pytest.raises(fetch.FixtureFetchError, match="spelling differs"):
        fetch.extract_selected_zip(wrong_case, archive, tmp_path / "cache-case")

    directory = _fixture_manifest(
        archive,
        selected=("Folder",),
        tree_sha256="0" * 64,
    )
    with pytest.raises(fetch.FixtureFetchError, match="not a regular file"):
        fetch.extract_selected_zip(directory, archive, tmp_path / "cache-directory")


def test_tree_digest_mismatch_does_not_publish_partial_fixture(tmp_path: Path) -> None:
    entries = {"fixture.raw": b"exact"}
    archive = tmp_path / "archive.zip"
    archive.write_bytes(_zip_bytes(tmp_path, entries))
    manifest = _fixture_manifest(
        archive,
        selected=tuple(entries),
        tree_sha256="0" * 64,
    )

    with pytest.raises(fetch.FixtureFetchError, match="tree SHA-256"):
        fetch.extract_selected_zip(manifest, archive, tmp_path / "cache")

    assert not list((tmp_path / "cache" / "fixtures").glob("external_fixture-*"))
    assert not list((tmp_path / "cache" / "fixtures").glob(".external_fixture.*"))


def test_tree_digest_rejects_undeclared_cache_content(tmp_path: Path) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    (root / "fixture.raw").write_bytes(b"exact")
    expected = fetch.canonical_tree_digest(root, ("fixture.raw",))
    (root / "undeclared.raw").write_bytes(b"unexpected")

    with pytest.raises(fetch.FixtureFetchError, match="differ from the declared selection"):
        fetch.canonical_tree_digest(root, ("fixture.raw",))
    assert len(expected) == 64


def test_cache_symlink_is_rejected(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    cache = tmp_path / "cache"
    try:
        cache.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable")

    archive = tmp_path / "declared.zip"
    archive.write_bytes(b"x")
    manifest = _fixture_manifest(
        archive,
        selected=("fixture.raw",),
        tree_sha256="0" * 64,
    )
    with pytest.raises(fetch.FixtureFetchError, match="symlink"):
        fetch.download_fixture_archive(manifest, cache)


def test_cache_child_symlink_escape_is_rejected(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (cache / "downloads").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable")

    archive = tmp_path / "declared.zip"
    archive.write_bytes(b"x")
    manifest = _fixture_manifest(
        archive,
        selected=("fixture.raw",),
        tree_sha256="0" * 64,
    )
    with pytest.raises(fetch.FixtureFetchError, match="cache child"):
        fetch.download_fixture_archive(manifest, cache)


def test_digest_cache_child_symlink_escape_is_rejected(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    fixture_root = cache / "downloads" / "external_fixture"
    fixture_root.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    archive = tmp_path / "declared.zip"
    archive.write_bytes(b"x")
    manifest = _fixture_manifest(
        archive,
        selected=("fixture.raw",),
        tree_sha256="0" * 64,
    )
    try:
        (fixture_root / manifest.sha256).symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable")

    with pytest.raises(fetch.FixtureFetchError, match="cache child"):
        fetch.download_fixture_archive(manifest, cache)


def test_7z_is_verified_download_only_and_never_auto_extracted(tmp_path: Path) -> None:
    archive = b"7z\xbc\xaf\x27\x1c synthetic"
    with _server({"/archive.7z": (200, {}, archive)}) as (base_url, _server_instance):
        data = _manifest_data(
            url=f"{base_url}/archive.7z",
            content=archive,
            selected=(),
            tree_sha256=None,
            archive_type="7z",
        )
        manifest_path = _write_manifest(tmp_path / "manifest.json", data)
        result = fetch.fetch_fixture(
            manifest_path,
            tmp_path / "cache",
            accepted_license="Synthetic-Test-Permission",
            _allow_insecure_http=True,
        )

    assert result.archive.read_bytes() == archive
    assert result.extracted is None
    assert result.tree_sha256 is None
    assert not (tmp_path / "cache" / "fixtures").exists()


def test_direct_file_fixture_is_reproducibly_downloaded_without_extraction(tmp_path: Path) -> None:
    raw_fixture = b"direct synthetic instrument bytes"
    with _server({"/FID1A.CH": (200, {}, raw_fixture)}) as (base_url, _server_instance):
        data = _manifest_data(
            url=f"{base_url}/FID1A.CH",
            content=raw_fixture,
            selected=(),
            tree_sha256=None,
            archive_type="file",
            artifact_filename="FID1A.CH",
        )
        manifest_path = _write_manifest(tmp_path / "manifest.json", data)
        result = fetch.fetch_fixture(
            manifest_path,
            tmp_path / "cache",
            accepted_license="Synthetic-Test-Permission",
            _allow_insecure_http=True,
        )

    assert result.archive.name == "FID1A.CH"
    assert result.archive.read_bytes() == raw_fixture
    assert result.extracted is None


def test_ci_download_requires_manifest_eligibility_and_explicit_opt_in(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_fixture = b"ci fixture"
    with _server({"/fixture.bin": (200, {}, raw_fixture)}) as (base_url, server):
        data = _manifest_data(
            url=f"{base_url}/fixture.bin",
            content=raw_fixture,
            selected=(),
            tree_sha256=None,
            archive_type="file",
            artifact_filename="fixture.bin",
        )
        manifest_path = _write_manifest(tmp_path / "manifest.json", data)
        monkeypatch.setenv("CI", "true")
        with pytest.raises(fetch.FixtureFetchError, match="disabled in CI"):
            fetch.fetch_fixture(
                manifest_path,
                tmp_path / "blocked-cache",
                accepted_license="Synthetic-Test-Permission",
                _allow_insecure_http=True,
            )
        assert server.request_count == 0

        data["ci_eligible"] = True
        _write_manifest(manifest_path, data)
        with pytest.raises(fetch.FixtureFetchError, match="disabled in CI"):
            fetch.fetch_fixture(
                manifest_path,
                tmp_path / "still-blocked-cache",
                accepted_license="Synthetic-Test-Permission",
                _allow_insecure_http=True,
            )
        allowed = fetch.fetch_fixture(
            manifest_path,
            tmp_path / "allowed-cache",
            accepted_license="Synthetic-Test-Permission",
            allow_ci=True,
            _allow_insecure_http=True,
        )

    assert allowed.archive.read_bytes() == raw_fixture
