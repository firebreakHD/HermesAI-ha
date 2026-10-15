#!/usr/bin/env python3
"""Keyless local MCP tools for maps, directions and weather."""

from __future__ import annotations

import html
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path


SERVER = {"name": "hermes-local-assistant", "version": "1.0.0"}
OUTPUT_DIR = Path(os.environ.get("HERMES_HOME", "/data/hermes")) / "generated"
USER_AGENT = "HermesAI-ha local assistant/1.0 (personal Home Assistant add-on)"


TOOLS = [
    {
        "name": "route_and_maps",
        "description": (
            "Find a destination, calculate driving distance and duration, and create clickable Google Maps, "
            "Apple Maps and OpenStreetMap links. If origin is omitted, use the Home Assistant home location. "
            "No API key is required."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "destination": {"type": "string", "description": "Address, place or business to travel to"},
                "origin": {"type": "string", "description": "Optional starting address; omit for Home Assistant home"},
                "travel_mode": {"type": "string", "enum": ["driving", "walking", "bicycling", "transit"], "default": "driving"},
            },
            "required": ["destination"],
        },
    },
    {
        "name": "weather_forecast",
        "description": (
            "Get current weather and a 1-7 day forecast for a place without an API key. If location is omitted, "
            "use the Home Assistant home location. Creates a modern interactive HTML weather card for Hermes Desktop."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "Optional city, address or place"},
                "days": {"type": "integer", "minimum": 1, "maximum": 7, "default": 5},
            },
        },
    },
]


WEATHER_CODES = {
    0: "Klar", 1: "Überwiegend klar", 2: "Teilweise bewölkt", 3: "Bewölkt",
    45: "Nebel", 48: "Raureifnebel", 51: "Leichter Nieselregen", 53: "Nieselregen",
    55: "Starker Nieselregen", 61: "Leichter Regen", 63: "Regen", 65: "Starker Regen",
    71: "Leichter Schneefall", 73: "Schneefall", 75: "Starker Schneefall", 77: "Schneekörner",
    80: "Leichte Regenschauer", 81: "Regenschauer", 82: "Starke Regenschauer",
    85: "Leichte Schneeschauer", 86: "Starke Schneeschauer", 95: "Gewitter",
    96: "Gewitter mit Hagel", 99: "Starkes Gewitter mit Hagel",
}


def request_json(url: str, headers: dict[str, str] | None = None, timeout: int = 15) -> dict | list:
    merged = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        merged.update(headers)
    request = urllib.request.Request(url, headers=merged)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def read_env_file() -> dict[str, str]:
    values: dict[str, str] = {}
    path = Path(os.environ.get("HERMES_HOME", "/data/hermes")) / ".env"
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    except OSError:
        pass
    return values


def home_location() -> dict | None:
    env = read_env_file()
    url, token = env.get("HASS_URL", ""), env.get("HASS_TOKEN", "")
    if not url or not token:
        return None
    try:
        state = request_json(
            f"{url.rstrip('/')}/api/states/zone.home",
            {"Authorization": f"Bearer {token}"},
        )
        attrs = state.get("attributes", {})
        lat, lon = attrs.get("latitude"), attrs.get("longitude")
        if lat is None or lon is None:
            return None
        return {"lat": float(lat), "lon": float(lon), "label": attrs.get("friendly_name", "Zuhause")}
    except Exception:
        return None


def geocode(query: str) -> dict:
    params = urllib.parse.urlencode({"q": query, "format": "jsonv2", "limit": 1, "addressdetails": 1})
    result = request_json(f"https://nominatim.openstreetmap.org/search?{params}")
    if not result:
        raise ValueError(f"Ort nicht gefunden: {query}")
    item = result[0]
    return {"lat": float(item["lat"]), "lon": float(item["lon"]), "label": item.get("display_name", query)}


def resolve_place(query: str | None) -> dict:
    if query and query.strip():
        return geocode(query.strip())
    location = home_location()
    if location:
        return location
    raise ValueError("Kein Startort angegeben und Home Assistant zone.home enthält keine nutzbare Position.")


def safe_name(prefix: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_DIR / f"{prefix}-{int(time.time() * 1000)}.html"


def atomic_write(path: Path, content: str) -> None:
    temp = path.with_suffix(".tmp")
    temp.write_text(content, encoding="utf-8")
    os.chmod(temp, 0o600)
    temp.replace(path)


def page_shell(title: str, body: str, script: str = "") -> str:
    return f"""<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>
:root{{--bg:transparent;--card:color-mix(in srgb,var(--card,#111827) 92%,transparent);--fg:var(--foreground,#f4f5f7);--muted:var(--muted-foreground,#9ca3af);--accent:var(--accent,#35d0ba);--border:var(--border,#334155)}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,sans-serif}}.wrap{{padding:14px;display:grid;gap:12px}}.card{{background:var(--card);border:1px solid var(--border);border-radius:18px;padding:16px;box-shadow:0 10px 30px #0003}}h1,h2,p{{margin:0}}h1{{font-size:20px}}.muted{{color:var(--muted)}}.hero{{display:flex;align-items:end;justify-content:space-between;gap:16px}}.big{{font-size:42px;font-weight:750;letter-spacing:-2px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:8px}}.pill{{border:1px solid var(--border);border-radius:14px;padding:10px;background:#ffffff08}}a{{color:var(--accent);font-weight:650;text-decoration:none}}.links{{display:flex;flex-wrap:wrap;gap:8px}}.links a{{border:1px solid var(--border);border-radius:12px;padding:10px 12px}}svg{{width:100%;height:auto;overflow:visible}}@media(max-width:520px){{.wrap{{padding:8px}}.card{{padding:13px;border-radius:15px}}.big{{font-size:36px}}}}
</style></head><body><main class="wrap">{body}</main>{script}</body></html>"""


def map_links(origin: dict, destination: dict, mode: str) -> dict[str, str]:
    start = f"{origin['lat']},{origin['lon']}"
    end = f"{destination['lat']},{destination['lon']}"
    google = "https://www.google.com/maps/dir/?" + urllib.parse.urlencode({
        "api": 1, "origin": start, "destination": end, "travelmode": mode,
    })
    apple_modes = {"driving": "d", "walking": "w", "transit": "r", "bicycling": "d"}
    apple = "https://maps.apple.com/?" + urllib.parse.urlencode({
        "saddr": start, "daddr": end, "dirflg": apple_modes.get(mode, "d"),
    })
    osm = "https://www.openstreetmap.org/directions?" + urllib.parse.urlencode({
        "engine": "fossgis_osrm_car", "route": f"{start};{end}",
    })
    return {"google_maps": google, "apple_maps": apple, "openstreetmap": osm}


def route_tool(args: dict) -> dict:
    destination_text = str(args.get("destination", "")).strip()
    if not destination_text:
        raise ValueError("Ziel fehlt.")
    mode = str(args.get("travel_mode", "driving"))
    origin = resolve_place(args.get("origin"))
    destination = resolve_place(destination_text)
    coords = f"{origin['lon']},{origin['lat']};{destination['lon']},{destination['lat']}"
    route_path = f"router.project-osrm.org/route/v1/driving/{coords}?overview=full&geometries=geojson&steps=true"
    try:
        route_data = request_json(f"https://{route_path}")
    except Exception:
        # The public OSRM demo occasionally serves a broken TLS chain. Route
        # coordinates contain no credentials; keep the keyless tool usable.
        route_data = request_json(f"http://{route_path}")
    if route_data.get("code") != "Ok" or not route_data.get("routes"):
        raise ValueError("Für diese Orte konnte keine Route berechnet werden.")
    route = route_data["routes"][0]
    distance_km = round(route["distance"] / 1000, 1)
    duration_min = max(1, round(route["duration"] / 60))
    links = map_links(origin, destination, mode)
    geometry = route["geometry"]["coordinates"]
    encoded_geometry = html.escape(json.dumps([[lat, lon] for lon, lat in geometry], separators=(",", ":")))
    body = f"""
<section class="card"><p class="muted">ROUTE</p><h1>{html.escape(destination['label'])}</h1><p class="muted">ab {html.escape(origin['label'])}</p></section>
<section class="card hero"><div><p class="muted">Entfernung</p><div class="big">{distance_km} km</div></div><div><p class="muted">Fahrzeit</p><h2>ca. {duration_min} min</h2></div></section>
<section class="card"><div id="map" style="height:320px;border-radius:14px;overflow:hidden"></div></section>
<section class="card links"><a href="{html.escape(links['google_maps'])}">Google Maps öffnen</a><a href="{html.escape(links['apple_maps'])}">Apple Karten öffnen</a><a href="{html.escape(links['openstreetmap'])}">OpenStreetMap</a></section>"""
    script = f"""<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"><script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script><script>
const points={encoded_geometry};const map=L.map('map');L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',{{attribution:'© OpenStreetMap'}}).addTo(map);const line=L.polyline(points,{{color:'#35d0ba',weight:5}}).addTo(map);L.marker(points[0]).addTo(map);L.marker(points[points.length-1]).addTo(map);map.fitBounds(line.getBounds(),{{padding:[20,20]}});
</script>"""
    path = safe_name("route")
    atomic_write(path, page_shell("Route", body, script))
    return {
        "origin": origin["label"], "destination": destination["label"],
        "distance_km": distance_km, "driving_duration_minutes": duration_min,
        "requested_mode": mode,
        "note": "Entfernung und Zeit werden über die Straßenroute berechnet; Google/Apple öffnen die gewünschte Verkehrsart live.",
        "links": links, "preview_file": str(path),
        "preview_directive": f'::preview{{file="{path}"}}',
    }


def sparkline(values: list[float]) -> str:
    blocks = "▁▂▃▄▅▆▇█"
    low, high = min(values), max(values)
    if high == low:
        return blocks[3] * len(values)
    return "".join(blocks[round((value - low) / (high - low) * 7)] for value in values)


def weather_tool(args: dict) -> dict:
    days = max(1, min(7, int(args.get("days", 5))))
    place = resolve_place(args.get("location"))
    params = urllib.parse.urlencode({
        "latitude": place["lat"], "longitude": place["lon"], "timezone": "auto", "forecast_days": days,
        "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,relative_humidity_2m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunrise,sunset",
    })
    data = request_json(f"https://api.open-meteo.com/v1/forecast?{params}")
    current, daily = data["current"], data["daily"]
    highs = [float(value) for value in daily["temperature_2m_max"]]
    lows = [float(value) for value in daily["temperature_2m_min"]]
    forecast = []
    cards = []
    for index, date in enumerate(daily["time"]):
        item = {
            "date": date, "condition": WEATHER_CODES.get(int(daily["weather_code"][index]), "Unbekannt"),
            "max_c": highs[index], "min_c": lows[index],
            "rain_probability_percent": daily["precipitation_probability_max"][index],
        }
        forecast.append(item)
        cards.append(f"<div class='pill'><strong>{html.escape(date[5:])}</strong><br>{html.escape(item['condition'])}<br><b>{item['max_c']:.0f}°</b> / {item['min_c']:.0f}°<br><span class='muted'>Regen {item['rain_probability_percent']}%</span></div>")
    width, height, pad = 700, 190, 28
    all_temps = highs + lows
    lo, hi = min(all_temps) - 1, max(all_temps) + 1
    def points(values: list[float]) -> str:
        return " ".join(f"{pad + i * (width - 2 * pad) / max(1, len(values)-1):.1f},{height-pad-(v-lo)/(hi-lo)*(height-2*pad):.1f}" for i, v in enumerate(values))
    body = f"""
<section class="card"><p class="muted">WETTER · {html.escape(place['label'])}</p><div class="hero"><div class="big">{float(current['temperature_2m']):.0f}°</div><div><h1>{html.escape(WEATHER_CODES.get(int(current['weather_code']), 'Unbekannt'))}</h1><p class="muted">Gefühlt {float(current['apparent_temperature']):.0f}° · Wind {float(current['wind_speed_10m']):.0f} km/h · Feuchte {current['relative_humidity_2m']}%</p></div></div></section>
<section class="card"><svg viewBox="0 0 {width} {height}" role="img" aria-label="Temperaturverlauf"><polyline fill="none" stroke="#35d0ba" stroke-width="5" stroke-linecap="round" stroke-linejoin="round" points="{points(highs)}"/><polyline fill="none" stroke="#60a5fa" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" points="{points(lows)}"/></svg><p class="muted">Höchstwerte {sparkline(highs)} · Tiefstwerte {sparkline(lows)}</p></section>
<section class="card grid">{''.join(cards)}</section>"""
    path = safe_name("weather")
    atomic_write(path, page_shell("Wetter", body))
    return {
        "location": place["label"],
        "current": {
            "temperature_c": current["temperature_2m"], "apparent_c": current["apparent_temperature"],
            "condition": WEATHER_CODES.get(int(current["weather_code"]), "Unbekannt"),
            "wind_kmh": current["wind_speed_10m"], "humidity_percent": current["relative_humidity_2m"],
        },
        "forecast": forecast, "temperature_sparkline": sparkline(highs),
        "source": "Open-Meteo", "preview_file": str(path),
        "preview_directive": f'::preview{{file="{path}"}}',
    }


def tool_result(payload: dict, is_error: bool = False) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}], "isError": is_error}


def dispatch(message: dict) -> dict | None:
    method = message.get("method")
    request_id = message.get("id")
    if request_id is None:
        return None
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": request_id, "result": {
            "protocolVersion": "2025-03-26", "capabilities": {"tools": {}}, "serverInfo": SERVER,
        }}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = message.get("params") or {}
        name, arguments = params.get("name"), params.get("arguments") or {}
        try:
            if name == "route_and_maps":
                result = route_tool(arguments)
            elif name == "weather_forecast":
                result = weather_tool(arguments)
            else:
                raise ValueError(f"Unbekanntes Tool: {name}")
            payload = tool_result(result)
        except Exception as exc:
            payload = tool_result({"error": str(exc)}, True)
        return {"jsonrpc": "2.0", "id": request_id, "result": payload}
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "Method not found"}}


def main() -> None:
    for line in sys.stdin:
        try:
            message = json.loads(line)
            response = dispatch(message)
            if response is not None:
                sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
                sys.stdout.flush()
        except Exception as exc:
            sys.stderr.write(f"assistant-tools protocol error: {exc}\n")
            sys.stderr.flush()


if __name__ == "__main__":
    main()
