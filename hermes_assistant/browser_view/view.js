import RFB from '../novnc/core/rfb.js';

const $ = (id) => document.getElementById(id);
let viewer, rfb, latest, busy = false, polling = false, closed = false;
async function api(route, body) {
  const response = await fetch(new URL(route, location.href), {
    method: body ? 'POST' : 'GET', cache: 'no-store',
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  let result;
  try { result = await response.json(); } catch { throw new Error('Browserdienst nicht erreichbar. Hermes-Add-on und Home-Assistant-Anmeldung prüfen.'); }
  if (!response.ok) throw new Error(result.error || 'Browseraktion fehlgeschlagen. Ansicht neu öffnen.');
  return result;
}
function showError(text) { $('error').textContent = text; $('error').hidden = !text; }
function render() {
  if (!latest) return;
  const human = latest.lease?.holder === 'human';
  const paused = human && latest.lease?.reason === 'paused';
  $('state').textContent = !latest.running ? 'Bildschirm aus' : latest.mine ? 'Du steuerst' : paused ? 'Pausiert' : human ? 'Manuelle Steuerung aktiv' : 'Hermes steuert';
  document.body.classList.toggle('manual', Boolean(latest.mine));
  $('start').hidden = Boolean(latest.running);
  $('take').disabled = busy || !latest.running || latest.mine;
  $('pause').disabled = busy || !latest.running || paused;
  $('return').disabled = busy || !human;
  $('force').hidden = !human || latest.mine || paused;
  $('hint').textContent = latest.blocker || (!latest.installed ? 'Bildschirm-Pakete fehlen im Add-on. Neue Hermes-Version installieren.' : !latest.browser_installed ? 'Chromium fehlt im Add-on.' : latest.mine ? 'Du steuerst denselben Bildschirm wie Hermes. Währenddessen sind Hermes-Browserwerkzeuge gesperrt.' : paused ? 'Hermes und manuelle Eingaben sind pausiert. Übernehmen oder an Hermes zurückgeben.' : 'Zum Anmelden übernehmen. Falls der Browser noch geschlossen ist, das Browser-Symbol unten im Hermes-Bildschirm öffnen.');
  if (rfb) rfb.viewOnly = !latest.mine;
}
async function refresh() {
  if (polling || closed) return;
  polling = true;
  try {
    latest = await api(`status?viewer_id=${encodeURIComponent(viewer)}`);
    render();
  } catch (error) {
    if (rfb) rfb.viewOnly = true;
    showError(error.message);
  } finally { polling = false; }
}
function connect() {
  rfb?.disconnect(); rfb = null;
  if (!latest?.running) return;
  const url = new URL(`ws?viewer_id=${encodeURIComponent(viewer)}`, location.href);
  url.protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  rfb = new RFB($('screen'), url.href, { shared: true });
  rfb.scaleViewport = true; rfb.resizeSession = false; rfb.viewOnly = !latest.mine;
  rfb.addEventListener('disconnect', () => { if (!closed) showError('Bildverbindung beendet. Bei manueller Übernahme bleibt Hermes gesperrt. Mit „Bild erneut verbinden“ neu verbinden.'); });
  rfb.addEventListener('connect', () => showError(''));
}
async function control(action) {
  if (busy) return;
  busy = true; render(); showError('');
  try {
    const result = await api('control', { viewer_id: viewer, action });
    if (result.error) throw new Error(result.error);
    await refresh();
    if (action === 'start') connect();
    if (action === 'return' || action === 'force_return') $('hint').textContent = 'Steuerung zurückgegeben. Schreibe jetzt „Weiter“ im Hermes-Chat. Hermes muss die aktuelle Seite neu prüfen.';
  } catch (error) { showError(error.message); }
  finally { busy = false; render(); }
}
for (const [id, action] of Object.entries({ start: 'start', take: 'take', pause: 'pause', return: 'return', force: 'force_return' })) $(id).addEventListener('click', () => control(action));
$('reconnect').addEventListener('click', async () => { await refresh(); connect(); });
try { viewer = (await api('viewer', {})).viewer_id; await refresh(); connect(); }
catch (error) { showError(error.message); }
const timer = setInterval(refresh, 2000);
addEventListener('pagehide', () => { closed = true; clearInterval(timer); rfb?.disconnect(); });
