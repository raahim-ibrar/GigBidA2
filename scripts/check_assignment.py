"""Offline checks for the PDF's repository rules; not a grading/completion oracle."""

import argparse
import ast
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "e2596e9f2411fd7228a6ea1c6e68d08e9683df0e"
NUMBER = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?%?(?![\w.])")


def git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root)


def files(root):
    names = git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    return sorted(set(n.decode("utf-8") for n in names.split(b"\0") if n))


def sha(content):
    return hashlib.sha256(content).hexdigest()


def evidence_sha(path):
    content = path.read_bytes()
    if path.suffix in {".json", ".jsonl", ".md", ".csv"}:
        content = content.replace(b"\r\n", b"\n")
    return sha(content)


def protected_tree(root, baseline=BASELINE):
    expected = {}
    for entry in git(root, "ls-tree", "-rz", baseline, "--", "gigsim").split(b"\0"):
        if entry:
            _, name = entry.split(b"\t", 1)
            name = name.decode()
            expected[name] = sha(git(root, "show", baseline + ":" + name))
    if not expected:
        raise ValueError("Trusted gigsim baseline is missing; fetch full history")
    actual = {}
    for path in (root / "gigsim").rglob("*"):
        if path.is_symlink():
            raise ValueError("gigsim contains a symlink")
        if path.is_file():
            actual[path.relative_to(root).as_posix()] = sha(path.read_bytes())
    if actual != expected:
        raise ValueError("Protected gigsim tree changed (addition, deletion or content edit)")


def prompt_locations(root, names):
    def inline(value):
        if isinstance(value, ast.Constant):
            return isinstance(value.value, str) and bool(value.value.strip())
        if isinstance(value, ast.JoinedStr):
            return any(inline(part) for part in value.values)
        if isinstance(value, ast.BinOp):
            return inline(value.left) or inline(value.right)
        return False  # Loader-call filenames are not inline instructions.

    violations = []
    source_roots = {
        "agent",
        "apps",
        "rag",
        "simulator",
        "evals",
        "mcp_servers",
        "worker",
        "scripts",
    }
    for name in names:
        path = root / name
        if name.startswith("evals/results/") or not path.is_file():
            continue  # Immutable as-run source snapshots are evidence, not active prompts.
        if path.suffix in {".md", ".txt", ".j2", ".jinja", ".jinja2"}:
            if "prompt" in path.stem.lower() and not name.startswith("agent/prompts/"):
                violations.append(name)
        if path.suffix != ".py" or name.split("/")[0] not in source_roots:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=name)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                for keyword in node.keywords:
                    is_system = keyword.arg in {"prompt", "system_prompt", "system_instruction"}
                    is_system = is_system or (
                        keyword.arg == "content"
                        and isinstance(node.func, ast.Name)
                        and node.func.id == "SystemMessage"
                    )
                    if is_system and inline(keyword.value):
                        violations.append(f"{name}:{node.lineno} inline prompt argument")
            if isinstance(node, ast.Dict):
                fields = {
                    k.value: v
                    for k, v in zip(node.keys, node.values)
                    if isinstance(k, ast.Constant)
                }
                role, content = fields.get("role"), fields.get("content")
                if (
                    isinstance(role, ast.Constant)
                    and role.value == "system"
                    and isinstance(content, (ast.Constant, ast.JoinedStr))
                ):
                    violations.append(f"{name}:{node.lineno} inline system prompt")
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if any(
                    isinstance(t, ast.Name)
                    and t.id.lower()
                    in {
                        "prompt",
                        "system_prompt",
                        "system_instruction",
                        "prompt_template",
                        "system",
                    }
                    for t in targets
                ):
                    if isinstance(node.value, (ast.Constant, ast.JoinedStr)) and isinstance(
                        getattr(node.value, "value", ""), str
                    ):
                        violations.append(f"{name}:{node.lineno} inline prompt assignment")
    if violations:
        raise ValueError("Prompt-location violations: " + ", ".join(violations))
    import yaml

    config = yaml.safe_load((root / "agent/config.yaml").read_text(encoding="utf-8"))
    roles = {r for p in config["profiles"].values() for r in p.get("models", {})}
    for role in roles:
        if not (root / "agent/prompts" / (role + ".md")).is_file():
            raise ValueError("Missing configured role prompt: " + role)


def document_blocks(root, name):
    if name.endswith(".pdf"):
        from pypdf import PdfReader

        return {
            f"page-{i + 1}": page.extract_text() or ""
            for i, page in enumerate(PdfReader(root / name).pages)
        }
    text = (root / name).read_text(encoding="utf-8")
    chunks = re.split(r"(?m)^(## .+)$", text)
    result = {"preamble": chunks[0]}
    result.update({chunks[i]: chunks[i + 1] for i in range(1, len(chunks), 2)})
    return result


def numeric_tokens(text):
    # Link destinations, hashes and file/model identifiers are not measured claims.
    text = re.sub(r"https?://[^\s)]+", "", text)
    return NUMBER.findall(text)


def numeric_provenance(root):
    ledger_path = root / "evals/results/numeric-claim-provenance.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    expected_documents = {"README.md", "output/pdf/GigBid_RnD_Report.pdf"}
    if set(ledger["documents"]) != expected_documents:
        raise ValueError("Numeric provenance must cover README and engineering report")
    for name, evidence in ledger["documents"].items():
        blocks = {k: v for k, v in document_blocks(root, name).items() if numeric_tokens(v)}
        if set(blocks) != set(evidence):
            raise ValueError("Numeric provenance coverage changed: " + name)
        for key, text in blocks.items():
            item = evidence[key]
            if item["text_sha256"] != sha(text.encode()) or item[
                "numeric_tokens"
            ] != numeric_tokens(text):
                raise ValueError(f"Numeric claims changed without reviewed evidence: {name} {key}")
            if not item.get("sources") or not item.get("scope"):
                raise ValueError("Numeric claims need explicit evidence and scope")
            for source in item["sources"]:
                relative = source["path"]
                path = (root / relative).resolve()
                if not relative.startswith("evals/results/") or not path.is_relative_to(
                    root.resolve() / "evals/results"
                ):
                    raise ValueError("Numeric evidence must stay under evals/results")
                if not path.is_file() or evidence_sha(path) != source["sha256"]:
                    raise ValueError("Numeric evidence missing or changed: " + relative)
                if path.suffix == ".json":
                    json.loads(path.read_text(encoding="utf-8-sig"))
    return sum(len(v) for v in ledger["documents"].values())


def check(root=ROOT):
    names = files(root)
    forbidden = [n for n in names if Path(n).name == ".env" or Path(n).suffix in {".pem", ".key"}]
    if forbidden:
        raise ValueError("Private credential file tracked: " + ", ".join(forbidden))
    protected_tree(root)
    prompt_locations(root, names)
    blocks = numeric_provenance(root)
    return {
        "passed": True,
        "gigsim_unchanged": True,
        "prompt_locations": True,
        "numeric_evidence_blocks": blocks,
        "limits": "Evidence coverage/hashes require reviewed bindings; "
        "not semantic/statistical proof. "
        "Secret patterns/history checked separately with Gitleaks.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = check()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Assignment policy failed: {error}\n")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
