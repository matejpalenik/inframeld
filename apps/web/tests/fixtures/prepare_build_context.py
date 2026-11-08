"""Stage the account UI's public build inputs without host credentials or caches."""

import fnmatch
import os
import shutil
import signal
import stat
import subprocess
import sys
from pathlib import Path
from types import FrameType
from typing import NoReturn

ROOT_FILES = (".npmrc", "package.json", "pnpm-lock.yaml", "pnpm-workspace.yaml")
SOURCE_TREES = ("apps/web", "packages/sdk-typescript")
PROOF_ROOT_FILES = (
    "Cargo.toml",
    "Cargo.lock",
    "rust-toolchain.toml",
    "apps/web/tests/fixtures/recipient-proof.Dockerfile",
    "apps/web/tests/fixtures/.dockerignore",
)
PROOF_SOURCE_TREES = (
    "apps/cli",
    "packages/sdk-rust",
    "packages/sdk-tools/drivers/rust",
    "packages/sdk-tools/fixtures/rust",
    "packages/sdk-tools/fixtures/rust-capabilities",
)
EXCLUDED_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".aws",
    ".ssh",
    ".codex",
    ".agents",
    ".auth",
    ".npmrc",
    ".netrc",
    ".pypirc",
    ".npm",
    ".cache",
    ".pnpm-store",
    ".cargo",
    "target",
    "node_modules",
    ".next",
    ".turbo",
    "out",
    "build",
    "dist",
    "coverage",
    "test-results",
    "playwright-report",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".pyright",
    "secrets",
    ".DS_Store",
}
EXCLUDED_PATTERNS = (
    ".env*",
    "*.env",
    "*.env.*",
    "*.key",
    "*.pem",
    "*.p12",
    "*.pfx",
    "*.crt",
    "*.log",
    "*.tsbuildinfo",
    "*.pyc",
    "*.pyo",
)


def excluded(name: str) -> bool:
    return name in EXCLUDED_NAMES or any(
        fnmatch.fnmatchcase(name, pattern) for pattern in EXCLUDED_PATTERNS
    )


def open_input(root: int, relative: str) -> int:
    """Anchor every component to an allocated input, refusing links before opening."""
    current = os.dup(root)
    try:
        parts = Path(relative).parts
        for index, part in enumerate(parts):
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            if index < len(parts) - 1:
                flags |= os.O_DIRECTORY
            next_descriptor = os.open(part, flags, dir_fd=current)
            os.close(current)
            current = next_descriptor
        return current
    except BaseException:
        os.close(current)
        raise


def copy_input(descriptor: int, destination: Path) -> None:
    mode = os.fstat(descriptor).st_mode
    if stat.S_ISDIR(mode):
        destination.mkdir(mode=0o755)
        destination.chmod(0o755)
        for name in sorted(os.listdir(descriptor)):
            if excluded(name):
                continue
            child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
            try:
                copy_input(child, destination / name)
            finally:
                os.close(child)
    elif stat.S_ISREG(mode):
        with (
            os.fdopen(os.dup(descriptor), "rb") as source,
            destination.open("xb") as target,
        ):
            shutil.copyfileobj(source, target)
            os.fchmod(target.fileno(), 0o755 if mode & 0o111 else 0o644)
    else:
        raise ValueError("Only regular public source files and directories may be staged.")


def require_public_npm_policy(descriptor: int) -> None:
    """Preserve the committed policy without accepting registry credentials."""
    with os.fdopen(os.dup(descriptor), "r") as policy:
        for raw in policy:
            line = raw.strip()
            if not line or line.startswith(("#", ";")):
                continue
            key, separator, value = line.partition("=")
            valid = separator and (
                key.strip() == "min-release-age"
                and value.strip().isdecimal()
                or key.strip() == "engine-strict"
                and value.strip() in {"true", "false"}
            )
            if not valid:
                raise ValueError("Only public pnpm policy belongs in the fixture context.")
    os.lseek(descriptor, 0, os.SEEK_SET)


def prepare_build_context(
    source: Path,
    destination: Path,
    *,
    recipient_proof: bool = False,
    invitation_guide: bool = False,
) -> None:
    # Refuse preexisting state. Only this freshly created context may be removed on failure.
    destination.mkdir(mode=0o700)
    try:
        destination.chmod(0o700)
        root = os.open(source, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for name in PROOF_ROOT_FILES if recipient_proof else ROOT_FILES:
                descriptor = open_input(root, name)
                try:
                    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                        raise ValueError("A required public pnpm input is not a regular file.")
                    if name == ".npmrc":
                        require_public_npm_policy(descriptor)
                    target = destination / name
                    target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
                    copy_input(descriptor, target)
                finally:
                    os.close(descriptor)
            for name in PROOF_SOURCE_TREES if recipient_proof else SOURCE_TREES:
                descriptor = open_input(root, name)
                try:
                    if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
                        raise ValueError("A required public source input is not a directory.")
                    parent = destination / Path(name).parent
                    parent.mkdir(mode=0o755, parents=True, exist_ok=True)
                    parent.chmod(0o755)
                    copy_input(descriptor, destination / name)
                finally:
                    os.close(descriptor)
        finally:
            os.close(root)
        shutil.copyfile(
            destination / "apps/web/tests/fixtures/.dockerignore",
            destination / ".dockerignore",
        )
        (destination / ".dockerignore").chmod(0o644)
        if invitation_guide:
            prepare_invitation_guide(source, destination)
    except BaseException:
        shutil.rmtree(destination)
        raise


def terminate(signum: int, _frame: FrameType | None) -> NoReturn:
    raise SystemExit(128 + signum)


def prepare_invitation_guide(source: Path, destination: Path) -> None:
    """Bundle the literal browser guide for the existing private account image."""
    root = os.open(source, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        descriptor = open_input(root, "apps/docs/src/app/guides/manage-invitations/page.mdx")
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ValueError("The browser guide must be regular public source.")
            with os.fdopen(os.dup(descriptor), "rb") as document:
                body = document.read(131_073)
        finally:
            os.close(descriptor)
    finally:
        os.close(root)
    if len(body) > 131_072:
        raise ValueError("The browser guide exceeded its fixed input bound.")
    marker = b'```typescript {{ title: "TypeScript (browser)" }}\n'
    if body.count(marker) != 1:
        raise ValueError("The guide must contain one literal browser program.")
    program, separator, _tail = body.split(marker, 1)[1].partition(b"\n```")
    if not separator:
        raise ValueError("The literal browser program is incomplete.")
    entry = destination.parent / "invitation-guide.ts"
    with entry.open("xb") as output:
        output.write(program + b"\n")
        os.fchmod(output.fileno(), 0o600)
    bundle = destination / "apps/web/tests/fixtures/invitation-guide.iife.js"
    # This child shares the existing preparation phase's group and 30-second budget.
    subprocess.run(
        [
            str(source / "packages/sdk-tools/node_modules/esbuild/bin/esbuild"),
            str(entry),
            "--bundle",
            "--platform=browser",
            "--format=iife",
            f"--alias:@inframeld/sdk={source / 'packages/sdk-typescript/index.ts'}",
            f"--outfile={bundle}",
            "--log-level=warning",
        ],
        cwd=source,
        stdin=subprocess.DEVNULL,
        check=True,
    )
    bundle.chmod(0o644)


def main() -> int:
    if len(sys.argv) not in (3, 4) or (
        len(sys.argv) == 4 and sys.argv[3] not in {"--recipient-proof", "--invitation-guide"}
    ):
        return 2
    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    try:
        prepare_build_context(
            Path(sys.argv[1]),
            Path(sys.argv[2]),
            recipient_proof=sys.argv[3:] == ["--recipient-proof"],
            invitation_guide=sys.argv[3:] == ["--invitation-guide"],
        )
    except (OSError, ValueError, subprocess.CalledProcessError):
        print("The private web build context could not be prepared.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
