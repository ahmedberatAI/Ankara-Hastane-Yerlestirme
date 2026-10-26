from pathlib import Path
from types import SimpleNamespace
import pytest
import backend.motis_runtime as runtime


@pytest.fixture
def process(monkeypatch, tmp_path):
    local = tmp_path / 'local-motis'
    local.mkdir()
    exe = tmp_path / 'motis-2.10.2/motis.exe'
    monkeypatch.setattr(runtime, 'LOCAL', local)
    values = {'pid': 123, 'cwd': str(local), 'exe': str(exe), 'created': 100.,
              'args': [str(exe), 'server', '--data', 'data', '--log-level', 'error']}
    fake = SimpleNamespace(pid=123, create_time=lambda: values['created'],
        cwd=lambda: values['cwd'], exe=lambda: values['exe'],
        cmdline=lambda: values['args'], is_running=lambda: True)
    monkeypatch.setattr(runtime.psutil, 'Process', lambda pid: fake)
    listener = SimpleNamespace(status=runtime.psutil.CONN_LISTEN,
        laddr=SimpleNamespace(port=8088, ip='127.0.0.1'), pid=123)
    monkeypatch.setattr(runtime.psutil, 'net_connections', lambda **kwargs: [listener])
    return values, listener


def test_local_process_binds_executable_cwd_data_and_birth_time(process):
    result = runtime.runtime_identity()
    assert result['processImportVerified'] is True
    assert result['pid'] == 123 and result['processCreatedEpoch'] == 100


@pytest.mark.parametrize('field,value', [
    ('cwd', '/different-import'), ('exe', '/another/motis.exe'),
    ('args', ['motis.exe', 'server', '--data', 'other-import', '--log-level', 'error']),
    ('args', ['motis.exe', 'server', '--data', 'data', '--log-level', 'error', '--config', 'other.yml']),
])
def test_same_version_is_not_enough_to_verify_process(process, field, value):
    values, _ = process
    values[field] = value
    with pytest.raises(RuntimeError):
        runtime.runtime_identity()


def test_public_listener_is_not_the_verified_local_motor(process):
    _, listener = process
    listener.laddr.ip = '0.0.0.0'
    with pytest.raises(RuntimeError, match='tek yerel'):
        runtime.runtime_identity()


def test_unknown_listener_or_owner_remains_unavailable(process, monkeypatch):
    monkeypatch.setattr(runtime.psutil, 'net_connections', lambda **kwargs: [])
    with pytest.raises(RuntimeError):
        runtime.runtime_identity()


def test_permission_failure_does_not_approve_an_unverified_process(process, monkeypatch):
    def denied(pid):
        raise runtime.psutil.AccessDenied(pid)
    monkeypatch.setattr(runtime.psutil, 'Process', denied)
    with pytest.raises(RuntimeError, match='kimliği doğrulanamadı'):
        runtime.runtime_identity()
