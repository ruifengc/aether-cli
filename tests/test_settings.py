from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aether_cli.settings import load_settings


class SettingsTests(unittest.TestCase):
    def test_environment_file_is_parsed_as_data_and_keys_are_not_exported(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.env"
            path.write_text("DEEPSEEK_API_KEY='test-credential'\n"
                            "DEEPSEEK_MODEL='configured-model'\nUNRELATED_SECRET='do-not-import'\n")
            with patch.dict(os.environ, {}, clear=True):
                settings = load_settings(env_file=path, provider="deepseek")
                self.assertEqual(settings.model, "configured-model")
                self.assertEqual(settings.api_key, "test-credential")
                self.assertEqual(settings.reasoning, "high")
                self.assertNotIn("DEEPSEEK_API_KEY", os.environ)
                self.assertNotIn("UNRELATED_SECRET", os.environ)
