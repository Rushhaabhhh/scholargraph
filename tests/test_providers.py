"""Schema validity, semantic fidelity, real-recording provenance and fallback."""

import json
import unittest
from pathlib import Path
from pydantic import ValidationError
from hiresense.assistant.providers import LocalLLMProvider, QueryUnderstander, RecordedProvider, deterministic_intent
from hiresense.assistant.schemas import QueryIntent

ROOT = Path(__file__).resolve().parents[1]


class ProviderTests(unittest.TestCase):
    def test_live_local_provider_handles_an_unseen_query(self):
        class LocalModel:
            def create_chat_completion(self, **kwargs):
                return {'choices': [{'message': {'content': json.dumps({
                    'topics': ['distributed storage'], 'recency_preference': 'any', 'since_year': None,
                })}}]}
            def reset(self):
                pass
        provider = LocalLLMProvider('/unused-model')
        provider.model = LocalModel()
        result = QueryUnderstander(provider).understand('distributed storage')
        self.assertEqual(result['provider'], 'local_llm')
        self.assertFalse(result['used_fallback'])
        self.assertEqual(result['intent']['topics'], ['distributed storage'])

    def test_recordings_are_actual_model_outputs_and_are_validated_on_replay(self):
        recordings = json.loads((ROOT / 'resources/recordings/query-intents.json').read_text())
        model = json.loads((ROOT / 'resources/recordings/local-model.json').read_text())
        self.assertEqual(recordings['provenance']['model_sha256'], model['sha256'])
        self.assertEqual(recordings['provenance']['revision'], model['revision'])
        self.assertIn('unedited', recordings['provenance']['method'])
        provider = RecordedProvider(ROOT / 'resources/recordings/query-intents.json')
        for item in recordings['records']:
            self.assertEqual(provider.extract(item['query']), item['raw_output'])
            QueryIntent.model_validate_json(item['raw_output'])
        parsed = QueryUnderstander(provider).understand('an entirely unseen research query on distributed storage')
        self.assertTrue(parsed['used_fallback'])
        self.assertEqual(parsed['fallback_reason'], 'query_not_recorded')

    def test_schema_valid_but_wrong_topic_or_year_or_preference_is_rejected(self):
        class Wrong:
            name = 'local_llm'
            def __init__(self, output): self.output = output
            def extract(self, text): return self.output
        outputs = [
            {'topics': ['graph retrieval'], 'recency_preference': 'recent', 'since_year': None},
            {'topics': ['graph retrieval'], 'recency_preference': 'any', 'since_year': 2030},
            {'topics': ['cooking recipes'], 'recency_preference': 'any', 'since_year': None},
        ]
        for output in outputs:
            QueryIntent.model_validate(output)  # Syntactically valid is not sufficient.
            result = QueryUnderstander(Wrong(output)).understand('graph retrieval')
            self.assertTrue(result['used_fallback'])
            self.assertEqual(result['intent']['topics'], ['graph retrieval'])
            self.assertEqual(result['intent']['recency_preference'], 'any')
            self.assertIsNone(result['intent']['since_year'])

    def test_missing_local_llm_and_malformed_provider_json_have_working_fallback(self):
        missing = LocalLLMProvider(ROOT / 'nonexistent-local-query-model.gguf')
        result = QueryUnderstander(missing).understand('recent graph neural networks since 2017')
        self.assertTrue(result['used_fallback'])
        self.assertEqual(result['intent']['since_year'], 2017)
        class Malformed:
            name = 'local_llm'
            def extract(self, text): return '{not valid JSON'
        self.assertTrue(QueryUnderstander(Malformed()).understand('graph retrieval')['used_fallback'])

    def test_failed_live_generation_also_clears_logical_model_state(self):
        class BrokenModel:
            resets = 0
            def create_chat_completion(self, **kwargs):
                raise TimeoutError('generation interrupted')
            def reset(self):
                self.resets += 1
        provider = LocalLLMProvider('/unused-model')
        provider.model = BrokenModel()
        result = QueryUnderstander(provider).understand('graph retrieval')
        self.assertTrue(result['used_fallback'])
        self.assertEqual(provider.model.resets, 1)

    def test_intent_schema_and_explicit_dates_are_strict(self):
        self.assertEqual(deterministic_intent('graph retrieval after 2017').since_year, 2018)
        self.assertEqual(deterministic_intent('latest graph retrieval').recency_preference, 'recent')
        self.assertEqual(deterministic_intent('graph retrieval any year').recency_preference, 'any')
        for item in ({'topics': [' ']}, {'topics': ['graph'], 'since_year': True},
                     {'topics': ['graph'], 'since_year': '2017'}, {'topics': ['graph'], 'tool': 'get_profile'}):
            with self.assertRaises(ValidationError):
                QueryIntent.model_validate(item)
