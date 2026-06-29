# Migration plan: pip → uv and mypy → ty

## Context

The project uses pip/setuptools as its package manager and mypy as its type checker.
Migrating to uv (Astral's package manager) brings a lockfile, significantly faster installs,
and tighter integration with ruff (already in use). Migrating to ty (Astral's type checker)
replaces mypy with a Rust-based checker from the same toolchain.

The codebase is well-positioned for both migrations: strict mypy compliance, no `# type: ignore`
comments, only 3 `cast()` calls, and all modern union syntax (`X | Y`, builtin generics).

> **Note on ty maturity:** ty is in active development (pre-1.0 as of mid-2025). Verify that
> Python 3.14 is fully supported before committing. If ty raises false positives, pinning a
> specific version and filing upstream issues is the right approach rather than adding suppression.

---

## Part 1 — pip → uv

### 1. Add `.python-version`

Create `.python-version` at the repo root:

```text
3.14
```

uv reads this file; no need to pass `--python` flags elsewhere.

### 2. Update `pyproject.toml`

**a) Switch build backend from setuptools to hatchling** (cleaner for uv projects — hatchling
auto-discovers the `channel_ten` package, so `[tool.setuptools.packages.find]` can be removed):

```toml
# Remove:
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["channel_ten*"]

# Replace with:
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

**b) Migrate dev extras to a dependency group** (PEP 735 — not published with the package,
the right place for dev tooling):

```toml
# Remove:
[project.optional-dependencies]
dev = [...]

# Add:
[dependency-groups]
dev = [
    "pytest>=9.0",
    "pytest-cov>=5.0",
    "pytest-html>=4.1",
    "ruff>=0.4",
    "ty",                   # replaces mypy (see Part 2)
    "pre-commit>=3.7",
    "lxml-stubs",
    "types-PyYAML",
    "types-Pygments",
    "types-html5lib",
    "types-requests",
]
```

**c) Add uv config** to pin Python preference:

```toml
[tool.uv]
python-preference = "only-managed"
```

### 3. Generate `uv.lock`

```bash
uv lock
```

This creates `uv.lock` — commit it alongside the other changes.

### 4. Update CI workflows

All five workflows share the same pattern. Replace `setup-python@v5` + `pip install` with
`setup-uv@v4` + `uv sync`.

Files to update:

- `.github/workflows/pre-commit.yml`
- `.github/workflows/publish.yml`
- `.github/workflows/scrape.yml`
- `.github/workflows/validate.yml`
- `.github/workflows/twda-reimport.yml`

**Before (in each workflow):**

```yaml
- name: Set up Python
  uses: actions/setup-python@v5
  with:
    python-version: "3.14"
    allow-prereleases: true
    cache: "pip"

- name: Install dependencies
  run: pip install -e ".[dev]"
  # or: pip install -e "./channel-ten[dev]"
```

**After:**

```yaml
- name: Set up uv
  uses: astral-sh/setup-uv@v4
  with:
    enable-cache: true
    python-version: "3.14"

- name: Install dependencies
  run: uv sync --group dev
  # or for checked-out subdirectory:
  run: uv sync --group dev --project ./channel-ten
```

Also update the pre-commit invocation to run inside the uv environment:

```yaml
# Before:
- name: Run pre-commit hooks
  run: pre-commit run --all-files

# After:
- name: Run pre-commit hooks
  run: uv run pre-commit run --all-files
```

### 5. Update `.pre-commit-config.yaml` local hooks

Replace `python -m <tool>` with `uv run <tool>` in local hooks so they always use the
managed environment (matters for local developer runs where uv may not have activated a venv):

```yaml
# Before:
entry: python -m pytest
# After:
entry: uv run pytest

# Before:
entry: python -m channel_ten.cli
# After:
entry: uv run python -m channel_ten.cli
```

---

## Part 2 — mypy → ty

### 1. Update `pyproject.toml`

**a) Remove the `[tool.mypy]` section entirely** (lines 65–79 in the current file).

**b) In the `[dependency-groups].dev` list** (already updated in Part 1), replace
`mypy>=1.10` with `ty`. Also evaluate stub packages — ty bundles its own stubs and may not
need all of `lxml-stubs`, `types-PyYAML`, `types-Pygments`, `types-html5lib`, `types-requests`.
Keep them for now and remove any that ty flags as unused/redundant after the first clean run.

**c) Add a `[tool.ty]` section.** ty's strict configuration is still evolving; check the
[ty docs](https://github.com/astral-sh/ty) for the current knobs. A starting point that
mirrors the mypy strict setup:

```toml
[tool.ty]
# Source root — ty discovers packages from here
src = ["."]
```

ty does not have a plugin system; Pydantic v2 models are understood natively (no equivalent
of `plugins = ["pydantic.mypy"]` needed). The `html_report` from mypy has no ty equivalent
yet — remove it.

> **Pydantic caveat:** ty's Pydantic understanding may differ from `pydantic.mypy` in edge
> cases (e.g., `model_validator`, `field_validator` return types). Run `ty check channel_ten`
> after migration and fix any new errors before treating them as false positives.

### 2. Add a ty hook to `.pre-commit-config.yaml`

Append to the existing local hooks block:

```yaml
      - id: ty
        name: ty type check
        entry: uv run ty check channel_ten
        language: system
        pass_filenames: false
        always_run: true
        types_or: [python, pyi]
```

### 3. Run ty and fix errors

```bash
uv run ty check channel_ten
```

Expected: clean run or minor differences in how BeautifulSoup's `Any`-typed returns are
handled (the 3 `cast()` usages in `_vekn.py`, `_forum.py`, and `cli/validate.py` should
still be valid under ty).

---

## Verification

```bash
# Install fresh
uv sync --group dev

# Full test suite
uv run pytest

# Type check
uv run ty check channel_ten

# All pre-commit hooks (includes ruff, pytest, smoke tests, ty)
uv run pre-commit run --all-files
```

Expected: all green. The tests are not type-checked (excluded in both mypy and by default in
ty), so no test-file changes are needed.
