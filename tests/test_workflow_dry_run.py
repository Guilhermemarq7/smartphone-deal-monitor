"""Exercise the workflow's actual Bash step without running collectors or Telegram."""

import os
from pathlib import Path
import shutil
import subprocess

import pytest
import yaml


BASH = shutil.which('bash')
pytestmark = pytest.mark.skipif(BASH is None, reason='Bash necessário para testar o workflow Linux')


@pytest.fixture(scope='module')
def radar_step():
    path = Path(__file__).resolve().parents[1] / '.github/workflows/radar.yml'
    # Preserve 'on' as a string, matching Actions rather than YAML 1.1 booleans.
    workflow = yaml.load(path.read_text(encoding='utf-8'), Loader=yaml.BaseLoader)
    assert workflow['on']['workflow_dispatch']['inputs']['dry_run']['default'] == 'true'
    return next(step for step in workflow['jobs']['radar']['steps']
                if step.get('name') == 'Executar radar')


def run_step(step, tmp_path, event, dry_run, radar_exit=0):
    assert step['shell'] == 'bash'
    assert step['env']['RADAR_DRY_RUN'] == '${{ inputs.dry_run }}'
    capture = tmp_path / 'radar-args'
    env = {'PATH': os.defpath, 'GITHUB_EVENT_NAME': event,
           'RADAR_ARGS_CAPTURE': str(capture)}
    if dry_run is not None:
        env['RADAR_DRY_RUN'] = dry_run
    # Capture the command arguments instead of executing the application.
    # No credentials are inherited, no network requests or messages are sent.
    stub = ('python() { printf "%s\\0" "$@" > "$RADAR_ARGS_CAPTURE"; '
            f'return {radar_exit}; }}\n')
    result = subprocess.run([BASH, '-e', '-u', '-o', 'pipefail', '-c',
                             stub + step['run']], env=env, cwd=tmp_path,
                            capture_output=True, text=True)
    args = capture.read_bytes().decode().rstrip('\0').split('\0')
    return result, args


@pytest.mark.parametrize('event,dry_run,no_alerts', [
    ('workflow_dispatch', 'false', False),
    ('workflow_dispatch', 'true', True),
    ('workflow_dispatch', None, True),  # Input absent, as observed in the runner.
    ('workflow_dispatch', '', True),  # Null/empty Actions input resolves to ''.
    ('workflow_dispatch', 'null', True),
    ('workflow_dispatch', 'FALSE', True),  # Only literal false enables alerts.
    ('schedule', None, False),
    ('schedule', 'true', False),
    ('schedule', 'false', False),
])
def test_workflow_alert_mode(radar_step, tmp_path, event, dry_run, no_alerts):
    result, args = run_step(radar_step, tmp_path, event, dry_run)
    assert result.returncode == 0, result.stderr
    assert args == ['main.py', '--cloud', '--fail-on-critical'] + (
        ['--no-alerts'] if no_alerts else [])


def test_workflow_preserves_critical_exit(radar_step, tmp_path):
    result, args = run_step(radar_step, tmp_path, 'workflow_dispatch', None, radar_exit=2)
    assert result.returncode == 2
    assert '--no-alerts' in args
