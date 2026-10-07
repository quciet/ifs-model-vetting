import pathlib
import tempfile
import unittest
from app import installation_layout


class InstallationTests(unittest.TestCase):
    def test_fixed_layout_recursive_runs_and_legacy_filter(self):
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder).resolve()
            (root/'DATA').mkdir(); (root/'RUNFILES'/'nested').mkdir(parents=True)
            for name in ['Base.run.db','nested/Scenario.run','nested/Upper.RUN.DB']:
                (root/'RUNFILES'/name).write_bytes(b'SQLite format 3\x00')
            (root/'RUNFILES'/'Old.run').write_bytes(b'legacy format')
            (root/'RUNFILES'/'metadata.db').write_bytes(b'SQLite format 3\x00')
            (root/'DATA'/'NotAnOutput.run.db').write_bytes(b'SQLite format 3\x00')
            result=installation_layout(root)
            self.assertEqual(len(result['runs']),3)
            self.assertEqual(len(result['skipped']),1)
            self.assertEqual(result['data'],str(root/'DATA'))
            self.assertEqual(result['labels'][str(root/'RUNFILES'/'nested'/'Scenario.run')],str(pathlib.Path('nested/Scenario.run')))

    def test_runfiles_folder_is_not_an_installation(self):
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder); (root/'RUNFILES').mkdir()
            with self.assertRaisesRegex(ValueError,'installation root'):
                installation_layout(root/'RUNFILES')

    def test_missing_data_is_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder);(root/'RUNFILES').mkdir()
            with self.assertRaisesRegex(ValueError,'DATA'):
                installation_layout(root)
