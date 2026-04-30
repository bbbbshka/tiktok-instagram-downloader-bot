"""Tests for translation strings."""

from i18n import _STRINGS, msg


class TestTranslations:
    def test_every_key_bilingual(self):
        for key, langs in _STRINGS.items():
            assert "ru" in langs, f"{key} missing ru"
            assert "en" in langs, f"{key} missing en"

    def test_russian_default(self):
        text = msg("hello")
        assert "Привет" in text

    def test_english(self):
        text = msg("hello", "en")
        assert "Hi" in text

    def test_bad_key(self):
        assert msg("nonexistent_key_xyz") == "nonexistent_key_xyz"

    def test_unknown_lang_fallback(self):
        text = msg("hello", "de")
        assert "Привет" in text

    def test_flood_msg(self):
        assert msg("err_flood", "ru") != ""
        assert msg("err_flood", "en") != ""
