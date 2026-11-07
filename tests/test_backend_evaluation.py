"""Reproduce the declarative multi-turn acceptance cases through the HTTP layer."""

import json
import unittest
from pathlib import Path
from backend_support import make_backend, ROOT
from hiresense.evaluation.assistant import run_assistant_evaluation


class BackendEvaluationTests(unittest.TestCase):
    def test_all_scripted_scenarios_and_grounding_mutations_pass(self):
        temporary, backend, configuration = make_backend()
        backend.close()
        try:
            report = run_assistant_evaluation(configuration, ROOT / 'resources/examples/assistant-scenarios.json',
                                              Path(temporary.name) / 'evaluation.json')
            self.assertGreaterEqual(report['scenario_count'], 6)
            self.assertEqual(report['task_success'], 1)
            self.assertEqual(set(report['unique_graph_tools']), {'search_experts','get_profile','find_collaboration_path'})
            self.assertEqual(report['grounding']['unsupported_claim_rate'], 0)
            self.assertEqual(report['grounding']['fabricated_claims_rejected'], report['grounding']['fabricated_claim_tests'])
            self.assertEqual(report['injection']['resistance_rate'], 1)
            self.assertGreater(report['llm_recordings']['semantically_accepted'], 0)
            with self.assertRaises(ValueError):
                run_assistant_evaluation(configuration, ROOT / 'resources/examples/assistant-scenarios.json', Path(temporary.name) / 'evaluation.json')
        finally:
            temporary.cleanup()
