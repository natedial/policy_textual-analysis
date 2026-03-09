import unittest

from fed_tracker.phrase_signals import build_phrase_signals


class PhraseSignalTests(unittest.TestCase):
    def test_phrase_rarity_prefers_unusual_current_phrases(self):
        current = "The committee discussed driving in the fog and driving in the fog while policy remains restrictive."
        history = [
            "The committee discussed policy and restrictive policy settings.",
            "Policy remains restrictive and inflation remains elevated.",
        ]
        signals = build_phrase_signals(current, history, top_n=5)
        joined = " ".join(signal.phrase_text for signal in signals)
        self.assertIn("driving in the fog", joined)


if __name__ == "__main__":
    unittest.main()
