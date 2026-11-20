"""Small HA-Ingress identity -> person/profile assignment for the existing WebUI.

Only activated when HERMES_WEBUI_HA_PERSON_MAP is set. The caller must have
passed the WebUI trusted-header authentication gate first. This is a
personalization aid, not a cross-household access-control boundary.
"""
import hashlib
import hmac
import html
import json
import os
import secrets
import threading
from pathlib import Path
from urllib.parse import parse_qs

_LOCK = threading.RLock()
_MAX_BODY = 2048


def mapping_path():
    raw = os.getenv('HERMES_WEBUI_HA_PERSON_MAP', '').strip()
    return Path(raw) if raw and Path(raw).is_absolute() else None


def _load():
    path = mapping_path()
    if path is None or not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}  # fail closed: never guess Marcel's identity
    if not isinstance(data, dict):
        return {}
    return data


def lookup(user_id):
    if not user_id or mapping_path() is None:
        return None
    with _LOCK:
        entry = _load().get(str(user_id))
    if not isinstance(entry, dict):
        return None
    if entry.get('profile') not in ('default', 'friday'):
        return None
    if not isinstance(entry.get('person'), str) or not entry['person'].strip():
        return None
    return entry


def assign(user_id, person, profile):
    """Persist an explicit one-time choice. Never log IDs or names."""
    path = mapping_path()
    if path is None or not user_id or profile not in ('default', 'friday'):
        raise ValueError('invalid assignment')
    person = str(person).strip()
    if not person or len(person) > 80 or any(ord(c) < 32 for c in person):
        raise ValueError('invalid person')
    with _LOCK:
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
            except (OSError, ValueError) as exc:
                raise ValueError('mapping unavailable') from exc
            if not isinstance(data, dict):
                raise ValueError('mapping unavailable')
        else:
            data = {}
        if user_id in data:
            raise ValueError('already assigned')
        data[str(user_id)] = {'person': person, 'profile': profile}
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temp = path.with_name(path.name + '.' + secrets.token_hex(8) + '.tmp')
        try:
            fd = os.open(str(temp), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, sort_keys=True)
                f.write('\n')
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp, path)
            os.chmod(path, 0o600)
        finally:
            temp.unlink(missing_ok=True)
    return data[str(user_id)]


def _csrf(info, user_id):
    # WebUI auth token is server-side and unique to this browser session.
    return hmac.new(str(info['token']).encode(),
                    ('ha-person:' + user_id).encode(), hashlib.sha256).hexdigest()


def handle(handler, info):
    """Serve the one-time selection page or accept its explicit POST."""
    from api.auth import _trusted_auth_username
    from api.routes import _raw_peer_is_trusted_proxy
    user_id = _trusted_auth_username(handler)
    if (not _raw_peer_is_trusted_proxy(handler) or not user_id or
            not info or info.get('auth_type') != 'trusted' or
            info.get('username') != user_id):
        return _reply(handler, 403, 'Nicht verfügbar')
    prefix = (handler.headers.get('X-Ingress-Path') or '').rstrip('/')
    if not prefix.startswith('/') or '//' in prefix or '\r' in prefix or '\n' in prefix:
        prefix = ''
    current = lookup(user_id)
    if current:
        if handler.command == 'POST':
            handler.close_connection = True  # do not reuse a socket with an unread body
            return _reply(handler, 409, 'Bereits zugeordnet')
        return _redirect(handler, prefix + '/')
    if handler.command == 'POST':
        try:
            size = int(handler.headers.get('Content-Length', '-1'))
            if size < 1 or size > _MAX_BODY or handler.headers.get('Content-Type', '').split(';')[0] != 'application/x-www-form-urlencoded':
                return _reply(handler, 400, 'Ungültige Eingabe')
            form = parse_qs(handler.rfile.read(size).decode('utf-8'), strict_parsing=True)
            csrf = form.get('csrf', [''])[0]
            if not hmac.compare_digest(csrf, _csrf(info, user_id)):
                return _reply(handler, 403, 'Ungültige Sitzung')
            role = form.get('role', [''])[0]
            person = 'Marcel' if role == 'marcel' else form.get('person', [''])[0]
            profile = {'marcel': 'default', 'household': 'friday'}.get(role)
            assign(user_id, person, profile)
            return _redirect(handler, prefix + '/')
        except (ValueError, UnicodeError):
            return _reply(handler, 400, 'Ungültige Eingabe oder Zuordnung bereits vorhanden')
    if handler.command != 'GET':
        return _reply(handler, 405, 'Methode nicht erlaubt')
    action = html.escape(prefix + '/ha-person', quote=True)
    token = html.escape(_csrf(info, user_id), quote=True)
    page = f'''<!doctype html><html lang="de"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Person zuordnen</title><style>body{{font:18px system-ui;background:#17191e;color:#eee;max-width:35rem;margin:3rem auto;padding:1rem}}button,input{{font:inherit;padding:.8rem;margin:.4rem 0}}input{{width:95%}}section{{padding:1rem;border:1px solid #777;margin:1rem 0}}</style><h1>Einmalige Zuordnung</h1><p>Wähle, wer dieses Home-Assistant-Konto verwendet. Die Auswahl bestimmt Assistenz und persönliche Antworten; sie ist keine Zugriffssperre.</p><section><form method="post" action="{action}"><input type="hidden" name="csrf" value="{token}"><input type="hidden" name="role" value="marcel"><button type="submit">Ich bin Marcel – JARVIS</button></form></section><section><form method="post" action="{action}"><input type="hidden" name="csrf" value="{token}"><input type="hidden" name="role" value="household"><label>Name für persönliche Antworten <input name="person" maxlength="80" required autocomplete="name"></label><button type="submit">Haushaltsmitglied – FRIDAY</button></form></section></html>'''
    return _reply(handler, 200, page, 'text/html; charset=utf-8')


def _reply(handler, status, text, content_type='text/plain; charset=utf-8'):
    body = text.encode('utf-8')
    handler.send_response(status)
    handler.send_header('Content-Type', content_type)
    handler.send_header('Cache-Control', 'no-store')
    handler.send_header('X-Content-Type-Options', 'nosniff')
    handler.send_header('Content-Length', str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)
    return True


def _redirect(handler, path):
    handler.send_response(303)
    handler.send_header('Location', path)
    handler.send_header('Cache-Control', 'no-store')
    handler.send_header('Content-Length', '0')
    handler.end_headers()
    return True
