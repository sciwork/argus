from pathlib import Path

from argus.kktix import scraper


def test_parse_event_html_extracts_utc_start_time_and_capacity():
    """Parse a saved Sciwork KKTIX page fragment into stored event metadata."""
    fixture_path = Path(__file__).with_name("scisprint-202608-taipei.html")
    html = fixture_path.read_text()

    details = scraper.parse_event_html(html)

    assert details == scraper.EventDetails(start_at="2026-08-15T02:00:00", capacity=20)
