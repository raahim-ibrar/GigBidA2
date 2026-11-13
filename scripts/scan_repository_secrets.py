"""Run Gitleaks on tracked/publishable files and Git history, never the private .env."""

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.check_assignment import ROOT, files


def run(binary, root=ROOT):
    with TemporaryDirectory(prefix="gigbid-secret-check-") as temporary:
        base = Path(temporary)
        exported = base / "source"
        exported.mkdir()
        config = base / "defaults.toml"
        config.write_text("[extend]\nuseDefault = true\n", encoding="utf-8")
        ignore = base / "empty.ignore"
        ignore.write_text("", encoding="utf-8")
        for name in files(root):
            source = root / name
            if source.is_symlink() or not source.resolve().is_relative_to(root.resolve()):
                raise ValueError("Refusing symlink/outside-root source: " + name)
            if source.is_file():
                target = exported / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        for mode, location in (("dir", exported), ("git", root)):
            report = base / (mode + ".json")
            command = [
                binary,
                mode,
                str(location),
                "--redact=100",
                "--no-banner",
                "--ignore-gitleaks-allow",
                "--config=" + str(config),
                "--gitleaks-ignore-path=" + str(ignore),
                "--report-format=json",
                "--report-path=" + str(report),
            ]
            if mode == "git":
                command.append("--log-opts=--all")
            result = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=180)
            if result.returncode:
                findings = json.loads(report.read_text()) if report.is_file() else []
                # Emit locations/rules only, never raw matching lines or secret values.
                safe = [
                    {k: row.get(k) for k in ("RuleID", "File", "StartLine")} for row in findings
                ]
                print(json.dumps({"scan": mode, "findings": safe}))
                raise ValueError("Gitleaks failed or found potential secrets; review locally")
            print("Gitleaks " + mode + " scan passed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", default="gitleaks")
    args = parser.parse_args()
    try:
        run(args.binary)
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"Secret check failed: {error}\n")
