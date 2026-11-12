"""Download the approved, pinned Kaggle archive and verify before preprocessing."""

import hashlib
import urllib.request
from pathlib import Path

from scripts.prepare_student_data import prepare

URL = (
    "https://www.kaggle.com/api/v1/datasets/download/asaniczka/"
    "upwork-job-postings-dataset-2024-50k-records?datasetVersionNumber=1"
)
SHA256 = "3f40f06c267f6429e6c9fdd9a81c0c9bb3a3c9eb85edadb1d6638394e9ce5b35"


def main():
    path = Path("data/processed/raw/upwork-2024-v1.zip")
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        temporary = path.with_suffix(".download")
        request = urllib.request.Request(URL, headers={"User-Agent": "GigBid-coursework/1.0"})
        with (
            urllib.request.urlopen(request, timeout=60) as response,
            temporary.open("wb") as output,
        ):
            count = 0
            while block := response.read(1024 * 1024):
                count += len(block)
                if count > 100 * 1024 * 1024:
                    raise ValueError("Archive exceeded the expected download bound")
                output.write(block)
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != SHA256:
            raise ValueError("Archive differs from pinned source; inspect before accepting")
        temporary.replace(path)
    if hashlib.sha256(path.read_bytes()).hexdigest() != SHA256:
        raise ValueError("Existing source archive does not match the pinned SHA256")
    result = prepare(path, "data/processed/student_jobs.json", 200)
    print(f"Prepared {sum(result['selected_by_persona'].values())} hybrid simulator jobs.")


if __name__ == "__main__":
    main()
