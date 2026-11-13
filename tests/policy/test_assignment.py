import contextlib
import io
import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scripts import check_assignment as policy
from scripts.scan_repository_secrets import run as scan


class AssignmentRules(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.write("gigsim/.gitkeep", "")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Policy Fixture",
                "-c",
                "user.email=fixture@example.org",
                "commit",
                "-qm",
                "baseline",
            ],
            cwd=self.root,
            check=True,
        )
        self.baseline = policy.git(self.root, "rev-parse", "HEAD").decode().strip()
        self.write("agent/config.yaml", "profiles:\n  open:\n    models:\n      writer: fixture\n")
        self.write("agent/prompts/writer.md", "Fixture prompt")

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_gigsim_edits_additions_and_deletions_fail(self):
        policy.protected_tree(self.root, self.baseline)
        self.write("gigsim/new.py", "pass")
        with self.assertRaisesRegex(ValueError, "tree changed"):
            policy.protected_tree(self.root, self.baseline)
        (self.root / "gigsim/new.py").unlink()
        self.write("gigsim/.gitkeep", "modified")
        with self.assertRaisesRegex(ValueError, "tree changed"):
            policy.protected_tree(self.root, self.baseline)
        (self.root / "gigsim/.gitkeep").unlink()
        with self.assertRaisesRegex(ValueError, "tree changed"):
            policy.protected_tree(self.root, self.baseline)

    def test_prompt_files_and_inline_system_instructions_fail(self):
        policy.prompt_locations(self.root, policy.files(self.root))
        self.write("simulator/client_prompt.md", "Misplaced fixture")
        with self.assertRaisesRegex(ValueError, "Prompt-location"):
            policy.prompt_locations(self.root, policy.files(self.root))
        (self.root / "simulator/client_prompt.md").unlink()
        for text in (
            'messages = [{"role": "system", "content": "Inline fixture"}]',
            'model(prompt="Inline fixture")',
        ):
            self.write("agent/consumer.py", text)
            with self.assertRaisesRegex(ValueError, "inline"):
                policy.prompt_locations(self.root, policy.files(self.root))

    def test_missing_configured_prompt_fails(self):
        (self.root / "agent/prompts/writer.md").unlink()
        with self.assertRaisesRegex(ValueError, "Missing configured"):
            policy.prompt_locations(self.root, policy.files(self.root))

    def ledger(self):
        source = self.write("evals/results/fixture.json", '{"observed": 42}')
        documents = {}
        for name in ("README.md", "output/pdf/GigBid_RnD_Report.pdf"):
            text = "Fixture measurement 42"
            self.write(name, text)
            documents[name] = {
                "fixture": {
                    "text_sha256": policy.sha(text.encode()),
                    "numeric_tokens": ["42"],
                    "scope": "Fixture evidence",
                    "sources": [
                        {
                            "path": "evals/results/fixture.json",
                            "sha256": policy.evidence_sha(source),
                        }
                    ],
                }
            }
        ledger = {"documents": documents}
        self.write("evals/results/numeric-claim-provenance.json", json.dumps(ledger))
        return ledger

    def test_claim_changes_and_changed_or_missing_evidence_fail(self):
        self.ledger()
        with patch.object(
            policy,
            "document_blocks",
            side_effect=lambda root, name: {"fixture": (root / name).read_text()},
        ):
            self.assertEqual(policy.numeric_provenance(self.root), 2)
            self.write("README.md", "Fixture measurement 43")
            with self.assertRaisesRegex(ValueError, "claims changed"):
                policy.numeric_provenance(self.root)
            self.ledger()
            self.write("evals/results/fixture.json", '{"observed": 99}')
            with self.assertRaisesRegex(ValueError, "evidence missing or changed"):
                policy.numeric_provenance(self.root)
            self.ledger()
            (self.root / "evals/results/fixture.json").unlink()
            with self.assertRaisesRegex(ValueError, "evidence missing or changed"):
                policy.numeric_provenance(self.root)

    def test_numeric_evidence_cannot_escape_results(self):
        ledger = self.ledger()
        ledger["documents"]["README.md"]["fixture"]["sources"][0]["path"] = "../../private.json"
        self.write("evals/results/numeric-claim-provenance.json", json.dumps(ledger))
        with patch.object(
            policy, "document_blocks", return_value={"fixture": "Fixture measurement 42"}
        ):
            with self.assertRaisesRegex(ValueError, "under evals/results"):
                policy.numeric_provenance(self.root)

    def test_private_env_file_is_rejected_without_reading_its_contents(self):
        self.write(".env", "PRIVATE_FIXTURE_CONTENT")
        with self.assertRaisesRegex(ValueError, "Private credential file"):
            policy.check(self.root)

    def test_secret_diagnostics_never_print_matching_text(self):
        def fake_gitleaks(command, **kwargs):
            report = next(x.split("=", 1)[1] for x in command if x.startswith("--report-path="))
            Path(report).write_text(
                json.dumps(
                    [
                        {
                            "RuleID": "fixture",
                            "File": "fixture.py",
                            "StartLine": 1,
                            "Secret": "PRIVATE_CANARY",
                            "Match": "PRIVATE_CANARY",
                        }
                    ]
                )
            )
            return subprocess.CompletedProcess(command, 1)

        output = io.StringIO()
        with (
            patch("scripts.scan_repository_secrets.subprocess.run", side_effect=fake_gitleaks),
            patch("scripts.scan_repository_secrets.files", return_value=["gigsim/.gitkeep"]),
        ):
            with (
                contextlib.redirect_stdout(output),
                self.assertRaisesRegex(ValueError, "Gitleaks failed"),
            ):
                scan("fixture-binary", self.root)
        self.assertNotIn("PRIVATE_CANARY", output.getvalue())
        self.assertIn("fixture.py", output.getvalue())


if __name__ == "__main__":
    unittest.main()
