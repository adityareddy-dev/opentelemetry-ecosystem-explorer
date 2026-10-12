# JavaScript Instrumentation Watcher

Automation tool for synchronizing OpenTelemetry JavaScript instrumentation metadata to the ecosystem
registry.

The metadata sources are the contrib repository
(<https://github.com/open-telemetry/opentelemetry-js-contrib>) and the browser repository
(<https://github.com/open-telemetry/opentelemetry-browser>).

## Methodology

On a scheduled basis, the tool clones (or pulls) `opentelemetry-js-contrib`, discovers every
instrumentation package, and records per-package metadata snapshots in the registry.

Process:

- Clone or pull `opentelemetry-js-contrib` (override the checkout with the `JS_CONTRIB_REPO_PATH`
  env var; the clone target dir is configurable with `JS_CONTRIB_REPOS_DIR`, default `tmp_repos`).
- Discover active packages under `packages/instrumentation-*` that ship a `package.json`. Packages
  without a `package.json` (typically deprecated) are skipped.
- Load supporting data once per run:
  - bundle membership from `packages/auto-instrumentations-node/package.json` dependencies, and
  - component owners from `.github/component_owners.yml`.
- Parse each package's `package.json`, `.tav.yml` (tested version ranges), and the "Supported
  Versions" section of its `README.md`.
- For each package, skip it if its current version is already tracked; otherwise write a versioned
  YAML snapshot.

Unlike the Java agent — which has a single release version covering all instrumentations — JS
packages version **independently**. Each package is therefore stored at its own version.

### Browser releases

The same watcher also collects `@opentelemetry/browser-instrumentation`. Its instrumentations are
subpath exports of one npm package, so they are stored as a sorted `modules` list in one package
entry at `javascript/browser-instrumentation/v{version}.yaml`.

- Clone `opentelemetry-browser` into the same base directory. Cached clones explicitly fetch all
  tags. `OTEL_BROWSER_REPO_PATH` uses an existing checkout as-is, without network access or checkout
  changes; that checkout must already contain the release tags to collect.
- Discover stable `browser-instrumentation-v*` tags, ignoring SDK tags and prereleases. The first
  run collects all available stable releases; subsequent runs skip versions already in the
  inventory.
- Read `packages/instrumentation/package.json` and each exported module's `src/<name>/index.ts` at
  that exact tag. Main may contain unreleased modules before the package version changes.
- Record each module's `name`, `import_path` and `source_path`. Blocked exports and exports without
  a corresponding source entry point are omitted. The package version must match the release tag.

The browser entry includes only metadata available from that source. It omits the contrib-specific
owners, Node bundle membership, engine and target-library version fields. Scope names, telemetry,
platform filtering, and publishing module metadata in the Explorer UI remain follow-up work under
[issue #1187](https://github.com/open-telemetry/opentelemetry-ecosystem-explorer/issues/1187).

## Registry layout

The watcher maintains a per-package, per-version inventory under `ecosystem-registry/javascript/`:

```text
javascript/
└── {package-name}/                 # e.g. instrumentation-express
    └── v{version}.yaml             # e.g. v0.66.0.yaml
```

This is intentionally different from the aggregated-file ecosystems (Java, .NET, Collector,
Configuration), which write one or more files per release version. Here each package directory holds
one YAML file per version of that package.

### File format

**Example**: `javascript/instrumentation-express/v0.66.0.yaml`

```yaml
component_owners:
  - JamieDanielson
  - pkanal
  - raphael-theriault-swi
description: OpenTelemetry instrumentation for `express` http web application framework
in_auto_instrumentations_node: true
name: instrumentation-express
node_engine: ^18.19.0 || >=20.6.0
npm_package: "@opentelemetry/instrumentation-express"
repository: open-telemetry/opentelemetry-js-contrib
source_path: packages/instrumentation-express
supported_versions: # parsed from the README "Supported Versions" section
  - package: express
    source: README.md
    version_range: ">=4.0.0 <6"
tested_versions: # parsed from .tav.yml
  - mode: latest-minors
    package: express
    range: ">=4.16.2 <6"
    source: .tav.yml
version: 0.66.0
```

Output is deterministic: keys are sorted and the `supported_versions` / `tested_versions` arrays are
sorted by a stable key so upstream reordering does not churn the registry.

## Usage

From the repository root:

```bash
uv run js-instrumentation-watcher
```

## Development

From the repository root:

```bash
# Install dependencies
uv sync

# Run tests
uv run pytest ecosystem-automation/js-instrumentation-watcher/tests

# Run tests with coverage
uv run pytest ecosystem-automation/js-instrumentation-watcher/tests --cov=js_instrumentation_watcher

# Run the module
uv run python -m js_instrumentation_watcher
```

## Adding Dependencies

```bash
uv add --package js-instrumentation-watcher <package-name>
```
