"""آزمون آفلاین واقعی مدل روی نمونهٔ عمومی فارسی؛ بدون ثبت گزارش یا هلو.

فایل نمونه و فرادادهٔ مجاز آن باید از قبل دریافت شده باشند.
متن مرجع یا متن تشخیص‌داده‌شده در گزارش چاپ یا ذخیره نمی‌شود.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data/speech-samples/google-fleurs-fa-ir-test-sample.wav"


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized_words(value):
    value = unicodedata.normalize("NFKC", value).translate(
        str.maketrans({"ي": "ی", "ك": "ک", "\u200c": " "})
    )
    return "".join(char if char.isalnum() or char.isspace() else " " for char in value).split()


def edit_distance(reference, hypothesis):
    row = list(range(len(hypothesis) + 1))
    for i, first in enumerate(reference, 1):
        following = [i]
        for j, second in enumerate(hypothesis, 1):
            following.append(min(following[-1] + 1, row[j] + 1, row[j - 1] + (first != second)))
        row = following
    return row[-1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-directory", required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--model-revision", required=True)
    options = parser.parse_args()
    model_path = Path(options.model_directory).resolve()
    model_path.relative_to(ROOT)
    sys.path.insert(0, str(ROOT))
    os.environ["KIARAD_SPEECH_MODEL_PATH"] = str(model_path)
    report = {
        "checked_at": datetime.now().astimezone().isoformat(),
        "sample_kind": "public_persian_dataset_not_user_or_phone_microphone",
        "model_id": options.model_id,
        "model_revision": options.model_revision,
        "phone_microphone_tested": False,
        "user_voice_tested": False,
        "public_sample_word_error_rate_limit": 0.35,
        "quality_scope": "one_public_sample_not_general_accuracy",
        "conversion_completed": False,
        "public_sample_check_passed": False,
    }
    try:
        previous = json.loads((model_path / "verification.json").read_text(encoding="utf-8"))
        report["exclude_from_auto_selection"] = previous.get("exclude_from_auto_selection") is True
    except (OSError, ValueError, TypeError):
        report["exclude_from_auto_selection"] = False
    try:
        metadata = json.loads(SAMPLE.with_suffix(".json").read_text(encoding="utf-8"))
        assert metadata["sample_kind"] == report["sample_kind"]
        assert file_hash(SAMPLE) == metadata["sample_sha256"]
        report.update(
            dataset=metadata["dataset"],
            dataset_revision=metadata["dataset_revision"],
            dataset_source=metadata["source"],
            dataset_license=metadata["license"],
            sample_sha256=metadata["sample_sha256"],
            sample_duration_seconds=metadata["duration_seconds"],
            model_files={
                name: {"sha256": file_hash(model_path / name), "bytes": (model_path / name).stat().st_size}
                for name in ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt")
            },
        )
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env", override=False)
        import voice_reports

        started = time.perf_counter()
        with (
            patch("requests.sessions.Session.request", side_effect=AssertionError("External HTTP disabled")),
            patch("httpx.HTTPTransport.handle_request", side_effect=AssertionError("External HTTP disabled")),
        ):
            result = voice_reports._transcribe_bytes(SAMPLE.read_bytes())
        seconds = time.perf_counter() - started
        reference = normalized_words(metadata["reference_transcription"])
        hypothesis = normalized_words(result["raw_text"])
        edits = edit_distance(reference, hypothesis)
        error_rate = edits / max(1, len(reference))
        report.update(
            conversion_completed=True,
            processing_seconds=round(seconds, 3),
            reference_word_count=len(reference),
            recognized_word_count=len(hypothesis),
            word_edits=edits,
            normalized_word_error_rate=round(error_rate, 4),
            public_sample_check_passed=error_rate <= report["public_sample_word_error_rate_limit"],
        )
    except Exception as error:
        report["error_type"] = type(error).__name__
    folder = ROOT / "audit-2026-10-18"
    folder.mkdir(exist_ok=True)
    destination = folder / (model_path.name + "-real-transcription.json")
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (model_path / "verification.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        "MODEL", options.model_id,
        "CONVERSION", report["conversion_completed"],
        "PUBLIC_SAMPLE_CHECK", report["public_sample_check_passed"],
        "SECONDS", report.get("processing_seconds"),
        "NORMALIZED_WER", report.get("normalized_word_error_rate"),
        flush=True,
    )
    print("REPORT", destination.relative_to(ROOT).as_posix(), flush=True)
    return 0 if report["public_sample_check_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
