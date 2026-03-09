import unittest

from fed_tracker.contract import API_VERSION, cli_envelope, get_openapi_schema


class ContractTests(unittest.TestCase):
    def test_cli_envelope_is_versioned(self):
        payload = cli_envelope(command="ingest", data={"x": 1})
        self.assertEqual(payload["api_version"], API_VERSION)
        self.assertEqual(payload["transport"], "cli")
        self.assertEqual(payload["operation"], "ingest")
        self.assertEqual(payload["data"]["x"], 1)

    def test_openapi_schema_version_matches_contract(self):
        schema = get_openapi_schema()
        self.assertEqual(schema["info"]["version"], API_VERSION)
        self.assertIn("/openapi.json", schema["paths"])


if __name__ == "__main__":
    unittest.main()
