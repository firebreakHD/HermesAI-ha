#!/usr/bin/env python3
"""B1-Auslieferung: nie unpatchte WebUI starten; keine Änderungen an fremden Diffs."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
PATCH = HERE / 'b1.patch'
FILES = ('api/ha_person.py', 'tests/test_ha_person_assignment.py')
BASE = (HERE / 'base-commit').read_text().strip()


def git(path, *args):
    return subprocess.run(['git', '-C', str(path), *args], capture_output=True, text=True)


def state(path):
    diff = git(path, 'diff', '--binary', '--', 'api/auth.py', 'server.py')
    status = git(path, 'status', '--porcelain', '--untracked-files=all')
    if diff.returncode or status.returncode:
        raise RuntimeError('Git-Status nicht lesbar')
    expected = PATCH.read_text()
    changed = {line[3:] for line in status.stdout.splitlines()}
    permitted = {'api/auth.py', 'server.py', *FILES}
    if changed - permitted:
        raise RuntimeError('Fremde lokale Änderungen: Update und B1-Auslieferung blockiert')
    if diff.stdout and diff.stdout != expected:
        raise RuntimeError('Abweichender/teilweiser B1-Diff: keine Änderung')
    for name in FILES:
        dest = path / name
        if dest.exists() and dest.read_bytes() != (HERE / 'files' / name).read_bytes():
            raise RuntimeError(f'Abweichende B1-Datei: {name}')
    if changed and (diff.stdout != expected or any(not (path / name).exists() for name in FILES)):
        raise RuntimeError('Unvollständige B1-Änderung: keine Änderung')
    return bool(changed)


def apply(path):
    if state(path):
        print('B1 bereits vollständig vorhanden')
        return
    check = git(path, 'apply', '--check', str(PATCH))
    if check.returncode:
        raise RuntimeError('B1 inkompatibel: ' + check.stderr.strip())
    result = git(path, 'apply', str(PATCH))
    if result.returncode:
        raise RuntimeError('B1-Patch fehlgeschlagen: ' + result.stderr.strip())
    for name in FILES:
        dest = path / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(HERE / 'files' / name, dest)
    if not state(path):
        raise RuntimeError('B1-Nachprüfung fehlgeschlagen')
    print('B1 angewendet und geprüft')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('checkout', type=Path)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--update', action='store_true')
    group.add_argument('--no-update', action='store_true')
    args = parser.parse_args()
    path = args.checkout.resolve()
    current = state(path)
    if current:
        # Insbesondere keine Git-Operation, die das installierte Dirty-Checkout überschreibt.
        if args.update:
            print('B1-Checkout dirty: Upstream-Update übersprungen', file=sys.stderr)
        apply(path)
        return
    if not args.update:
        apply(path)
        return
    # Staging in persistentem /data auf demselben Dateisystem; niemals live reset/clean.
    stage = path.with_name(path.name + '.b1-stage')
    backup = path.with_name(path.name + '.b1-previous')
    if stage.exists() or backup.exists():
        raise RuntimeError('Staging/Backup vorhanden; manuelle Prüfung erforderlich')
    shutil.copytree(path, stage, symlinks=True)
    try:
        fetched = git(stage, 'fetch', '--depth=1', 'origin', 'master')
        if fetched.returncode:
            print('Upstream nicht erreichbar; installierten Stand verwenden', file=sys.stderr)
            apply(path)
            return
        checked = git(stage, 'checkout', '--detach', 'FETCH_HEAD')
        if checked.returncode:
            raise RuntimeError('Staging-Checkout fehlgeschlagen: ' + checked.stderr.strip())
        apply(stage)
        # Die alte Installation bleibt als vollständiges Rollback erhalten.
        os.rename(path, backup)
        try:
            os.rename(stage, path)
        except OSError:
            os.rename(backup, path)
            raise
        print(f'B1-Staging aktiviert; Rollback: {backup}')
    finally:
        if stage.exists():
            shutil.rmtree(stage)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError) as exc:
        print(f'B1 FEHLER: {exc}', file=sys.stderr)
        sys.exit(1)
