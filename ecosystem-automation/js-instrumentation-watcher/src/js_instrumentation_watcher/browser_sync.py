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
"""Read browser instrumentation metadata from component release tags."""

import json
import logging
import re
from pathlib import Path
from typing import Any

from semantic_version import Version
from watcher_common.version_detector import VersionDetector

from .inventory_manager import InventoryManager

logger = logging.getLogger(__name__)

TAG_PREFIX = "browser-instrumentation-v"
PACKAGE_NAME = "browser-instrumentation"
NPM_PACKAGE = "@opentelemetry/browser-instrumentation"
SOURCE_PATH = "packages/instrumentation"
MODULE_NAME_RE = re.compile(r"[a-z][a-z0-9-]*")


class BrowserInstrumentationSync:
    """Write one immutable package snapshot per released browser version.

    The package's exported modules share its version. Both the manifest and
    source-file checks use the same tag; main may contain unreleased modules
    without a package version bump and must never supply release metadata.
    """

    def __init__(self, repo_path: Path, inventory_manager: InventoryManager):
        self.inventory_manager = inventory_manager
        self.detector = VersionDetector(repo_path, tag_prefix=TAG_PREFIX)

    def _parse_release(self, version: Version) -> dict[str, Any]:
        ref = f"refs/tags/{TAG_PREFIX}{version}"
        manifest = self.detector.read_file_at_ref(ref, f"{SOURCE_PATH}/package.json")
        if manifest is None:
            raise ValueError(f"No instrumentation package.json at {ref}")
        package = json.loads(manifest)
        if not isinstance(package, dict) or package.get("name") != NPM_PACKAGE:
            raise ValueError(f"Unexpected instrumentation package at {ref}")
        if package.get("version") != str(version):
            raise ValueError(f"Package version does not match release tag {ref}")
        exports = package.get("exports")
        if not isinstance(exports, dict):
            raise ValueError(f"No exports mapping at {ref}")

        modules = []
        for export_path, target in exports.items():
            # Package metadata and blocked exports are not instrumentations.
            # A module may later leave ./experimental/ without changing its name.
            if not export_path.startswith("./") or target is None:
                continue
            name = export_path.rsplit("/", 1)[-1]
            if not MODULE_NAME_RE.fullmatch(name):
                continue
            source_path = f"{SOURCE_PATH}/src/{name}"
            if self.detector.read_file_at_ref(ref, f"{source_path}/index.ts") is None:
                continue
            modules.append(
                {
                    "name": name,
                    "import_path": f"{NPM_PACKAGE}{export_path[1:]}",
                    "source_path": source_path,
                }
            )

        if not modules:
            raise ValueError(f"No exported instrumentation modules found at {ref}")
        return {
            "name": PACKAGE_NAME,
            "npm_package": NPM_PACKAGE,
            "version": str(version),
            "description": package.get("description", ""),
            "repository": "open-telemetry/opentelemetry-browser",
            "source_path": SOURCE_PATH,
            "modules": sorted(modules, key=lambda module: (module["name"], module["import_path"])),
        }

    def sync(self) -> dict[str, list[str]]:
        """Collect missing stable releases, without rewriting existing snapshots."""
        summary: dict[str, list[str]] = {"new": [], "skipped": [], "failed": []}
        for version in reversed(self.detector.get_all_release_tags()):
            label = f"{PACKAGE_NAME}@{version}"
            if self.inventory_manager.version_exists(PACKAGE_NAME, str(version)):
                summary["skipped"].append(label)
                continue
            try:
                data = self._parse_release(version)
                self.inventory_manager.save(PACKAGE_NAME, str(version), data)
            except (ValueError, OSError):
                logger.exception("Failed to collect %s", label)
                summary["failed"].append(label)
                continue
            summary["new"].append(label)
            logger.info("Saved: %s", label)
        return summary
