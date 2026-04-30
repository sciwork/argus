from argus.kktix.scraper import (
    EventDetails,
    _parse_capacity,
    _parse_start_at,
    parse_event_html,
)


# Realistic HTML snippets based on actual KKTIX page structure
SAMPLE_HTML = """
<html>
<script type="application/ld+json">
{"@context":"http://schema.org","@type":"Event","name":"Test Event",
 "startDate":"2026-04-25T09:00:00.000+08:00","endDate":"2026-04-25T18:00:00.000+08:00"}
</script>
<span class="info-desc">
  <i class="fa fa-calendar"></i>
  <span class="timezoneSuffix">2026/04/25(周六) 09:00(+0800)</span>
   ~ <span class="timezoneSuffix">18:00(+0800)</span>
</span>
<span class="info-count">
  <i class="fa fa-male"></i>0 / 30</span>
</html>
"""

HTML_NO_JSONLD = """
<span class="info-count"><i class="fa fa-male"></i>5 / 50</span>
"""

HTML_NO_CAPACITY = """
<script type="application/ld+json">
{"startDate":"2026-04-25T09:00:00.000+08:00"}
</script>
"""


def test_parse_event_html_full():
    result = parse_event_html(SAMPLE_HTML)
    assert result == EventDetails(start_at="2026-04-25T01:00:00", capacity=30)


def test_parse_start_at_from_jsonld():
    result = _parse_start_at(SAMPLE_HTML)
    assert result == "2026-04-25T01:00:00"


def test_parse_start_at_converts_to_utc():
    # +08:00 → UTC is 8 hours behind, so 09:00+08:00 → 01:00 UTC
    html = '{"startDate":"2026-04-25T09:00:00.000+08:00"}'
    assert _parse_start_at(html) == "2026-04-25T01:00:00"


def test_parse_start_at_missing_returns_none():
    assert _parse_start_at("<html>no json-ld here</html>") is None


def test_parse_capacity_slash_format():
    assert _parse_capacity('<i class="fa fa-male"></i>0 / 30') == 30


def test_parse_capacity_zero_after_slash():
    assert _parse_capacity('<i class="fa fa-male"></i>0 / 0') == 0


def test_parse_capacity_no_pattern_returns_none():
    assert _parse_capacity("no capacity info") is None


def test_parse_event_html_missing_jsonld():
    result = parse_event_html(HTML_NO_JSONLD)
    assert result.start_at is None
    assert result.capacity == 50


def test_parse_event_html_missing_capacity():
    result = parse_event_html(HTML_NO_CAPACITY)
    assert result.start_at == "2026-04-25T01:00:00"
    assert result.capacity is None
