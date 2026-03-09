import unittest

from fed_tracker.agent_service import FedTextAgentService
from test_persistence_flow import FakeDatabase


class AgentServiceTests(unittest.TestCase):
    def test_service_ingests_and_answers_questions(self):
        db = FakeDatabase()
        service = FedTextAgentService(database=db)

        service.ingest_markdown(
            "Inflation has moderated and labor market conditions have improved.",
            metadata={
                "speaker_name": "Jerome H. Powell",
                "speech_date": "2026-01-10",
                "document_type": "speech",
            },
        )
        service.ingest_markdown(
            "Inflation remains elevated, labor market conditions are tight, and policy may need to stay restrictive.",
            metadata={
                "speaker_name": "Jerome H. Powell",
                "speech_date": "2026-02-10",
                "document_type": "speech",
            },
        )

        brief = service.speaker_brief("Jerome H. Powell", theme="INFLATION")
        answer = service.answer_question(
            "Jerome H. Powell",
            "How has Powell's inflation rhetoric shifted?",
        )

        self.assertIn("latest_snapshot", brief)
        self.assertIn("theme_drift_24m", brief)
        self.assertEqual(answer["theme_focus"], "INFLATION")
        self.assertTrue(answer["highlights"])


if __name__ == "__main__":
    unittest.main()
