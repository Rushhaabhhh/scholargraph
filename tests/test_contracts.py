"""Keep committed HTTP/tool contracts aligned with executable schemas."""

import json
import unittest
from pathlib import Path
from hiresense.api.app import create_app
from hiresense.assistant.schemas import SearchExpertsArgs,ProfileArgs,PathArgs,QueryIntent

ROOT = Path(__file__).resolve().parents[1]


class ContractTests(unittest.TestCase):
    def test_openapi_is_generated_from_the_actual_routes(self):
        committed = json.loads((ROOT / 'resources/contracts/api.openapi.json').read_text())
        self.assertEqual(committed, create_app().openapi())
        self.assertIn('/sessions/{session_id}/messages', committed['paths'])
        self.assertIn('/sessions/{session_id}/memory', committed['paths'])

    def test_tool_definitions_are_the_actual_execution_argument_schemas(self):
        committed = json.loads((ROOT / 'resources/contracts/tools.schema.json').read_text())
        expected = {'search_experts': SearchExpertsArgs, 'get_profile': ProfileArgs, 'find_collaboration_path': PathArgs}
        for name, model in expected.items():
            self.assertEqual(committed['tools'][name], model.model_json_schema())
        self.assertEqual(committed['query_intent'], QueryIntent.model_json_schema())

    def test_all_committed_schema_references_resolve(self):
        for name in ('api.openapi.json','batch.schema.json'):
            schema = json.loads((ROOT / 'resources/contracts' / name).read_text())
            def walk(value):
                if isinstance(value, dict):
                    if '$ref' in value:
                        self.assertTrue(value['$ref'].startswith('#/'))
                        pointer = schema
                        for part in value['$ref'][2:].split('/'):
                            pointer = pointer[part]
                    for child in value.values(): walk(child)
                elif isinstance(value,list):
                    for child in value: walk(child)
            walk(schema)
