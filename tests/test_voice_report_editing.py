"""Pure voice-report checks; no audio model, network, or database is used."""
import unittest
import os
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch

from voice_reports import AdvancedReportInput, parse_report_nlp, speech_readiness, speech_model_source


class VoiceReportEditingTests(unittest.TestCase):
    def test_offline_model_readiness_does_not_claim_decoding_success(self):
        with TemporaryDirectory() as folder, patch.dict(os.environ, {"KIARAD_SPEECH_MODEL_PATH": folder}), patch('voice_reports.find_spec', return_value=object()), patch('voice_reports.whisper_model', None), patch('voice_reports._whisper_tried', False):
            self.assertEqual(speech_model_source(), folder)
            self.assertEqual(speech_readiness()['state'], 'local_files_missing')
            for name in ('model.bin', 'config.json', 'tokenizer.json'):
                Path(folder, name).touch()
            self.assertEqual(speech_readiness()['state'], 'local_files_present')
            self.assertFalse(speech_readiness()['automatic_download'])

    def test_parsed_text_remains_available_for_user_editing(self):
        result = parse_report_nlp("امروز داروخانه بهار را ویزیت کردم و کاتالوگ خواست")
        self.assertEqual(result["raw_text"], "امروز داروخانه بهار را ویزیت کردم و کاتالوگ خواست")
        self.assertIn("داروخانه بهار", result["customer_name"])
        self.assertTrue(result["followup_task"])

    def test_selected_customer_id_is_accepted_in_final_payload(self):
        payload = AdvancedReportInput(
            customer_id=42,
            customer_name="نام اصلاح‌شده",
            summary="ویزیت انجام شد",
            notes="متن ویرایش‌شده",
        )
        self.assertEqual(payload.customer_id, 42)
        self.assertEqual(payload.notes, "متن ویرایش‌شده")

    def test_rejected_public_sample_is_not_reported_ready(self):
        with TemporaryDirectory() as folder, patch.dict(os.environ, {"KIARAD_SPEECH_MODEL_PATH": folder}), patch('voice_reports.find_spec', return_value=object()), patch('voice_reports.whisper_model', None), patch('voice_reports._whisper_tried', False), patch('voice_reports._speech_conversion_verified', True):
            for name in ('model.bin', 'config.json', 'tokenizer.json'):
                Path(folder, name).touch()
            Path(folder, 'verification.json').write_text('{"public_sample_check_passed":false,"exclude_from_auto_selection":true}', encoding='utf-8')
            status = speech_readiness()
            self.assertEqual(status['state'], 'quality_rejected')
            self.assertFalse(status['conversion_verified'])

    def test_default_source_skips_rejected_local_model(self):
        with TemporaryDirectory() as folder, patch.dict(os.environ, {"KIARAD_SPEECH_MODEL_PATH": ""}), patch('voice_reports.__file__', str(Path(folder) / 'voice_reports.py')):
            tiny = Path(folder) / 'data' / 'speech-models' / 'faster-whisper-tiny'
            tiny.mkdir(parents=True)
            for name in ('model.bin', 'config.json', 'tokenizer.json'):
                (tiny / name).touch()
            self.assertEqual(speech_model_source(), str(tiny))
            (tiny / 'verification.json').write_text('{"public_sample_check_passed":false,"exclude_from_auto_selection":true}', encoding='utf-8')
            self.assertEqual(speech_model_source(), 'small')

    def test_explicit_active_model_is_not_blocked_by_one_public_sample(self):
        with TemporaryDirectory() as folder, patch.dict(os.environ, {"KIARAD_SPEECH_MODEL_PATH": ""}), patch('voice_reports.__file__', str(Path(folder) / 'voice_reports.py')):
            root = Path(folder) / 'data' / 'speech-models'
            model = root / 'faster-whisper-small'
            model.mkdir(parents=True)
            for name in ('model.bin', 'config.json', 'tokenizer.json'):
                (model / name).touch()
            (model / 'verification.json').write_text('{"public_sample_check_passed":false}', encoding='utf-8')
            (root / 'active-model.json').write_text('{"directory":"faster-whisper-small"}', encoding='utf-8')
            self.assertEqual(speech_model_source(), str(model.resolve()))

    def test_active_model_pointer_cannot_escape_model_root(self):
        with TemporaryDirectory() as folder, patch.dict(os.environ, {"KIARAD_SPEECH_MODEL_PATH": ""}), patch('voice_reports.__file__', str(Path(folder) / 'voice_reports.py')):
            root = Path(folder) / 'data' / 'speech-models'
            root.mkdir(parents=True)
            outside = root.parent / 'outside'
            outside.mkdir()
            for name in ('model.bin', 'config.json', 'tokenizer.json'):
                (outside / name).touch()
            (root / 'active-model.json').write_text('{"directory":"../outside"}', encoding='utf-8')
            self.assertEqual(speech_model_source(), 'small')


if __name__ == "__main__":
    unittest.main()
