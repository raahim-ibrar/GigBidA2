import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile


def read_rows(path, schema):
    raw = Path(path).read_bytes()
    rows = []
    for line_number, line in enumerate(raw.decode("utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(schema.model_validate_json(line))
        except ValueError as error:
            raise ValueError(f"{path}: invalid record at line {line_number}: {error}") from error
    if not rows or len({row.id for row in rows}) != len(rows):
        raise ValueError(f"{path}: nonempty records with unique job IDs are required")
    return rows, {
        "name": Path(path).name,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "rows": len(rows),
    }


def align(gold, predictions):
    predicted = {row.id: row for row in predictions}
    if {row.id for row in gold} != set(predicted):
        raise ValueError(
            "Gold and prediction job IDs must match exactly; missing jobs cannot be dropped"
        )
    return [(row, predicted[row.id]) for row in gold]


def write_result(path, *, metric, data_origin, inputs, results):
    if Path(path).resolve() in {Path(item).resolve() for item in inputs}:
        raise ValueError("Result output cannot overwrite an input")
    output = {
        "schema_version": 1,
        "metric": metric,
        "data_origin": data_origin,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "inputs": list(inputs.values()),
        "results": results,
    }
    target = Path(path)
    payload = json.dumps(output, indent=2, sort_keys=True, allow_nan=False) + "\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=target.parent, prefix=".eval-", suffix=".tmp", delete=False
    ) as handle:
        temporary = Path(handle.name)
        handle.write(payload)
    try:
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return output
