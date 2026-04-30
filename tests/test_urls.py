"""Tests for URL detection logic."""

from handlers.links import detect_url


class TestTikTok:
    def test_regular(self):
        assert detect_url("https://www.tiktok.com/@user/video/123")

    def test_short_vm(self):
        assert detect_url("https://vm.tiktok.com/ZMh1abc/")

    def test_short_vt(self):
        assert detect_url("https://vt.tiktok.com/ZMh1abc/")

    def test_mobile(self):
        assert detect_url("https://m.tiktok.com/@user/video/123")

    def test_inside_text(self):
        url = detect_url("look at this https://www.tiktok.com/@u/video/1 lol")
        assert url == "https://www.tiktok.com/@u/video/1"


class TestInstagram:
    def test_reel(self):
        assert detect_url("https://www.instagram.com/reel/abc123/")

    def test_post(self):
        assert detect_url("https://www.instagram.com/p/abc123/")

    def test_tv(self):
        assert detect_url("https://www.instagram.com/tv/abc123/")

    def test_stories(self):
        assert detect_url("https://www.instagram.com/stories/user/123/")

    def test_no_www(self):
        assert detect_url("https://instagram.com/reel/abc123/")


class TestNegative:
    def test_youtube(self):
        assert detect_url("https://youtube.com/watch?v=xyz") is None

    def test_plain_text(self):
        assert detect_url("just some random text") is None

    def test_empty(self):
        assert detect_url("") is None

    def test_half_tiktok(self):
        assert detect_url("tiktok.com") is None
