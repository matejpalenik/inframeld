"""Select complete CI check families from the original Git event comparison."""

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

FLAGS = (
    "backend",
    "integration",
    "web",
    "web_format",
    "cli",
    "cli_dependencies",
    "sdk",
    "sdk_macos",
    "codeql_python",
    "codeql_javascript",
)

# These SDK inputs preserve the former inline detector, including its prose exceptions.
SDK_PREFIXES = (
    "packages/sdk-",
    "contracts/openapi/",
    "apps/backend/src/",
    "apps/backend/tests/unit/contract/",
    ".cargo/",
    ".github/workflows/sdk-",
)
SDK_INPUTS = {
    "package.json",
    "pnpm-lock.yaml",
    "pnpm-workspace.yaml",
    ".npmrc",
    "Cargo.toml",
    "Cargo.lock",
    "rust-toolchain.toml",
    "mise.toml",
    "apps/backend/package.json",
    "apps/backend/pyproject.toml",
    "apps/backend/uv.lock",
    "apps/backend/.python-version",
    "apps/backend/.env.test.example",
    "apps/backend/scripts/export_openapi.py",
    "apps/backend/tests/__init__.py",
    "apps/backend/tests/conftest.py",
    "apps/backend/tests/unit/__init__.py",
    "apps/backend/tests/unit/conftest.py",
    "apps/backend/tests/support/__init__.py",
    "apps/backend/tests/support/authentication_evidence.py",
    "apps/backend/tests/support/openapi_schema_fixture.py",
    "apps/backend/tests/support/sdk_conformance_app.py",
    "apps/backend/tests/support/sdk_server.py",
}
MACOS_PREFIXES = (
    "packages/sdk-tools/generators/",
    "packages/sdk-tools/src/generation/",
    "packages/sdk-tools/src/system/",
    "packages/sdk-tools/src/conformance/",
    "packages/sdk-tools/drivers/",
    "packages/sdk-tools/consumers/",
    "packages/sdk-tools/tests/native/",
)
MACOS_INPUTS = {
    ".github/workflows/sdk-conformance.yml",
    "pnpm-workspace.yaml",
    ".npmrc",
    "packages/sdk-tools/src/workflows/generate.ts",
    "packages/sdk-tools/requirements.in",
    "packages/sdk-tools/requirements.lock",
    "packages/sdk-tools/package.json",
    "packages/sdk-rust/Cargo.toml",
    "packages/sdk-python/pyproject.toml",
    "packages/sdk-typescript/package.json",
    "packages/sdk-tools/tests/unit/process.test.ts",
    "packages/sdk-tools/tests/unit/backend.test.ts",
    "packages/sdk-tools/tests/conformance/transport.ts",
    "rust-toolchain.toml",
    "mise.toml",
}
WORKSPACE_INPUTS = {"package.json", "pnpm-lock.yaml", "pnpm-workspace.yaml", ".npmrc"}
WORKFLOWS = {
    ".github/workflows/ci.yml": {"backend", "integration", "web", "cli", "sdk"},
    ".github/workflows/cli.yml": {"cli", "cli_dependencies"},
    ".github/workflows/sdk-conformance.yml": {"sdk", "sdk_macos"},
    ".github/workflows/codeql.yml": {"codeql_python", "codeql_javascript"},
}


@dataclass(frozen=True, slots=True)
class Selection:
    """Private workflow decisions, without any claim that selected checks ran."""

    backend: bool = False
    integration: bool = False
    web: bool = False
    web_format: bool = False
    cli: bool = False
    cli_dependencies: bool = False
    sdk: bool = False
    sdk_macos: bool = False
    codeql_python: bool = False
    codeql_javascript: bool = False
    reasons: tuple[str, ...] = field(default=(), compare=False)


def _selection(enabled: set[str], reasons: tuple[str, ...]) -> Selection:
    return Selection(
        backend="backend" in enabled,
        integration="integration" in enabled,
        web="web" in enabled,
        web_format="web_format" in enabled,
        cli="cli" in enabled,
        cli_dependencies="cli_dependencies" in enabled,
        sdk="sdk" in enabled,
        sdk_macos="sdk_macos" in enabled,
        codeql_python="codeql_python" in enabled,
        codeql_javascript="codeql_javascript" in enabled,
        reasons=reasons,
    )


def _affects_sdk(path: str) -> bool:
    if path in SDK_INPUTS or path.startswith("packages/sdk-tools/fixtures/"):
        return True
    if path.startswith("packages/sdk-") and "/generated/" in path:
        return True
    return not path.endswith((".md", ".mdx")) and path.startswith(SDK_PREFIXES)


def _families(path: str) -> set[str]:
    if (
        path.startswith(".github/scripts/") and not path.endswith((".md", ".mdx"))
    ) or path == ".github/workflows/changes.yml":
        return set(FLAGS)
    if path in WORKFLOWS:
        return WORKFLOWS[path]

    enabled: set[str] = set()
    if _affects_sdk(path):
        enabled.add("sdk")
        if path in MACOS_INPUTS or path.startswith(MACOS_PREFIXES):
            enabled.add("sdk_macos")

    # CodeQL scans each selected language across the repository, including fixtures.
    suffix = Path(path).suffix
    if suffix == ".py" or Path(path).name in {
        "pyproject.toml",
        "uv.lock",
        "requirements.in",
        "requirements.lock",
        ".python-version",
    }:
        enabled.add("codeql_python")
    if suffix in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts"} or (
        Path(path).name == "package.json"
        or path in WORKSPACE_INPUTS
        or Path(path).name.startswith("tsconfig")
    ):
        enabled.add("codeql_javascript")

    web_resource = path.startswith(("apps/web/app/", "apps/web/src/", "apps/web/components/"))
    if path in {
        "prettier.config.mjs",
        ".prettierignore",
        ".editorconfig",
        "apps/web/.prettierrc",
        "apps/web/.prettierignore",
    } or (path.startswith("apps/web/") and path.endswith((".md", ".mdx")) and not web_resource):
        return enabled | {"web_format"}

    consumed = (
        path.startswith(
            (
                "packages/sdk-tools/fixtures/",
                "apps/backend/tests/fixtures/",
                "apps/backend/src/",
                "apps/cli/tests/fixtures/",
                "apps/cli/xtask/tests/fixtures/",
                "apps/cli/src/",
                "apps/cli/xtask/src/",
                "packages/sdk-rust/src/",
            )
        )
        or (path.startswith("packages/sdk-") and "/generated/" in path)
        or web_resource
    )
    if path.endswith((".md", ".mdx")) and not consumed:
        return enabled

    if path in WORKSPACE_INPUTS:
        return enabled | {"backend", "integration", "web", "sdk"}
    if path == "mise.toml":
        return set(FLAGS)
    if path in {"Cargo.toml", "Cargo.lock", "rust-toolchain.toml"} or path.startswith(".cargo/"):
        return enabled | {"cli", "cli_dependencies", "sdk"}
    if Path(path).name == "Cargo.toml" and path.startswith(("apps/cli/", "packages/sdk-")):
        return enabled | {"cli", "cli_dependencies", "sdk"}
    if path == "deny.toml":
        return {"cli_dependencies"}
    if path == "dist-workspace.toml":
        return {"cli"}
    if path == "turbo.json":
        return {"backend", "web", "cli", "sdk"}
    if path.startswith(("apps/cli/", "packages/sdk-rust/")):
        return enabled | {"cli"}
    if path.startswith("apps/web/"):
        return enabled | {"web"}
    if path.startswith("apps/backend/"):
        enabled.add("backend")
        if path.startswith(
            (
                "apps/backend/src/",
                "apps/backend/migrations/",
                "apps/backend/tests/support/",
                "apps/backend/tests/integration/",
                "apps/backend/tests/fixtures/",
            )
        ) or path in {
            "apps/backend/tests/conftest.py",
            "apps/backend/tests/__init__.py",
            "apps/backend/package.json",
            "apps/backend/pyproject.toml",
            "apps/backend/uv.lock",
            "apps/backend/.python-version",
            "apps/backend/.env.test.example",
            "apps/backend/alembic.ini",
            "apps/backend/Dockerfile.integration",
            "apps/backend/Dockerfile",
        }:
            enabled.add("integration")
        return enabled
    if path in {
        "compose.test.yaml",
        ".dockerignore",
        "scripts/test-integration.sh",
        "scripts/dev-compose.sh",
    } or path.startswith("config/"):
        return enabled | {"backend", "integration"}
    if path.startswith("contracts/openapi/"):
        return enabled | {"backend", "sdk"}
    if path.startswith("packages/sdk-"):
        return enabled
    if path in {
        "prettier.config.mjs",
        ".prettierignore",
        ".editorconfig",
        "commitlint.config.cjs",
    } or path.startswith(("docs/", ".agents/", ".husky/")):
        return enabled
    if path in {".github/dependabot.yml", ".github/CODEOWNERS"} or path.startswith(
        ".github/ISSUE_TEMPLATE/"
    ):
        return enabled
    return set(FLAGS)


def select(paths: list[str]) -> Selection:
    """Choose relevant families, retaining consumed fixture and build inputs."""
    enabled: set[str] = set()
    reasons: list[str] = []
    for path in paths:
        families = _families(path)
        enabled.update(families)
        explanation = ", ".join(sorted(families)) if families else "formatting/commit checks only"
        if families == set(FLAGS):
            explanation += " (shared selection/toolchain input or conservative fallback)"
        reasons.append(f"{json.dumps(path, ensure_ascii=True)}: {explanation}")
    return _selection(enabled, tuple(reasons))


def detect(event: str, base: str, head: str, root: Path, *, macos: bool = True) -> Selection:
    """Read the complete event diff or select the documented full-run policy."""
    if event == "schedule":
        return _selection(
            {"cli_dependencies", "codeql_python", "codeql_javascript"},
            ("Scheduled security checks use current advisories and analysis queries.",),
        )
    if event not in {"pull_request", "push", "workflow_dispatch"}:
        raise ValueError("Unsupported CI event")
    if event == "workflow_dispatch" or not base or set(base) == {"0"}:
        enabled: set[str] = set(FLAGS)
        if event == "workflow_dispatch" and not macos:
            enabled.remove("sdk_macos")
        return _selection(enabled, ("Manual full verification or no initial comparison baseline.",))
    revisions = [f"{base}...{head}"] if event == "pull_request" else [base, head]
    paths = (
        subprocess.check_output(
            ["git", "diff", "--name-only", "--no-renames", "-z", *revisions, "--"],
            cwd=root,
        )
        .decode("utf-8", errors="surrogateescape")
        .split("\0")
    )
    return select([path for path in paths if path])


def main() -> int:
    """Publish selection only after successful comparison and validation."""
    try:
        macos = os.environ.get("MACOS", "true")
        if macos not in {"true", "false"}:
            raise ValueError("Invalid manual platform choice")
        result = detect(
            os.environ["EVENT"],
            os.environ.get("BASE", ""),
            os.environ.get("HEAD", "HEAD"),
            Path.cwd(),
            macos=macos == "true",
        )
        outputs = {name: str(getattr(result, name)).lower() for name in FLAGS}
        matrix = {
            "include": [
                {"language": language, "os": platform}
                for language in ("rust", "typescript", "python")
                for platform in ("ubuntu-26.04", "macos-15")
                if platform == "ubuntu-26.04" or result.sdk_macos
            ]
        }
        outputs["sdk_matrix"] = json.dumps(matrix)
        with open(os.environ["GITHUB_OUTPUT"], "a") as output:
            output.writelines(f"{name}={value}\n" for name, value in outputs.items())
        summary = (
            "## CI selection\n\nEach caller executes its own relevant families.\n\n"
            "| Check family | Relevant |\n| --- | --- |\n"
        )
        summary += "".join(f"| {name} | {outputs[name]} |\n" for name in FLAGS)
        summary += "\nReasons (JSON-escaped original paths):\n\n```text\n"
        # Escape fence markers in untrusted filenames before rendering the summary.
        summary += "\n".join(
            "  " + reason.replace("```", "\\u0060\\u0060\\u0060") for reason in result.reasons
        )
        summary += "\n```\n\nSelection is not execution evidence.\n"
        print(summary)
        if summary_path := os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(summary_path, "a") as report:
                report.write(summary)
        return 0
    except (KeyError, OSError, ValueError, subprocess.CalledProcessError):
        print(
            "CI change detection failed. No successful skip was established.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
