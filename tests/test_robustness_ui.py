"""Render real React markup to prevent false success claims in the report card."""
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.parametrize('script', ['robustness_ui.mjs', 'stage_comparison_ui.mjs', 'shared_capacity_ui.mjs', 'transport_relaxation_ui.mjs', 'benchmark_ui.mjs', 'joint_plan_ui.mjs', 'joint_travel_ui.mjs', 'access_connectors_ui.mjs'])
def test_ui_cards_keep_evidence_scopes_and_unknown_results_separate(script):
    root = Path(__file__).resolve().parents[1]
    node = shutil.which('node')
    if not node or not (root/'node_modules/esbuild').is_dir():
        pytest.skip('Install Node dependencies with npm ci for the React evidence test')
    checked = subprocess.run([node, f'tests/{script}'], cwd=root,
                             capture_output=True, text=True, encoding='utf-8', timeout=30)
    assert checked.returncode == 0, checked.stdout + checked.stderr
