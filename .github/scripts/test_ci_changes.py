"""Exercise check selection and the real Git comparison without application services."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ci_changes import FLAGS, Selection, detect, select


class SelectionTests(unittest.TestCase):
    """Keep unrelated prose cheap while retaining real component dependencies."""

    def test_specification_pr_270_needs_no_application_checks(self) -> None:
        paths = [
            ".agents/skills/inframeld-access-models/references/grant-contracts.md",
            ".agents/skills/inframeld-access-models/references/human-cli-credential-lifecycle.md",
            ".agents/skills/inframeld-application-contracts/SKILL.md",
            ".agents/skills/inframeld-application-contracts/references/cli-change-review.md",
            ".agents/skills/inframeld-application-contracts/references/cli-context-portability-and-recovery.md",
            ".agents/skills/inframeld-application-contracts/references/cli-output-and-automation.md",
            ".agents/skills/inframeld-application-contracts/references/cli-presentation-components.md",
            ".agents/skills/inframeld-application-contracts/references/cli-result-contracts.md",
            ".agents/skills/inframeld-application-contracts/references/idempotency-and-replay.md",
            ".agents/skills/inframeld-application-contracts/references/jobs-and-recovery.md",
            ".agents/skills/inframeld-application-contracts/references/operation-recovery-contracts.md",
            ".agents/skills/inframeld-knowledge/references/project-deletion.md",
            ".agents/skills/inframeld-rust-standards/SKILL.md",
            ".agents/skills/inframeld-rust-standards/references/cli-structure.md",
            "apps/cli/AGENTS.md",
            "apps/cli/README.md",
            "docs/development/guides/contracts-and-data.md",
        ]
        self.assertEqual(select(paths), Selection())

    def test_component_checks_follow_consumed_inputs(self) -> None:
        cases = [
            (
                "apps/backend/src/inframeld_backend/main.py",
                {"backend", "integration", "sdk", "codeql_python"},
            ),
            (
                "apps/backend/tests/unit/access/test_grant.py",
                {"backend", "codeql_python"},
            ),
            (
                "apps/backend/tests/unit/contract/test_consent.py",
                {"backend", "sdk", "codeql_python"},
            ),
            (
                "apps/backend/tests/integration/access/test_session.py",
                {"backend", "integration", "codeql_python"},
            ),
            (
                "apps/backend/tests/support/postgres.py",
                {"backend", "integration", "codeql_python"},
            ),
            (
                "apps/backend/tests/support/sdk_server.py",
                {"backend", "integration", "sdk", "codeql_python"},
            ),
            (
                "apps/backend/migrations/versions/001.py",
                {"backend", "integration", "codeql_python"},
            ),
            ("compose.test.yaml", {"backend", "integration"}),
            ("scripts/test-integration.sh", {"backend", "integration"}),
            ("config/kratos/test.yaml", {"backend", "integration"}),
            ("apps/web/app/page.tsx", {"web", "codeql_javascript"}),
            ("apps/cli/src/app.rs", {"cli"}),
            ("apps/cli/xtask/src/package.rs", {"cli"}),
            ("apps/cli/compatibility.json", {"cli"}),
            ("packages/sdk-rust/src/lib.rs", {"cli", "sdk"}),
            (
                "packages/sdk-tools/src/system/run.ts",
                {"sdk", "sdk_macos", "codeql_javascript"},
            ),
            ("contracts/openapi/v1/inframeld-v1.json", {"backend", "sdk"}),
            ("deny.toml", {"cli_dependencies"}),
        ]
        for path, expected in cases:
            with self.subTest(path=path):
                actual = select([path])
                enabled = {name for name in FLAGS if getattr(actual, name)}
                self.assertEqual(enabled, expected)

    def test_consumed_markdown_is_not_mistaken_for_prose(self) -> None:
        for path in [
            "packages/sdk-rust/generated/docs/Session.md",
            "packages/sdk-tools/fixtures/input.md",
        ]:
            with self.subTest(path=path):
                self.assertTrue(select([path]).sdk)
        self.assertTrue(select(["apps/backend/tests/fixtures/input.md"]).integration)
        self.assertTrue(select(["apps/cli/tests/fixtures/help.md"]).cli)
        self.assertTrue(select(["apps/cli/src/help.md"]).cli)
        self.assertTrue(select(["packages/sdk-rust/src/help.md"]).cli)
        self.assertTrue(select(["apps/backend/src/inframeld_backend/template.md"]).integration)
        self.assertTrue(select(["apps/web/app/page.mdx"]).web)

    def test_workspace_bootstrap_does_not_select_native_cargo_jobs(self) -> None:
        for path in ["package.json", "pnpm-lock.yaml", "pnpm-workspace.yaml", ".npmrc"]:
            with self.subTest(path=path):
                actual = select([path])
                self.assertTrue(actual.backend and actual.integration and actual.web and actual.sdk)
                self.assertFalse(actual.cli or actual.cli_dependencies)
        self.assertTrue(select(["pnpm-workspace.yaml"]).sdk_macos)

    def test_web_prose_and_shared_formatter_config_need_formatting_dependencies_only(self) -> None:
        for path in [
            "apps/web/README.md",
            "prettier.config.mjs",
            ".prettierignore",
            ".editorconfig",
        ]:
            with self.subTest(path=path):
                actual = select([path])
                self.assertTrue(actual.web_format)
                self.assertFalse(actual.web or actual.cli or actual.integration or actual.sdk)

    def test_cargo_workspace_inputs_select_rust_consumers_and_audits(self) -> None:
        for path in [
            "Cargo.toml",
            "Cargo.lock",
            "apps/cli/Cargo.toml",
            "packages/sdk-tools/drivers/rust/Cargo.toml",
        ]:
            with self.subTest(path=path):
                actual = select([path])
                self.assertTrue(actual.cli and actual.cli_dependencies and actual.sdk)
                self.assertFalse(actual.integration or actual.web)

    def test_workflow_changes_select_their_checks(self) -> None:
        cases = [
            (
                ".github/workflows/ci.yml",
                {"backend", "integration", "web", "cli", "sdk"},
            ),
            (".github/workflows/cli.yml", {"cli", "cli_dependencies"}),
            (".github/workflows/sdk-conformance.yml", {"sdk", "sdk_macos"}),
            (".github/workflows/codeql.yml", {"codeql_python", "codeql_javascript"}),
        ]
        for path, expected in cases:
            with self.subTest(path=path):
                actual = select([path])
                self.assertEqual({name for name in FLAGS if getattr(actual, name)}, expected)

    def test_unknown_inputs_and_selector_changes_select_full_checks(self) -> None:
        for path in [
            "new-runtime/input.bin",
            ".github/scripts/ci_changes.py",
            ".github/workflows/changes.yml",
        ]:
            with self.subTest(path=path):
                actual = select([path])
                self.assertTrue(all(getattr(actual, name) for name in FLAGS))


class GitComparisonTests(unittest.TestCase):
    """Prove cumulative PR diffs, push ranges and comparison failures against Git."""

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.git("init", "--quiet", "--initial-branch=main")
        self.git("config", "user.name", "CI selection test")
        self.git("config", "user.email", "ci-selection@example.invalid")
        self.base = self.commit("README.md", "baseline")

    def git(self, *arguments: str) -> str:
        return subprocess.check_output(["git", *arguments], cwd=self.root, text=True).strip()

    def commit(self, name: str, content: str) -> str:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        self.git("add", "--all")
        self.git("commit", "--quiet", "-m", "test: record input")
        return self.git("rev-parse", "HEAD")

    def test_later_documentation_commit_keeps_earlier_code_relevant(self) -> None:
        self.git("switch", "--quiet", "-c", "feature")
        self.commit("apps/cli/src/app.rs", "fn main() {}")
        head = self.commit("README.md", "later prose")
        self.assertTrue(detect("pull_request", self.base, head, self.root).cli)

    def test_base_branch_only_changes_do_not_select_pr_checks(self) -> None:
        self.git("switch", "--quiet", "-c", "feature")
        head = self.commit("README.md", "feature prose")
        self.git("switch", "--quiet", "main")
        base = self.commit("apps/web/app/page.tsx", "export default null")
        self.assertEqual(detect("pull_request", base, head, self.root), Selection())

    def test_push_compares_the_actual_before_and_after(self) -> None:
        previous = self.commit("apps/cli/src/app.rs", "fn main() {}")
        head = self.commit("README.md", "later prose")
        self.assertEqual(detect("push", previous, head, self.root), Selection())
        self.assertTrue(detect("push", self.base, head, self.root).cli)

    def test_rename_retains_deleted_and_new_component_inputs(self) -> None:
        base = self.commit("apps/cli/src/app.rs", "shared bytes")
        target = self.root / "apps/web/app/page.tsx"
        target.parent.mkdir(parents=True, exist_ok=True)
        (self.root / "apps/cli/src/app.rs").rename(target)
        head = self.commit("README.md", "record rename")
        actual = detect("push", base, head, self.root)
        self.assertTrue(actual.cli and actual.web)

    def test_unusual_and_deleted_filenames_remain_data(self) -> None:
        name = "apps/cli/tests/é\n$(touch should-not-exist).rs"
        head = self.commit(name, "fixture")
        self.assertTrue(detect("push", self.base, head, self.root).cli)
        (self.root / name).unlink()
        removed = self.commit("README.md", "record deletion")
        self.assertTrue(detect("push", head, removed, self.root).cli)
        self.assertFalse((self.root / "should-not-exist").exists())

    def test_manual_missing_baseline_and_scheduled_security_selection(self) -> None:
        for event, base in [
            ("workflow_dispatch", ""),
            ("push", ""),
            ("push", "0" * 40),
        ]:
            with self.subTest(event=event, base=base):
                actual = detect(event, base, "HEAD", self.root)
                self.assertTrue(all(getattr(actual, name) for name in FLAGS))
        actual = detect("workflow_dispatch", "", "HEAD", self.root, macos=False)
        self.assertTrue(actual.sdk)
        self.assertFalse(actual.sdk_macos)
        self.assertEqual(
            detect("schedule", "", "HEAD", self.root),
            Selection(cli_dependencies=True, codeql_python=True, codeql_javascript=True),
        )

    def test_failed_comparison_exits_without_publishing_skip_outputs(self) -> None:
        output = self.root / "outputs"
        environment = {
            **os.environ,
            "EVENT": "pull_request",
            "BASE": "f" * 40,
            "HEAD": self.base,
            "GITHUB_OUTPUT": str(output),
        }
        result = subprocess.run(
            [sys.executable, str(Path(__file__).with_name("ci_changes.py"))],
            cwd=self.root,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CI change detection failed", result.stderr)
        self.assertFalse(output.exists() and output.read_text())

    def test_invalid_manual_platform_choice_cannot_publish_partial_verification(self) -> None:
        output = self.root / "outputs"
        environment = {
            **os.environ,
            "EVENT": "workflow_dispatch",
            "MACOS": "not-a-boolean",
            "GITHUB_OUTPUT": str(output),
        }
        result = subprocess.run(
            [sys.executable, str(Path(__file__).with_name("ci_changes.py"))],
            cwd=self.root,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(output.exists() and output.read_text())

    def test_entry_point_publishes_valid_flags_matrix_and_explanation(self) -> None:
        for macos, expected in [("true", 6), ("false", 3)]:
            with self.subTest(macos=macos):
                output = self.root / f"outputs-{macos}"
                summary = self.root / f"summary-{macos}"
                environment = {
                    **os.environ,
                    "EVENT": "workflow_dispatch",
                    "MACOS": macos,
                    "GITHUB_OUTPUT": str(output),
                    "GITHUB_STEP_SUMMARY": str(summary),
                }
                result = subprocess.run(
                    [sys.executable, str(Path(__file__).with_name("ci_changes.py"))],
                    cwd=self.root,
                    env=environment,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                values = dict(line.split("=", 1) for line in output.read_text().splitlines())
                self.assertTrue(all(values[name] in {"true", "false"} for name in FLAGS))
                matrix: dict[str, list[dict[str, str]]] = json.loads(values["sdk_matrix"])
                self.assertEqual(len(matrix["include"]), expected)
                self.assertEqual(values["sdk_macos"], macos)
                self.assertIn("Manual full verification", summary.read_text())

    def test_more_than_three_hundred_files_are_not_truncated(self) -> None:
        # The relevant runtime file sorts after every prose file in Git's output.
        (self.root / "aaa").mkdir()
        for index in range(310):
            (self.root / "aaa" / f"prose-{index}.md").write_text("prose")
        head = self.commit("apps/cli/src/app.rs", "fn main() {}")
        self.assertTrue(detect("push", self.base, head, self.root).cli)


if __name__ == "__main__":
    unittest.main()
