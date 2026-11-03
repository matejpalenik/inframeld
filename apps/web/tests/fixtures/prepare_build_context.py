"""Stage the account UI's public build inputs without host credentials or caches."""

import fnmatch
import os
import shutil
import signal
import stat
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
    source: Path, destination: Path, *, recipient_proof: bool = False
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
    except BaseException:
        shutil.rmtree(destination)
        raise


def terminate(signum: int, _frame: FrameType | None) -> NoReturn:
    raise SystemExit(128 + signum)


def main() -> int:
    if len(sys.argv) not in (3, 4) or (len(sys.argv) == 4 and sys.argv[3] != "--recipient-proof"):
        return 2
    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    try:
        prepare_build_context(
            Path(sys.argv[1]), Path(sys.argv[2]), recipient_proof=len(sys.argv) == 4
        )
    except (OSError, ValueError):
        print("The private web build context could not be prepared.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
