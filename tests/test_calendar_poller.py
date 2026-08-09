import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from hawk_dove.calendar import (
    SpeakerEvent,
    filter_due_events,
    is_actionable_status,
    speaker_event_from_row,
)
from hawk_dove.discovery import DiscoveredDocument
from hawk_dove.url_resolve import (
    is_published_speech_url,
    is_rejected_event_url,
    resolve_event_url,
)
from poll_speaker_schedule import process_event, run_poll


def _row(**overrides):
    base = {
        "id": 1,
        "external_id": "fed-speech-1",
        "speaker_id": 10,
        "speaker_name": "Jerome H. Powell",
        "title": "Economic Outlook",
        "event_type": "speech",
        "scheduled_start": "2025-06-18T15:00:00+00:00",
        "scheduled_end": None,
        "location": "Washington",
        "description": None,
        "url": "https://www.federalreserve.gov/newsevents/speech/powell20250618a.htm",
        "source": "Federal Reserve Board",
        "status": "scheduled",
        "speech_id": None,
        "raw_payload": None,
    }
    base.update(overrides)
    return base


class CalendarFilterTests(unittest.TestCase):
    def test_speaker_event_from_row(self):
        event = speaker_event_from_row(_row())
        self.assertEqual(event.external_id, "fed-speech-1")
        self.assertEqual(event.scheduled_date.isoformat(), "2025-06-18")
        self.assertTrue(is_actionable_status(event.status))

    def test_filters_cancelled_and_wrong_type(self):
        now = datetime(2025, 6, 18, 16, 0, tzinfo=timezone.utc)
        rows = [
            _row(external_id="ok", status="scheduled"),
            _row(id=2, external_id="cancelled", status="cancelled"),
            _row(id=3, external_id="cpi", event_type="data_release", url=None),
            _row(
                id=4,
                external_id="too_old",
                scheduled_start=(now - timedelta(hours=20)).isoformat(),
            ),
        ]
        due = filter_due_events(rows, now=now, lookback=timedelta(hours=6), lookahead=timedelta(hours=2))
        self.assertEqual([event.external_id for event in due], ["ok"])

    def test_includes_completed_status(self):
        now = datetime(2025, 6, 18, 16, 0, tzinfo=timezone.utc)
        due = filter_due_events(
            [_row(status="completed")],
            now=now,
            lookback=timedelta(hours=6),
            lookahead=timedelta(hours=2),
        )
        self.assertEqual(len(due), 1)


class UrlQualityTests(unittest.TestCase):
    def test_accepts_board_speech_urls(self):
        url = "https://www.federalreserve.gov/newsevents/speech/powell20250618a.htm"
        self.assertTrue(is_published_speech_url(url))
        self.assertFalse(is_rejected_event_url(url))

    def test_rejects_livestream_and_registration_hosts(self):
        bad = [
            "https://zoom.us/meeting/register/HwGA9SMaQu-vrt_YA2ZJaw",
            "https://onemetlife.webex.com/onemetlife/j.php?MTID=mbbedc1dd8ba1351aa71d43af74b7592a",
            "https://www.youtube.com/watch?v=OFTWSRRkkCU",
            "https://www.federalreserve.gov/live-broadcast.htm",
            "https://financialservices.house.gov",
            "https://www.banking.senate.gov",
        ]
        for url in bad:
            self.assertTrue(is_rejected_event_url(url), url)
            self.assertFalse(is_published_speech_url(url), url)

    def test_rejects_conference_pages_as_published_speech(self):
        url = "https://www.federalreserve.gov/conferences/next-gen-financial-inclusion.htm"
        self.assertFalse(is_published_speech_url(url))


class UrlResolveTests(unittest.TestCase):
    def test_prefers_event_url(self):
        event = speaker_event_from_row(_row())
        url = resolve_event_url(event, discovered=[])
        self.assertIn("powell20250618a", url)

    def test_junk_calendar_url_falls_through_to_discovery(self):
        event = speaker_event_from_row(
            _row(url="https://zoom.us/meeting/register/abc123")
        )
        discovered = [
            DiscoveredDocument(
                url="https://www.federalreserve.gov/newsevents/speech/powell20250618a.htm",
                source_family="board",
                title="Chair Powell Speech",
                date_hint=event.scheduled_date,
            )
        ]
        url = resolve_event_url(event, discovered=discovered)
        self.assertIn("powell20250618a", url)

    def test_junk_calendar_url_without_discovery_returns_none(self):
        event = speaker_event_from_row(
            _row(url="https://www.youtube.com/watch?v=OFTWSRRkkCU")
        )
        self.assertIsNone(resolve_event_url(event, discovered=[]))

    def test_unnamed_press_conference_does_not_match_archival_speech(self):
        event = speaker_event_from_row(
            _row(
                speaker_name=None,
                title="FOMC Press Conference",
                event_type="press_conference",
                url="https://www.federalreserve.gov/live-broadcast.htm",
                scheduled_start="2026-07-29T18:30:00+00:00",
            )
        )
        discovered = [
            DiscoveredDocument(
                url="https://www.newyorkfed.org/newsevents/speeches/1996/ep960125",
                source_family="nyfed",
                title="Archival remarks",
                date_hint=None,
            ),
            DiscoveredDocument(
                url="https://www.federalreserve.gov/newsevents/speech/powell20250618a.htm",
                source_family="board",
                title="Chair Powell Speech",
                date_hint=event.scheduled_date,
            ),
        ]
        self.assertIsNone(resolve_event_url(event, discovered=discovered))

    def test_unnamed_press_conference_matches_dated_pc_transcript(self):
        event = speaker_event_from_row(
            _row(
                speaker_name=None,
                title="FOMC Press Conference",
                event_type="press_conference",
                url=None,
                scheduled_start="2026-07-29T18:30:00+00:00",
            )
        )
        discovered = [
            DiscoveredDocument(
                url="https://www.federalreserve.gov/newsevents/pressconferences/fomcpresconf20260729.htm",
                source_family="board",
                title="FOMC Press Conference",
                date_hint=event.scheduled_date,
            )
        ]
        url = resolve_event_url(event, discovered=discovered)
        self.assertIn("pressconferences", url)

    def test_discovery_fallback_matches_speaker_and_date(self):
        event = speaker_event_from_row(_row(url=None))
        discovered = [
            DiscoveredDocument(
                url="https://www.federalreserve.gov/newsevents/speech/powell20250618a.htm",
                source_family="board",
                title="Chair Powell Speech",
                date_hint=event.scheduled_date,
            ),
            DiscoveredDocument(
                url="https://www.federalreserve.gov/newsevents/speech/waller20250618a.htm",
                source_family="board",
                title="Governor Waller Speech",
                date_hint=event.scheduled_date,
            ),
        ]
        url = resolve_event_url(event, discovered=discovered)
        self.assertIn("powell", url)


class PollerTests(unittest.TestCase):
    def test_skips_already_scored(self):
        event = speaker_event_from_row(_row())
        corpus = MagicMock()
        corpus.get_calendar_ingest_run.return_value = {
            "status": "scored",
            "document_key": "doc_1",
            "score_key": "score_1",
        }
        pipeline = MagicMock()
        result = process_event(event, pipeline=pipeline, corpus_db=corpus, dry_run=False)
        self.assertEqual(result["status"], "skipped_already_scored")
        pipeline.score_document.assert_not_called()

    def test_dry_run_does_not_score(self):
        event = speaker_event_from_row(_row())
        corpus = MagicMock()
        corpus.get_calendar_ingest_run.return_value = None
        corpus.source_document_exists.return_value = False
        pipeline = MagicMock()
        result = process_event(event, pipeline=pipeline, corpus_db=corpus, dry_run=True)
        self.assertEqual(result["status"], "dry_run_would_score")
        pipeline.score_document.assert_not_called()

    def test_pending_url_when_unresolved(self):
        event = speaker_event_from_row(
            _row(url="https://zoom.us/meeting/register/abc123")
        )
        corpus = MagicMock()
        corpus.get_calendar_ingest_run.return_value = None
        pipeline = MagicMock()
        with patch("poll_speaker_schedule.resolve_event_url", return_value=None):
            result = process_event(event, pipeline=pipeline, corpus_db=corpus, dry_run=False)
        self.assertEqual(result["status"], "pending_url")
        self.assertEqual(result["error"], "no_url_resolved")
        self.assertEqual(result["rejected_calendar_url"], event.url)
        pipeline.score_document.assert_not_called()
        corpus.upsert_calendar_ingest_run.assert_called_once()
        payload = corpus.upsert_calendar_ingest_run.call_args.args[0]
        self.assertEqual(payload["status"], "pending_url")

    def test_run_poll_with_injected_events_filters_scored(self):
        now = datetime(2025, 6, 18, 16, 0, tzinfo=timezone.utc)
        events = [
            speaker_event_from_row(_row(external_id="a")),
            speaker_event_from_row(_row(id=2, external_id="b", url=None)),
        ]
        corpus = MagicMock()
        corpus.list_scored_calendar_external_ids.return_value = {"a"}
        corpus.get_calendar_ingest_run.return_value = None
        corpus.source_document_exists.return_value = False

        with patch("poll_speaker_schedule.resolve_event_url", return_value=None):
            summary = run_poll(
                method="heuristic",
                events=events,
                now=now,
                persist=True,
                dry_run=True,
                corpus_db=corpus,
            )
        # "a" filtered as already scored; "b" remains pending_url
        self.assertEqual(summary["due_count"], 1)
        self.assertEqual(summary["results"][0]["external_id"], "b")
        self.assertEqual(summary["results"][0]["status"], "pending_url")
        self.assertEqual(summary["pending_url"], 1)


if __name__ == "__main__":
    unittest.main()
