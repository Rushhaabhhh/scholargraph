"""Ground-truth evaluation runs after resolution, outside candidate generation."""

import json
from pathlib import Path


def evaluate_resolution(database, truth_path: str | Path) -> dict:
    actual = predicted = correct = candidate_hits = false_merges = false_splits = 0
    failures = {'incorrect_merge': [], 'abstained_or_split': []}
    with Path(truth_path).open(encoding='utf-8') as stream:
        for line in stream:
            truth = json.loads(line)
            match = database.execute('SELECT canonical_author_id FROM entity_resolution_matches WHERE noisy_record_id=?',
                                     (truth['record_id'],)).fetchone()
            candidates = database.execute('SELECT candidate_ids_json FROM entity_resolution_candidates WHERE noisy_record_id=?',
                                          (truth['record_id'],)).fetchone()
            actual += 1
            candidate_hits += candidates is not None and truth['source_author_id'] in json.loads(candidates[0])
            matched = match is not None and match[0] is not None
            predicted += matched
            is_correct = matched and match[0] == truth['source_author_id']
            correct += is_correct
            false_merges += matched and not is_correct
            false_splits += not matched
            category = 'incorrect_merge' if matched else 'abstained_or_split'
            if not is_correct and len(failures[category]) < 5:
                failures[category].append({'record_id': truth['record_id'], 'expected_author_id': truth['source_author_id'],
                                 'predicted_author_id': match[0] if match else None,
                                 'error': 'incorrect_merge' if matched else 'abstained_or_split'})
    precision = correct / predicted if predicted else 0.0
    recall = correct / actual if actual else 0.0
    return {'records': actual, 'predicted': predicted, 'correct': correct, 'precision': precision, 'recall': recall,
            'f1': 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
            'candidate_recall': candidate_hits / actual if actual else 0.0, 'incorrect_merges': false_merges,
            'abstained_or_split': false_splits, 'failure_examples': failures['incorrect_merge'] + failures['abstained_or_split'],
            'task': 'Known-identity linkage of synthetic noisy authorship observations, not open-world clustering.'}
