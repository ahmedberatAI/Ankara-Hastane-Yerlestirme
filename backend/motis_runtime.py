"""Bind the local listener to the pinned executable and actual import directory.

OS inspection is separate from frozen routing mathematics. No process is
started, stopped or changed here; inability to verify remains unavailable.
"""
from pathlib import Path
import psutil
from backend.motis import LOCAL


def runtime_identity():
    try:
        listeners = [c for c in psutil.net_connections(kind='tcp4')
            if c.status == psutil.CONN_LISTEN and c.laddr.port == 8088]
        if len(listeners) != 1 or listeners[0].laddr.ip != '127.0.0.1' or not listeners[0].pid:
            raise RuntimeError('MOTIS için tek yerel 127.0.0.1:8088 dinleyicisi doğrulanamadı.')
        process = psutil.Process(listeners[0].pid)
        created = process.create_time()
        expected_exe = (LOCAL.parent / 'motis-2.10.2/motis.exe').resolve()
        if Path(process.exe()).resolve() != expected_exe:
            raise RuntimeError('8088 portundaki süreç sürüme sabitlenmiş MOTIS motoru değil.')
        cwd = Path(process.cwd()).resolve()
        arguments = process.cmdline()
        # The supported launcher uses explicit data and logging arguments;
        # reject unverified config/data overrides rather than guessing them.
        if arguments[1:] != ['server', '--data', 'data', '--log-level', 'error']:
            raise RuntimeError('MOTIS başlangıç/veri argümanları doğrulanmış yerel kurulumla uyuşmuyor.')
        if cwd != LOCAL.resolve() or (cwd / arguments[3]).resolve() != (LOCAL / 'data').resolve():
            raise RuntimeError('Çalışan MOTIS farklı bir içe aktarma dizini kullanıyor.')
        if not process.is_running() or process.create_time() != created:
            raise RuntimeError('MOTIS süreci doğrulama sırasında değişti.')
        return {'pid': process.pid, 'processCreatedEpoch': created,
                'executable': 'work/free-routing-research-2026-10-26/motis-2.10.2/motis.exe',
                'importDirectory': 'work/free-routing-research-2026-10-26/local-motis/data',
                'listener': '127.0.0.1:8088', 'processImportVerified': True}
    except (psutil.Error, OSError) as exc:
        raise RuntimeError('Yerel MOTIS süreç/veri dizini kimliği doğrulanamadı.') from exc
