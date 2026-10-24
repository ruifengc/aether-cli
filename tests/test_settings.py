from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aether_cli.settings import load_settings


class SettingsTests(unittest.TestCase):
    def test_missing_environment_credentials_never_fall_back_to_home_files(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            unrelated = home / ".hermes"
            unrelated.mkdir()
            (unrelated / ".env").write_text(
                "TOKENHUB_API_KEY=unrelated-credential\n"
                "DEEPSEEK_API_KEY=unrelated-credential\n")
            with (patch.dict(os.environ, {}, clear=True),
                  patch.object(Path, "home", return_value=home),
                  patch.object(Path, "read_text", side_effect=AssertionError("unexpected file read")),
                  patch("builtins.open", side_effect=AssertionError("unexpected file read"))):
                for provider in ("tencent", "deepseek"):
                    with self.subTest(provider=provider), self.assertRaisesRegex(
                            ValueError, f"no credential configured for {provider}"):
                        load_settings(provider=provider)

    def test_environment_settings_need_no_files_and_do_not_modify_environment(self):
        for provider, environment, expected in (
                ("tencent", {"TOKENHUB_API_KEY": "test-credential",
                             "TOKENHUB_BASE_URL": "https://model.invalid/v1/",
                             "LLM_PRO_MODEL": "configured-model"},
                 ("https://model.invalid/v1", "configured-model")),
                ("deepseek", {"DEEPSEEK_API_KEY": "test-credential",
                              "DEEPSEEK_MODEL": "configured-model"},
                 ("https://api.deepseek.com/v1", "configured-model"))):
            with (self.subTest(provider=provider), patch.dict(os.environ, environment, clear=True),
                  patch.object(Path, "home", side_effect=AssertionError("unexpected home lookup")),
                  patch("builtins.open", side_effect=AssertionError("unexpected file read"))):
                before = dict(os.environ)
                settings = load_settings(provider=provider)
                self.assertEqual(settings.api_key, "test-credential")
                self.assertEqual((settings.base_url, settings.model), expected)
                self.assertEqual(settings.reasoning, "high")
                self.assertEqual(dict(os.environ), before)

    def test_explicit_options_override_environment_defaults(self):
        environment = {"LLM_PROVIDER": "deepseek", "TOKENHUB_API_KEY": "test-credential",
                       "LLM_PRO_MODEL": "environment-model", "LLM_PRO_REASONING_EFFORT": "low"}
        with patch.dict(os.environ, environment, clear=True):
            settings = load_settings(provider="tencent", model="explicit-model", reasoning="high")
        self.assertEqual(settings.provider, "tencent")
        self.assertEqual(settings.model, "explicit-model")
        self.assertEqual(settings.reasoning, "high")
