# Copyright The OpenTelemetry Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
"""Release-history tests for the browser source; no external APIs are used."""

import json

import pytest
from js_instrumentation_watcher.browser_sync import BrowserInstrumentationSync
from js_instrumentation_watcher.inventory_manager import InventoryManager
from watcher_common.testing import git_commit, init_repo, run_git


def write_package(repo, version, exports):
    package_dir = repo / "packages/instrumentation"
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "package.json").write_text(
        json.dumps(
            {
                "name": "@opentelemetry/browser-instrumentation",
                "version": version,
                "description": "Browser instrumentation fixture",
                "exports": exports,
            }
        ),
        encoding="utf-8",
    )


def add_source(repo, name):
    source = repo / "packages/instrumentation/src" / name / "index.ts"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("export {};\n", encoding="utf-8")


@pytest.fixture
def history(tmp_path):
    """An old release, a newer release, other components, and unreleased main."""
    repo = tmp_path / "browser"
    repo.mkdir()
    init_repo(repo)
    write_package(repo, "0.8.1", {"./experimental/errors": "./dist/errors/index.js"})
    add_source(repo, "errors")
    run_git(repo, "add", ".")
    git_commit(repo, "First fixture release")
    run_git(repo, "tag", "browser-instrumentation-v0.8.1")

    write_package(
        repo,
        "0.8.2",
        {
            "./experimental/xhr": "./dist/xhr/index.js",
            "./experimental/errors": {"import": "./dist/errors/index.js"},
            "./experimental/missing": "./dist/missing/index.js",
            "./experimental/blocked": None,
            "./package.json": "./package.json",
        },
    )
    add_source(repo, "xhr")
    add_source(repo, "blocked")
    run_git(repo, "add", ".")
    git_commit(repo, "Second fixture release")
    run_git(repo, "tag", "browser-instrumentation-v0.8.2")
    run_git(repo, "tag", "browser-sdk-v9.0.0")
    run_git(repo, "tag", "v10.0.0")
    run_git(repo, "tag", "browser-instrumentation-v0.9.0-rc.1")
    run_git(repo, "tag", "browser-instrumentation-vinvalid")

    # Main changes its exports before the release version changes. Reading the
    # current checkout would incorrectly assign fetch to already-published 0.8.2.
    write_package(repo, "0.8.2", {"./experimental/fetch": "./dist/fetch/index.js"})
    add_source(repo, "fetch")
    run_git(repo, "add", ".")
    git_commit(repo, "Unreleased fixture change")
    return repo


def test_each_release_uses_its_own_manifest_and_source_tree(history, tmp_path):
    inventory = InventoryManager(str(tmp_path / "registry"))
    original_head = run_git(history, "rev-parse", "HEAD")

    summary = BrowserInstrumentationSync(history, inventory).sync()

    assert summary == {
        "new": ["browser-instrumentation@0.8.1", "browser-instrumentation@0.8.2"],
        "skipped": [],
        "failed": [],
    }
    old = inventory.load("browser-instrumentation", "0.8.1")
    new = inventory.load("browser-instrumentation", "0.8.2")
    assert [module["name"] for module in old["modules"]] == ["errors"]
    assert new["modules"] == [
        {
            "name": "errors",
            "import_path": "@opentelemetry/browser-instrumentation/experimental/errors",
            "source_path": "packages/instrumentation/src/errors",
        },
        {
            "name": "xhr",
            "import_path": "@opentelemetry/browser-instrumentation/experimental/xhr",
            "source_path": "packages/instrumentation/src/xhr",
        },
    ]
    assert new["repository"] == "open-telemetry/opentelemetry-browser"
    assert "node_engine" not in new
    assert "in_auto_instrumentations_node" not in new
    assert run_git(history, "rev-parse", "HEAD") == original_head
    assert run_git(history, "status", "--porcelain") == ""


def test_existing_versions_are_skipped_before_parsing(history, tmp_path, monkeypatch):
    inventory = InventoryManager(str(tmp_path / "registry"))
    sync = BrowserInstrumentationSync(history, inventory)
    sync.sync()
    before = {path: path.read_bytes() for path in inventory.registry_dir.rglob("*.yaml")}

    def unexpected_parse(_):
        pytest.fail("Existing releases must not be parsed or rewritten")

    monkeypatch.setattr(sync, "_parse_release", unexpected_parse)
    assert sync.sync() == {
        "new": [],
        "skipped": ["browser-instrumentation@0.8.1", "browser-instrumentation@0.8.2"],
        "failed": [],
    }
    assert {path: path.read_bytes() for path in before} == before


def test_tag_version_mismatch_fails_without_writing_a_snapshot(history, tmp_path):
    run_git(history, "tag", "browser-instrumentation-v0.9.0")
    inventory = InventoryManager(str(tmp_path / "registry"))

    summary = BrowserInstrumentationSync(history, inventory).sync()

    assert summary["failed"] == ["browser-instrumentation@0.9.0"]
    assert not inventory.version_exists("browser-instrumentation", "0.9.0")
    assert len(summary["new"]) == 2


@pytest.mark.parametrize("manifest", ["[]", "{broken", '{"name":"other"}'])
def test_malformed_release_is_reported_and_not_saved(history, tmp_path, manifest):
    (history / "packages/instrumentation/package.json").write_text(manifest, encoding="utf-8")
    run_git(history, "add", ".")
    git_commit(history, "Malformed fixture release")
    run_git(history, "tag", "browser-instrumentation-v0.9.0")
    inventory = InventoryManager(str(tmp_path / "registry"))

    summary = BrowserInstrumentationSync(history, inventory).sync()

    assert summary["failed"] == ["browser-instrumentation@0.9.0"]
    assert not inventory.version_exists("browser-instrumentation", "0.9.0")


def test_module_can_leave_experimental_without_changing_its_name(history, tmp_path):
    write_package(history, "1.0.0", {"./fetch": "./dist/fetch/index.js"})
    run_git(history, "add", ".")
    git_commit(history, "Stable public subpath fixture")
    run_git(history, "tag", "browser-instrumentation-v1.0.0")
    inventory = InventoryManager(str(tmp_path / "registry"))

    BrowserInstrumentationSync(history, inventory).sync()

    assert inventory.load("browser-instrumentation", "1.0.0")["modules"] == [
        {
            "name": "fetch",
            "import_path": "@opentelemetry/browser-instrumentation/fetch",
            "source_path": "packages/instrumentation/src/fetch",
        }
    ]
