"""Financial entry points must reject missing or changed reviewed inputs."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import project_runtime
from study import CONTRACT, load_reviewed_tape, scenario_grid


class PublicInputsTests(unittest.TestCase):
    def test_missing_inputs_explain_private_prerequisite(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, 'not distributed'):
                load_reviewed_tape(folder)

    def test_changed_snapshot_rejected_before_parquet_read(self):
        with tempfile.TemporaryDirectory() as folder:
            for name in CONTRACT['input_sha256']:
                (Path(folder) / name).write_bytes(b'not reviewed data')
            with patch('study.pd.read_parquet') as reader:
                with self.assertRaisesRegex(ValueError, 'Changed evidence'):
                    load_reviewed_tape(folder)
                reader.assert_not_called()

    def test_unprespecified_scenario_rejected(self):
        with self.assertRaisesRegex(ValueError, 'prespecified'):
            scenario_grid({'id': 'selected_after_the_test'})
