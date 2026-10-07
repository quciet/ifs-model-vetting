import pathlib
import tempfile
import unittest
from unittest.mock import patch
import app


class StorageTests(unittest.TestCase):
    def test_frozen_storage_is_separate_and_has_no_personal_default(self):
        with tempfile.TemporaryDirectory() as folder:
            data=pathlib.Path(folder)/'userdata'
            with patch.object(app,'DATA_ROOT',data),patch.object(app,'SETTINGS',data/'settings.json'),patch.object(app,'FROZEN',True):
                app.initialize_storage()
                self.assertTrue(data.is_dir())
                self.assertIsNone(app.saved_installation())
                self.assertEqual(app.empty_installation()['runs'],[])

    def test_legacy_copy_preserves_existing_user_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            source=pathlib.Path(folder)/'source';source.mkdir()
            data=pathlib.Path(folder)/'data';data.mkdir()
            (source/'settings.json').write_text('{"installation":"old"}')
            (data/'settings.json').write_text('{"installation":"new"}')
            (source/'results'/'existing').mkdir(parents=True)
            (source/'results'/'existing'/'report.json').write_text('{}')
            with patch.object(app,'ROOT',source),patch.object(app,'DATA_ROOT',data),patch.object(app,'SETTINGS',data/'settings.json'),patch.object(app,'FROZEN',False):
                app.initialize_storage()
                self.assertEqual(str(app.saved_installation()),'new')
                self.assertTrue((data/'results'/'existing'/'report.json').exists())
                self.assertTrue((source/'results'/'existing'/'report.json').exists())
