"""Generate a snapshot description of the ShadexTable project.

This script produces a single markdown file containing a high–level overview
of the repository.  The resulting document is designed to be attached to
AI requests so that the assistant has enough context to respect the
project’s conventions without needing to inspect the entire codebase.

The snapshot includes:

* A short description of the project based on its README and known
  architectural patterns.
* A hierarchical tree of files and folders under the current working
  directory, excluding build artefacts and typical temporary folders
  (e.g. ``node_modules``, ``.next``, ``.git``).
* The list of third‑party dependencies found in ``package.json``,
  ``requirements.txt`` or ``pyproject.toml``.  Only the package names and
  versions are captured; development dependencies are annotated
  separately.
* An outline of the unified error handling strategy implemented in
  ``src/utils/error.ts`` along with the TypeScript types defined in
  ``src/types/errors.ts``.
* A reminder that the backend API follows a FastAPI architecture and
  returns responses adhering to the ``StandardResponse`` schema (see
  backend ``schemas.py``).  The schema fields are echoed here so that
  the assistant understands the expected response shape.

Run this script from the root of your cloned repository:

    python generate_snapshot.py

The snapshot will be written to ``PROJECT_SNAPSHOT.md`` in the
current directory.  If an existing snapshot is present it will be
overwritten.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Tuple


EXCLUDE_DIRS: set[str] = {
    "node_modules",
    ".next",
    ".git",
    "dist",
    "build",
    ".turbo",
    "__pycache__",
    ".venv",
}


def should_skip(path: Path) -> bool:
    """Return True if the path should be skipped during the tree walk.

    Any part of the path matching one of the entries in ``EXCLUDE_DIRS``
    will cause the directory to be skipped.  This prevents traversing
    large dependency folders and build outputs.
    """
    for part in path.parts:
        if part in EXCLUDE_DIRS:
            return True
    return False


def build_tree(root: Path) -> str:
    """Return a formatted tree of files and directories under ``root``.

    The tree representation uses hyphenated lines with indentation
    corresponding to nesting depth.  Directories are suffixed with a
    trailing slash to differentiate them from files.  Hidden files and
    directories (names starting with a period) are included unless they
    match the exclusion set.
    """
    lines: List[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        rel = current.relative_to(root)
        # Skip excluded directories entirely
        if should_skip(rel):
            dirnames[:] = []  # do not traverse children
            continue

        depth = len(rel.parts) if rel != Path(".") else 0
        indent = "  " * depth
        name = current.name if rel != Path(".") else root.name
        lines.append(f"{indent}- {name}/")

        # Filter out excluded children from traversal
        dirnames[:] = [d for d in dirnames if not should_skip(rel / d)]

        for fname in sorted(f for f in filenames if not f.endswith((".pyc", ".pyo"))):
            if fname.startswith("."):
                continue  # skip dot files
            lines.append(f"{indent}  - {fname}")
    return "\n".join(lines)


def parse_package_json(path: Path) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Parse dependencies from a package.json file.

    Returns a tuple of (dependencies, devDependencies) where each is
    a mapping of package names to their pinned versions.  If the file
    cannot be parsed or does not exist, empty dictionaries are returned.
    """
    deps: Dict[str, str] = {}
    dev_deps: Dict[str, str] = {}
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            deps = data.get("dependencies", {}) or {}
            dev_deps = data.get("devDependencies", {}) or {}
        except Exception:
            pass
    return deps, dev_deps


def parse_requirements(path: Path) -> List[str]:
    """Parse package names from a requirements.txt file.

    Each non‑empty, non‑comment line is returned unchanged.  This
    function makes no attempt to normalise version specifiers.
    """
    packages: List[str] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            packages.append(stripped)
    return packages


def parse_pyproject(path: Path) -> Dict[str, str]:
    """Extract dependencies from a pyproject.toml if present.

    Only the dependencies defined under ``[project]`` or ``[tool.poetry]``
    are considered.  If ``tomllib`` is unavailable (Python < 3.11) the
    file will be ignored gracefully.
    """
    deps: Dict[str, str] = {}
    try:
        import tomllib  # type: ignore[import-not-found]
    except Exception:
        return deps
    if path.exists():
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
            # PEP 621 standard
            project_deps = data.get("project", {}).get("dependencies", [])
            for dep in project_deps:
                if isinstance(dep, str):
                    name = dep.split(";")[0].strip()
                    deps[name] = dep
            # Poetry support
            poetry_deps = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
            for name, spec in poetry_deps.items():
                if name == "python":
                    continue
                if isinstance(spec, str):
                    deps[name] = spec
                elif isinstance(spec, dict) and "version" in spec:
                    deps[name] = spec["version"]
        except Exception:
            pass
    return deps


def format_dependencies(section_name: str, packages: Dict[str, str] | List[str]) -> str:
    """Format a dependency section for the snapshot.

    Depending on the input type, this returns a bullet‑point list of
    ``package@version`` strings.  Empty inputs yield an empty string.
    """
    if not packages:
        return ""
    header = f"### {section_name}\n"
    lines: List[str] = []
    if isinstance(packages, dict):
        for name, version in sorted(packages.items()):
            lines.append(f"- {name}@{version}")
    else:
        for pkg in packages:
            lines.append(f"- {pkg}")
    return header + "\n".join(lines) + "\n"


def generate_snapshot(root: Path) -> str:
    """Compose the full snapshot as a markdown string."""
    tree = build_tree(root)

    # Parse dependency files
    deps, dev_deps = parse_package_json(root / "package.json")
    reqs = parse_requirements(root / "requirements.txt")
    pyproject_deps = parse_pyproject(root / "pyproject.toml")

    md_lines: List[str] = []
    md_lines.append(f"# {root.name} Project Snapshot\n")
    md_lines.append(
        "This document captures the current state of the ShadexTable project. "
        "Attach this file to your AI prompts to provide essential context about the "
        "project’s structure, dependencies and conventions. The goal is to help the AI "
        "produce code that integrates seamlessly with the existing codebase without "
        "breaking established patterns.\n"
    )

    md_lines.append("## Overview\n")
    md_lines.append(
        "ShadexTable is a statistical analysis platform built with Next.js 14, React and "
        "TypeScript.  It provides researchers and analysts with an intuitive interface "
        "for uploading CSV/Excel files, previewing data, performing descriptive statistics "
        "and generating survival analysis plots.  The front‑end uses Tailwind CSS for styling "
        "and implements a unified error handling framework.  On the server side, the system "
        "communicates with a FastAPI backend that returns responses following a `StandardResponse` "
        "schema.  This schema contains the fields `success: bool`, `message: str`, `data: dict | list | null` "
        "and an optional `error_code: int`.  When extending the API or consuming it from the front‑end, "
        "ensure that all responses conform to this structure.\n"
    )

    md_lines.append("## Project Structure\n")
    md_lines.append(
        "The following tree lists the files and folders in this repository.  "
        "Build artefacts and third‑party modules are omitted for brevity.\n"
    )
    md_lines.append("```\n" + tree + "\n```\n")

    md_lines.append("## Dependencies\n")
    # Node dependencies
    if deps:
        md_lines.append(format_dependencies("Runtime dependencies (package.json)", deps))
    if dev_deps:
        md_lines.append(format_dependencies("Development dependencies (package.json)", dev_deps))
    if pyproject_deps:
        md_lines.append(format_dependencies("Python dependencies (pyproject.toml)", pyproject_deps))
    if reqs:
        # Convert list to dict with empty version strings for display
        md_lines.append(format_dependencies("Python dependencies (requirements.txt)", {pkg: "" for pkg in reqs}))
    if not any([deps, dev_deps, pyproject_deps, reqs]):
        md_lines.append("No dependency manifests (package.json, requirements.txt, pyproject.toml) were detected.\n")

    md_lines.append("## Error Handling and API Conventions\n")
    md_lines.append(
        "The front‑end consolidates all error creation and handling in `src/utils/error.ts` and type "
        "definitions in `src/types/errors.ts`.  Developers should **not** throw arbitrary `Error` objects.  "
        "Instead, create new errors via `createError(code, context, messageKey?, options?)` or use the "
        "predefined helpers in `CommonErrors`.  Each error carries a user‑friendly message, an action "
        "suggestion, severity and retry flag.  When catching exceptions, use the type guard `isAppError` "
        "to distinguish between expected application errors and unknown failures.  Always report errors "
        "using `apiClient.reportError()` so that they can be logged and tracked.\n"
    )
    md_lines.append(
        "For API communication, use the `ApiClient` class in `src/lib/apiClient.ts`.  It wraps the native "
        "fetch API with timeout control, automatic retries on GET requests and conversion of HTTP status codes "
        "into typed `AppError` instances via `createErrorFromHttp()`.  All network errors propagate as "
        "`AppError` so they can be handled uniformly by the caller.\n"
    )
    md_lines.append(
        "On the backend, implement endpoints using FastAPI.  Responses **must** conform to the `StandardResponse` "
        "schema defined in the backend’s `schemas.py` (success, message, data, error_code).  When adding new "
        "endpoints, document their request and response models explicitly and update this snapshot if the schema "
        "changes.\n"
    )

    return "\n".join(md_lines)


def main() -> None:
    root = Path.cwd()
    snapshot_md = generate_snapshot(root)
    output_path = root / "PROJECT_SNAPSHOT.md"
    with output_path.open("w", encoding="utf-8") as f:
        f.write(snapshot_md)
    print(f"Snapshot written to {output_path}")


if __name__ == "__main__":
    main()