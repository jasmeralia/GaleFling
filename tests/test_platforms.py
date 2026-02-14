"""Tests for platform implementations."""

from src.platforms.bluesky import detect_urls
from src.utils.constants import BLUESKY_SPECS, TWITTER_SPECS


class TestDetectUrls:
    def test_no_urls(self):
        assert detect_urls('Just a normal post') == []

    def test_single_url(self):
        facets = detect_urls('Check out https://example.com today')
        assert len(facets) == 1
        assert facets[0]['features'][0]['uri'] == 'https://example.com'

    def test_multiple_urls(self):
        text = 'Visit https://one.com and http://two.com'
        facets = detect_urls(text)
        assert len(facets) == 2

    def test_url_with_path(self):
        text = 'Test https://rin-city.com/envira/orinnixi/'
        facets = detect_urls(text)
        assert facets[0]['features'][0]['uri'] == 'https://rin-city.com/envira/orinnixi/'
        start = text.index('https://rin-city.com/envira/orinnixi/')
        end = start + len('https://rin-city.com/envira/orinnixi/')
        assert facets[0]['index']['byteStart'] == start
        assert facets[0]['index']['byteEnd'] == end

    def test_byte_offsets_ascii(self):
        text = 'Go to https://example.com now'
        facets = detect_urls(text)
        url = 'https://example.com'
        start = text.index(url)
        end = start + len(url)
        assert facets[0]['index']['byteStart'] == start
        assert facets[0]['index']['byteEnd'] == end

    def test_byte_offsets_unicode(self):
        # Emoji before URL shifts byte offset
        text = '\U0001f525 https://example.com'
        facets = detect_urls(text)
        # Fire emoji is 4 bytes in UTF-8, plus space = 5 bytes
        assert facets[0]['index']['byteStart'] == 5
        url = 'https://example.com'
        assert facets[0]['index']['byteEnd'] == 5 + len(url.encode('utf-8'))

    def test_facet_structure(self):
        facets = detect_urls('https://example.com')
        f = facets[0]
        assert 'index' in f
        assert 'byteStart' in f['index']
        assert 'byteEnd' in f['index']
        assert f['features'][0]['$type'] == 'app.bsky.richtext.facet#link'


class TestPlatformSpecs:
    def test_twitter_specs(self):
        assert TWITTER_SPECS.max_text_length == 280
        assert TWITTER_SPECS.max_file_size_mb == 5.0
        assert not TWITTER_SPECS.requires_facets

    def test_bluesky_specs(self):
        assert BLUESKY_SPECS.max_text_length == 300
        assert BLUESKY_SPECS.max_file_size_mb == 1.0
        assert BLUESKY_SPECS.requires_facets
