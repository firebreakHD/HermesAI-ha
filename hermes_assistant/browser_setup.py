"""Merge native Bot Screen settings; restore owned fields when disabled."""
import copy
import json
import os
from pathlib import Path
import sys
import yaml

SETTINGS = {
    'browser': {'headed': True, 'cloud_provider': 'local'},
    'bot_desktop': {'auto_start': True, 'idle_stop_minutes': 0, 'placement': 'gateway'},
}


def merge(config, enabled, saved=None):
    result = copy.deepcopy(config)
    original = copy.deepcopy(saved) if saved is not None else {}
    for section, values in SETTINGS.items():
        current = result.setdefault(section, {})
        if not isinstance(current, dict):
            raise ValueError('Expected mapping for ' + section)
        if enabled:
            before = original.setdefault(section, {})
            for key, value in values.items():
                before.setdefault(key, {'present': key in current, 'value': current.get(key)})
                current[key] = value
        elif saved:
            for key, value in values.items():
                # Do not overwrite an operator's later edits.
                previous = saved.get(section, {}).get(key)
                if previous and current.get(key) == value:
                    if previous['present']:
                        current[key] = previous['value']
                    else:
                        current.pop(key, None)
        if not current:
            result.pop(section, None)
    return result, original


def private_write(path, text):
    temporary = path.with_name(path.name + '.browser.tmp')
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
        stream.write(text)
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def main():
    config_path, options_path = map(Path, sys.argv[1:])
    config = yaml.safe_load(config_path.read_text(encoding='utf-8')) or {}
    options = json.loads(options_path.read_text(encoding='utf-8'))
    enabled = options.get('browser_enabled', True)
    saved_path = config_path.with_name('.browser-original.json')
    saved = json.loads(saved_path.read_text(encoding='utf-8')) if saved_path.exists() else None
    if not enabled and saved is None:
        return
    updated, original = merge(config, enabled, saved)
    if enabled:
        private_write(saved_path, json.dumps(original))
    private_write(config_path, yaml.safe_dump(updated, sort_keys=False))
    if not enabled and saved_path.exists():
        saved_path.unlink()


if __name__ == '__main__':
    main()
