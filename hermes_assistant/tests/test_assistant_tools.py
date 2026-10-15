import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "assistant_tools.py"
SPEC = importlib.util.spec_from_file_location("assistant_tools", MODULE_PATH)
assistant_tools = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(assistant_tools)


class AssistantToolsTest(unittest.TestCase):
    def test_protocol_lists_keyless_tools(self):
        response = assistant_tools.dispatch({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        names = {item["name"] for item in response["result"]["tools"]}
        self.assertEqual(names, {"route_and_maps", "weather_forecast"})

    def test_route_creates_preview_and_mobile_links(self):
        origin = {"lat": 48.2, "lon": 16.3, "label": "Start"}
        destination = {"lat": 48.1, "lon": 16.4, "label": "Ziel"}
        route = {"code": "Ok", "routes": [{
            "distance": 12340, "duration": 1500,
            "geometry": {"coordinates": [[16.3, 48.2], [16.4, 48.1]]},
        }]}
        with tempfile.TemporaryDirectory() as temp, \
                patch.object(assistant_tools, "OUTPUT_DIR", Path(temp)), \
                patch.object(assistant_tools, "resolve_place", side_effect=[origin, destination]), \
                patch.object(assistant_tools, "request_json", return_value=route):
            result = assistant_tools.route_tool({"destination": "Ziel"})
            self.assertEqual(result["distance_km"], 12.3)
            self.assertIn("google.com/maps", result["links"]["google_maps"])
            self.assertIn("maps.apple.com", result["links"]["apple_maps"])
            self.assertTrue(Path(result["preview_file"]).is_file())
            self.assertIn("::preview", result["preview_directive"])

    def test_weather_creates_modern_preview(self):
        place = {"lat": 48.2, "lon": 16.3, "label": "Wien"}
        payload = {
            "current": {"temperature_2m": 20, "apparent_temperature": 19, "weather_code": 1,
                        "wind_speed_10m": 8, "relative_humidity_2m": 50},
            "daily": {"time": ["2026-10-16", "2026-10-17"], "weather_code": [1, 61],
                      "temperature_2m_max": [21, 18], "temperature_2m_min": [10, 9],
                      "precipitation_probability_max": [5, 70],
                      "sunrise": ["07:00", "07:01"], "sunset": ["18:00", "17:58"]},
        }
        with tempfile.TemporaryDirectory() as temp, \
                patch.object(assistant_tools, "OUTPUT_DIR", Path(temp)), \
                patch.object(assistant_tools, "resolve_place", return_value=place), \
                patch.object(assistant_tools, "request_json", return_value=payload):
            result = assistant_tools.weather_tool({"days": 2})
            preview = Path(result["preview_file"])
            self.assertTrue(preview.is_file())
            content = preview.read_text(encoding="utf-8")
            self.assertIn("Temperaturverlauf", content)
            self.assertIn("WETTER", content)
            self.assertEqual(len(result["forecast"]), 2)


if __name__ == "__main__":
    unittest.main()
