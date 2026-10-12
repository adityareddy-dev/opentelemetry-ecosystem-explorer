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
"""Component-prefixed tags must stay isolated from other release trains."""

from semantic_version import Version
from watcher_common.testing import git_commit, init_repo, run_git
from watcher_common.version_detector import VersionDetector


def test_component_prefix_filters_orders_and_checks_out_the_matching_tag(tmp_path):
    init_repo(tmp_path)
    marker = tmp_path / "marker"
    marker.write_text("old", encoding="utf-8")
    run_git(tmp_path, "add", ".")
    git_commit(tmp_path, "Old fixture")
    run_git(tmp_path, "tag", "browser-instrumentation-v0.9.0")
    marker.write_text("new", encoding="utf-8")
    run_git(tmp_path, "add", ".")
    git_commit(tmp_path, "New fixture")
    for tag in (
        "browser-instrumentation-v0.10.0",
        "browser-instrumentation-v0.11.0-rc.1",
        "browser-sdk-v99.0.0",
        "v50.0.0",
        "browser-instrumentation-vinvalid",
    ):
        run_git(tmp_path, "tag", tag)

    detector = VersionDetector(tmp_path, tag_prefix="browser-instrumentation-v")

    assert detector.get_all_release_tags() == [Version("0.10.0"), Version("0.9.0")]
    assert detector.get_latest_release_tag() == Version("0.10.0")
    detector.checkout_version(Version("0.9.0"))
    assert marker.read_text(encoding="utf-8") == "old"


def test_default_detection_preserves_plain_and_v_tags(tmp_path):
    init_repo(tmp_path)
    (tmp_path / "marker").write_text("fixture", encoding="utf-8")
    run_git(tmp_path, "add", ".")
    git_commit(tmp_path, "Fixture")
    for tag in ("1.0.0", "v2.0.0", "v3.0.0-rc.1", "browser-instrumentation-v9.0.0"):
        run_git(tmp_path, "tag", tag)

    assert VersionDetector(tmp_path).get_all_release_tags() == [Version("2.0.0"), Version("1.0.0")]
