"""Shared small, real-model backend fixture for integration and safety tests."""

import tempfile
from pathlib import Path
from hiresense.data.prepare_backend import prepare_backend
from hiresense.api.runtime import Backend

ROOT = Path(__file__).resolve().parents[1]


def make_backend():
    temporary = tempfile.TemporaryDirectory(prefix='hiresense-backend-test-')
    report = prepare_backend(ROOT / 'tests/fixtures/temporal.xml', Path(temporary.name) / 'backend', 2019)
    return temporary, Backend.load(report['config']), report['config']
