import json
import os
import tempfile
import unittest

import ipcore


class FakeResponse:
    def __init__(self, payload=None, text="", status=200):
        self._payload, self.text, self.status = payload, text, status

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakeHttp:
    """Answers each URL from a dict; anything missing counts as a network error."""

    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def get(self, url, **kwargs):
        self.calls.append(url)
        answer = self.answers.get(url)
        if answer is None:
            raise ConnectionError("offline")
        return answer


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "settings.json")

    def tearDown(self):
        self.dir.cleanup()

    def test_defaults_when_file_missing(self):
        s = ipcore.Settings(self.path).load()
        self.assertEqual(s.data, ipcore.DEFAULT_SETTINGS)

    def test_roundtrip(self):
        s = ipcore.Settings(self.path)
        s.set("x", 120)
        s.set("opacity", 0.5)
        again = ipcore.Settings(self.path).load()
        self.assertEqual(again.get("x"), 120)
        self.assertEqual(again.get("opacity"), 0.5)

    def test_bad_values_are_replaced(self):
        with open(self.path, "w") as fh:
            json.dump({"opacity": "abc", "interval": 1, "x": True, "show_details": "yes",
                       "pinned": "yes", "unknown": 1}, fh)
        s = ipcore.Settings(self.path).load()
        self.assertEqual(s.get("opacity"), 0.7)
        self.assertEqual(s.get("interval"), 5)  # clamped
        self.assertIsNone(s.get("x"))
        self.assertTrue(s.get("show_details"))
        self.assertFalse(s.get("pinned"))
        self.assertNotIn("unknown", s.data)

    def test_popup_is_the_default(self):
        self.assertFalse(ipcore.Settings(self.path).load().get("pinned"))

    def test_pinned_is_remembered(self):
        ipcore.Settings(self.path).set("pinned", True)
        self.assertTrue(ipcore.Settings(self.path).load().get("pinned"))

    def test_corrupt_file_is_ignored(self):
        with open(self.path, "w") as fh:
            fh.write("{not json")
        self.assertEqual(ipcore.Settings(self.path).load().data, ipcore.DEFAULT_SETTINGS)


class UpdateTests(unittest.TestCase):
    def test_versions_are_compared_as_numbers(self):
        self.assertTrue(ipcore.is_newer("v1.10.0", "1.9.0"))
        self.assertTrue(ipcore.is_newer("1.2", "1.1.9"))
        self.assertFalse(ipcore.is_newer("v1.1.0", "1.1.0"))
        self.assertFalse(ipcore.is_newer("v1.0.0", "1.1.0"))
        self.assertFalse(ipcore.is_newer("", "1.1.0"))
        self.assertFalse(ipcore.is_newer("latest", "1.1.0"))

    def test_check_reads_the_tag(self):
        http = FakeHttp({ipcore.RELEASES_API: FakeResponse({"tag_name": "v1.10.0"})})
        self.assertEqual(ipcore.check_for_update(http), {"tag": "v1.10.0"})

    def test_no_release_and_failure_are_different(self):
        http = FakeHttp({ipcore.RELEASES_API: FakeResponse({}, status=404)})
        self.assertEqual(ipcore.check_for_update(http), {"tag": ""})
        self.assertIsNone(ipcore.check_for_update(FakeHttp({})))


class PublicIpTests(unittest.TestCase):
    def test_first_source_works(self):
        http = FakeHttp({ipcore.IP_ENDPOINTS[0]: FakeResponse({"ip": "8.8.8.8"})})
        self.assertEqual(ipcore.fetch_public_ip(http), "8.8.8.8")
        self.assertEqual(len(http.calls), 1)

    def test_ip_api_answer_uses_query_field(self):
        http = FakeHttp({ipcore.IP_ENDPOINTS[0]: FakeResponse({"query": "5.6.7.8"})})
        self.assertEqual(ipcore.fetch_public_ip(http), "5.6.7.8")

    def test_falls_back_to_next_source(self):
        http = FakeHttp({ipcore.IP_ENDPOINTS[2]: FakeResponse(text="1.2.3.4\n")})
        self.assertEqual(ipcore.fetch_public_ip(http), "1.2.3.4")

    def test_garbage_answer_is_rejected(self):
        http = FakeHttp({url: FakeResponse(text="<html>captive portal</html>")
                         for url in ipcore.IP_ENDPOINTS[1:]})
        self.assertIsNone(ipcore.fetch_public_ip(http))

    def test_offline(self):
        self.assertIsNone(ipcore.fetch_public_ip(FakeHttp({})))

    def test_ipv6_is_accepted(self):
        http = FakeHttp({ipcore.IP_ENDPOINTS[0]: FakeResponse({"ip": "2001:4860:4860::8888"})})
        self.assertEqual(ipcore.fetch_public_ip(http), "2001:4860:4860::8888")


class LocationTests(unittest.TestCase):
    def test_ipwho(self):
        payload = {"success": True, "country": "Germany", "country_code": "de",
                   "city": "Berlin", "connection": {"isp": "Example ISP"},
                   "latitude": 52.52, "longitude": 13.405}
        http = FakeHttp({"https://ipwho.is/1.1.1.1": FakeResponse(payload)})
        self.assertEqual(ipcore.lookup_location("1.1.1.1", http),
                         {"country": "Germany", "code": "DE", "city": "Berlin", "isp": "Example ISP",
                          "lat": 52.52, "lon": 13.405})

    def test_position_from_each_source(self):
        ip_api = ipcore._from_ip_api({"status": "success", "country": "Iran", "countryCode": "IR",
                                      "city": "Tehran", "isp": "X", "lat": 35.69, "lon": 51.42})
        self.assertEqual((ip_api["lat"], ip_api["lon"]), (35.69, 51.42))
        co = ipcore._from_ipapi_co({"country_name": "Iran", "country_code": "IR", "city": "Karaj",
                                    "org": "X", "latitude": "35.83", "longitude": "50.99"})
        self.assertEqual((co["lat"], co["lon"]), (35.83, 50.99))

    def test_missing_or_wrong_position_is_none(self):
        for lat, lon in ((None, None), ("x", 1), (91, 0), (0, 181), (0, 0)):
            self.assertEqual(ipcore._coords(lat, lon), (None, None))

    def test_state_carries_the_position(self):
        loc = {"country": "Iran", "code": "IR", "city": "Tehran", "isp": "X", "lat": 35.69, "lon": 51.42}
        state = ipcore.make_state("1.2.3.4", loc)
        self.assertEqual((state["lat"], state["lon"]), (35.69, 51.42))
        offline = ipcore.make_state()
        self.assertEqual((offline["lat"], offline["lon"]), (None, None))

    def test_fallback_to_second_source(self):
        http = FakeHttp({
            "https://ipwho.is/1.1.1.1": FakeResponse({"success": False}),
            "https://ipapi.co/1.1.1.1/json/": FakeResponse(
                {"country_name": "France", "country_code": "FR", "city": "Paris", "org": "Org"}),
        })
        self.assertEqual(ipcore.lookup_location("1.1.1.1", http)["code"], "FR")

    def test_all_sources_fail(self):
        self.assertIsNone(ipcore.lookup_location("1.1.1.1", FakeHttp({})))

    def test_strange_values_are_cleaned(self):
        payload = {"success": True, "country": "Ger\x00many", "country_code": "../x",
                   "city": "A" * 500, "connection": {}}
        http = FakeHttp({"https://ipwho.is/1.1.1.1": FakeResponse(payload)})
        info = ipcore.lookup_location("1.1.1.1", http)
        self.assertEqual(info["country"], "Germany")
        self.assertEqual(info["code"], "")  # never used to build a file path
        self.assertEqual(len(info["city"]), 60)


class MonitorTests(unittest.TestCase):
    def make(self, ips, location=None):
        """A monitor whose IP answers come from the list `ips` (None = offline)."""
        seen, looked = [], []
        answers = iter(ips)

        def lookup(ip):
            looked.append(ip)
            return location

        mon = ipcore.IPMonitor(seen.append, lambda: 10, fetch_ip=lambda: next(answers), lookup=lookup)
        return mon, seen, looked

    LOC = {"country": "Germany", "code": "DE", "city": "Berlin", "isp": "X"}

    def test_reports_once_and_looks_up_once(self):
        mon, seen, looked = self.make(["1.1.1.1", "1.1.1.1", "1.1.1.1"], self.LOC)
        for _ in range(3):
            mon.poll_once()
        self.assertEqual(len(seen), 1)
        self.assertEqual(looked, ["1.1.1.1"])
        self.assertEqual(seen[0]["country"], "Germany")

    def test_new_ip_triggers_new_lookup(self):
        mon, seen, looked = self.make(["1.1.1.1", "2.2.2.2"], self.LOC)
        mon.poll_once()
        mon.poll_once()
        self.assertEqual(looked, ["1.1.1.1", "2.2.2.2"])
        self.assertEqual(len(seen), 2)

    def test_failed_details_are_retried(self):
        mon, seen, looked = self.make(["1.1.1.1", "1.1.1.1"], None)
        mon.poll_once()
        mon.poll_once()
        self.assertEqual(looked, ["1.1.1.1", "1.1.1.1"])
        self.assertFalse(seen[0]["located"])

    def test_one_failed_check_does_not_show_offline(self):
        mon, seen, _ = self.make(["1.1.1.1", None, "1.1.1.1"], self.LOC)
        for _ in range(3):
            mon.poll_once()
        self.assertEqual([s["online"] for s in seen], [True])

    def test_two_failed_checks_show_offline(self):
        mon, seen, _ = self.make(["1.1.1.1", None, None], self.LOC)
        for _ in range(3):
            mon.poll_once()
        self.assertEqual([s["online"] for s in seen], [True, False])

    def test_offline_at_startup_is_shown_immediately(self):
        mon, seen, _ = self.make([None])
        mon.poll_once()
        self.assertEqual([s["online"] for s in seen], [False])

    def test_force_always_reports(self):
        mon, seen, looked = self.make(["1.1.1.1", "1.1.1.1"], self.LOC)
        mon.poll_once()
        mon.poll_once(force=True)
        self.assertEqual(len(seen), 2)
        self.assertEqual(len(looked), 2)


class MiscTests(unittest.TestCase):
    def test_startup_helpers_are_safe_off_windows(self):
        if not ipcore.IS_WINDOWS:
            self.assertFalse(ipcore.is_startup_enabled())
            self.assertFalse(ipcore.set_startup(True))
            self.assertTrue(ipcore.acquire_single_instance())

    def test_startup_command_is_quoted(self):
        self.assertTrue(ipcore.startup_command().startswith('"'))


class SpeedTests(unittest.TestCase):
    def meter(self, readings, times):
        readings, times = iter(readings), iter(times)
        return ipcore.SpeedMeter(reader=lambda: next(readings), clock=lambda: next(times))

    def test_first_reading_is_zero(self):
        m = self.meter([{"Wi-Fi": (0, 0)}], [0.0])
        self.assertEqual(m.update(), (0.0, 0.0))

    def test_speed_is_bytes_per_second(self):
        m = self.meter([{"Wi-Fi": (0, 0)}, {"Wi-Fi": (2000, 10000)}], [0.0, 2.0])
        m.update()
        down, up = m.update()
        self.assertEqual((down, up), (5000.0, 1000.0))

    def test_loopback_is_ignored(self):
        m = self.meter([{"Loopback Pseudo-Interface 1": (0, 0), "lo": (0, 0), "Wi-Fi": (0, 0)},
                        {"Loopback Pseudo-Interface 1": (9e9, 9e9), "lo": (9e9, 9e9),
                         "Wi-Fi": (100, 300)}], [0.0, 1.0])
        m.update()
        self.assertEqual(m.update(), (300.0, 100.0))

    def test_vpn_traffic_is_not_counted_twice(self):
        m = self.meter([{"Wi-Fi": (0, 0), "VPN": (0, 0)},
                        {"Wi-Fi": (1100, 5200), "VPN": (1000, 5000)}], [0.0, 1.0])
        m.update()
        self.assertEqual(m.update(), (5200.0, 1100.0))

    def test_counter_reset_does_not_go_negative(self):
        m = self.meter([{"Wi-Fi": (5000, 5000)}, {"Wi-Fi": (10, 10)}], [0.0, 1.0])
        m.update()
        self.assertEqual(m.update(), (0.0, 0.0))

    def test_new_adapter_is_skipped_once(self):
        m = self.meter([{"Wi-Fi": (0, 0)}, {"Wi-Fi": (0, 0), "USB": (999, 999)}], [0.0, 1.0])
        m.update()
        self.assertEqual(m.update(), (0.0, 0.0))

    def test_reader_returning_nothing(self):
        m = self.meter([{}, {}], [0.0, 1.0])
        m.update()
        self.assertEqual(m.update(), (0.0, 0.0))

    def test_format(self):
        self.assertEqual(ipcore.format_speed(0), "0 B/s")
        self.assertEqual(ipcore.format_speed(999), "999 B/s")
        self.assertEqual(ipcore.format_speed(1536), "1.5 KB/s")
        self.assertEqual(ipcore.format_speed(5 * 1024 ** 2), "5.00 MB/s")
        self.assertEqual(ipcore.format_speed(-5), "0 B/s")

    def test_real_counters_are_readable(self):
        self.assertIsInstance(ipcore.read_counters(), dict)


class NewSettingsTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "settings.json")

    def tearDown(self):
        self.dir.cleanup()

    def test_defaults(self):
        s = ipcore.Settings(self.path).load()
        self.assertTrue(s.get("show_speed"))
        self.assertTrue(s.get("show_usage"))
        self.assertTrue(s.get("show_weather"))
        self.assertEqual(s.get("city_name"), "")
        self.assertIsNone(s.get("city_lat"))

    def test_city_roundtrip(self):
        s = ipcore.Settings(self.path)
        s.set("city_name", "\u062a\u0647\u0631\u0627\u0646")
        s.set("city_lat", 35.69)
        s.set("city_lon", 51.42)
        again = ipcore.Settings(self.path).load()
        self.assertEqual(again.get("city_name"), "\u062a\u0647\u0631\u0627\u0646")
        self.assertEqual((again.get("city_lat"), again.get("city_lon")), (35.69, 51.42))

    def test_bad_city_values(self):
        with open(self.path, "w") as fh:
            json.dump({"city_lat": 999, "city_lon": "abc", "city_name": 5, "show_speed": "no"}, fh)
        s = ipcore.Settings(self.path).load()
        self.assertIsNone(s.get("city_lat"))
        self.assertIsNone(s.get("city_lon"))
        self.assertEqual(s.get("city_name"), "")
        self.assertTrue(s.get("show_speed"))


class UsageTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "usage.json")
        self.day = ["2026-11-15"]
        self.now = [0.0]

    def tearDown(self):
        self.dir.cleanup()

    def make(self):
        return ipcore.DailyUsage(self.path, today=lambda: self.day[0], clock=lambda: self.now[0])

    def test_adds_up(self):
        u = self.make()
        u.add(1000, 10)
        u.add(500, 5)
        self.assertEqual((u.down, u.up), (1500, 15))

    def test_survives_restart_same_day(self):
        u = self.make()
        u.add(1000, 10)
        u.save(force=True)
        again = self.make()
        self.assertEqual((again.down, again.up), (1000, 10))

    def test_new_day_starts_at_zero(self):
        u = self.make()
        u.add(1000, 10)
        u.save(force=True)
        self.day[0] = "2026-11-16"
        self.assertEqual((self.make().down, self.make().up), (0, 0))
        u.add(7, 1)
        self.assertEqual((u.down, u.up), (7, 1))

    def test_save_is_throttled(self):
        u = self.make()
        u.add(1, 1)
        u.save()
        self.assertFalse(os.path.exists(self.path))
        self.now[0] = 31
        u.save()
        self.assertTrue(os.path.exists(self.path))

    def test_negative_and_corrupt_input(self):
        u = self.make()
        u.add(-5, -5)
        self.assertEqual((u.down, u.up), (0, 0))
        with open(self.path, "w") as fh:
            fh.write("garbage")
        self.assertEqual(self.make().down, 0)

    def test_speed_meter_reports_bytes_for_the_total(self):
        readings = iter([{"Wi-Fi": (0, 0), "VPN": (0, 0)}, {"Wi-Fi": (110, 520), "VPN": (100, 500)}])
        times = iter([0.0, 2.0])
        m = ipcore.SpeedMeter(reader=lambda: next(readings), clock=lambda: next(times))
        m.update()
        down, up = m.update()
        self.assertEqual((m.down_bytes, m.up_bytes), (520, 110))
        self.assertEqual((down, up), (260.0, 55.0))

    def test_format_bytes(self):
        self.assertEqual(ipcore.format_bytes(0), "0 B")
        self.assertEqual(ipcore.format_bytes(1536), "1.5 KB")
        self.assertEqual(ipcore.format_bytes(5 * 1024 ** 2), "5.0 MB")
        self.assertEqual(ipcore.format_bytes(3 * 1024 ** 3), "3.00 GB")


class WeatherTests(unittest.TestCase):
    CITY = {"results": [
        {"name": "Tehran", "latitude": 35.69, "longitude": 51.42, "country": "Iran", "admin1": "Tehran"},
        {"name": "Bad", "latitude": 999, "longitude": 0},
        {"name": "", "latitude": 1, "longitude": 1},
        {"latitude": 1},
    ]}

    def test_search_keeps_only_valid_results(self):
        http = FakeHttp({ipcore.GEOCODE_URL: FakeResponse(self.CITY)})
        found = ipcore.search_cities("Tehran", http)
        self.assertEqual(len(found), 1)
        self.assertEqual((found[0]["name"], found[0]["lat"], found[0]["lon"]), ("Tehran", 35.69, 51.42))

    def test_search_no_match_vs_failure(self):
        self.assertEqual(ipcore.search_cities("zzzz", FakeHttp({ipcore.GEOCODE_URL: FakeResponse({})})), [])
        self.assertIsNone(ipcore.search_cities("Tehran", FakeHttp({})))
        self.assertEqual(ipcore.search_cities(" a ", FakeHttp({})), [])

    def test_weather(self):
        payload = {"current": {"temperature_2m": 12.6, "weather_code": 3}}
        http = FakeHttp({ipcore.FORECAST_URL: FakeResponse(payload)})
        self.assertEqual(ipcore.fetch_weather(35.69, 51.42, http), {"temp": 12.6, "code": 3})

    def test_weather_failures(self):
        self.assertIsNone(ipcore.fetch_weather(1, 1, FakeHttp({})))
        self.assertIsNone(ipcore.fetch_weather(1, 1, FakeHttp({ipcore.FORECAST_URL: FakeResponse({"x": 1})})))

    def test_symbols_and_temperature(self):
        self.assertEqual(ipcore.weather_symbol(0), "\u2600")
        self.assertEqual(ipcore.weather_symbol(63), "\u2602")
        self.assertEqual(ipcore.weather_symbol(75), "\u2744")
        self.assertEqual(ipcore.weather_symbol(95), "\u26A1")
        self.assertEqual(ipcore.weather_symbol(12345), "\u2601")
        self.assertEqual(ipcore.format_temp(12.6), "13\u00B0C")
        self.assertEqual(ipcore.format_temp(-0.4), "0\u00B0C")
        self.assertEqual(ipcore.format_temp(-7.2), "-7\u00B0C")

    def test_monitor(self):
        seen = []
        result = {"temp": 1.0, "code": 0}
        m = ipcore.WeatherMonitor(seen.append, lambda: (1.0, 2.0), fetch=lambda lat, lon: result)
        self.assertTrue(m.poll_once())
        self.assertEqual(seen, [result])
        failing = ipcore.WeatherMonitor(seen.append, lambda: (1.0, 2.0), fetch=lambda lat, lon: None)
        self.assertFalse(failing.poll_once())
        nothing = ipcore.WeatherMonitor(seen.append, lambda: None)
        self.assertTrue(nothing.poll_once())
        self.assertEqual(seen[-1], None)


class DollarRateTests(unittest.TestCase):
    def test_newest_line_wins_and_persian_digits_work(self):
        html = "<p>\u062f\u0644\u0627\u0631: 98,500 \u062a\u0648\u0645\u0627\u0646</p><p>\u062f\u0644\u0627\u0631: \u06f9\u06f9\u066c\u06f1\u06f0\u06f0 \u062a\u0648\u0645\u0627\u0646</p>"
        self.assertEqual(ipcore.parse_dollar_rate(html), "99100")

    def test_number_after_the_word_is_the_fallback(self):
        self.assertEqual(ipcore.parse_dollar_rate("<b>\u0642\u06cc\u0645\u062a \u062f\u0644\u0627\u0631 \u0627\u0645\u0631\u0648\u0632 105,200</b>"), "105200")

    def test_nothing_or_nonsense(self):
        self.assertIsNone(ipcore.parse_dollar_rate("hello"))
        self.assertIsNone(ipcore.parse_dollar_rate(""))
        self.assertIsNone(ipcore.parse_dollar_rate(None))
        self.assertIsNone(ipcore.parse_dollar_rate("\u062f\u0644\u0627\u0631: 12,3"))

    def test_fetch(self):
        page = "\u062f\u0644\u0627\u0631: 98,500 \u062a\u0648\u0645\u0627\u0646"
        http = FakeHttp({ipcore.RATE_URL: FakeResponse(text=page)})
        self.assertEqual(ipcore.fetch_dollar_rate(http), "98500")
        self.assertIsNone(ipcore.fetch_dollar_rate(FakeHttp({})))
        self.assertIsNone(ipcore.fetch_dollar_rate(FakeHttp({ipcore.RATE_URL: FakeResponse(status=500)})))

    def test_format(self):
        self.assertEqual(ipcore.format_rate("98500"), "$ 98,500")
        self.assertEqual(ipcore.format_rate(None), "$ ...")
        self.assertEqual(ipcore.format_rate("abc"), "$ ...")

    def test_monitor(self):
        seen = []
        ok = ipcore.RateMonitor(seen.append, fetch=lambda: "98500")
        self.assertTrue(ok.poll_once())
        self.assertEqual(seen, ["98500"])
        failing = ipcore.RateMonitor(seen.append, fetch=lambda: None)
        self.assertFalse(failing.poll_once())
        self.assertEqual(seen, ["98500"])          # a failed read tells nobody: the old value stays
        off = ipcore.RateMonitor(seen.append, enabled_fn=lambda: False, fetch=lambda: "1")
        self.assertTrue(off.poll_once())
        self.assertEqual(seen, ["98500"])


class RateFallbackTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = os.path.join(self.dir.name, "rate.json")

    def test_json_wrapper_does_not_matter(self):
        flat = [{"assetId": "eur", "price": 311690}, {"assetId": "usd", "price": 284200}]
        wrapped = {"data": {"rates": flat}, "meta": {"source": "live"}}
        self.assertEqual(ipcore.parse_rate_json(flat), "284200")
        self.assertEqual(ipcore.parse_rate_json(wrapped), "284200")
        self.assertEqual(ipcore.parse_rate_json([{"assetId": "usd", "price": "284,200"}]), "284200")

    def test_json_nonsense(self):
        self.assertIsNone(ipcore.parse_rate_json({"data": []}))
        self.assertIsNone(ipcore.parse_rate_json([{"assetId": "eur", "price": 1000}]))
        self.assertIsNone(ipcore.parse_rate_json([{"assetId": "usd", "price": "abc"}]))
        self.assertIsNone(ipcore.parse_rate_json([{"assetId": "usd", "price": 12}]))
        self.assertIsNone(ipcore.parse_rate_json(None))

    def test_api_needs_a_key_and_sends_it(self):
        http = FakeHttp({ipcore.RATE_API_URL: FakeResponse(payload=[{"assetId": "usd", "price": 284200}])})
        self.assertIsNone(ipcore.fetch_dollar_rate_api("", http))
        self.assertEqual(http.calls, [])                       # no key: nothing is even asked
        self.assertEqual(ipcore.fetch_dollar_rate_api("k", http), "284200")
        self.assertIsNone(ipcore.fetch_dollar_rate_api("k", FakeHttp({})))
        self.assertIsNone(ipcore.fetch_dollar_rate_api("k", FakeHttp({ipcore.RATE_API_URL: FakeResponse(status=403)})))

    def test_fallback_runs_only_when_the_main_source_fails(self):
        seen, saved = [], []
        both = ipcore.RateMonitor(seen.append, fetch=lambda: "98500", fallback=lambda: "1", save=saved.append)
        self.assertTrue(both.poll_once())
        self.assertEqual((seen, saved), (["98500"], ["98500"]))
        backup = ipcore.RateMonitor(seen.append, fetch=lambda: None, fallback=lambda: "99000", save=saved.append)
        self.assertTrue(backup.poll_once())
        self.assertEqual((seen[-1], saved[-1]), ("99000", "99000"))
        none = ipcore.RateMonitor(seen.append, fetch=lambda: None, fallback=lambda: None, save=saved.append)
        self.assertFalse(none.poll_once())
        self.assertEqual(len(seen), 2)

    def test_cache_round_trip_and_age(self):
        self.assertIsNone(ipcore.load_cached_rate(self.path))
        ipcore.save_cached_rate("98500", self.path, now=lambda: 1000.0)
        self.assertEqual(ipcore.load_cached_rate(self.path, now=lambda: 1000.0 + 3600), "98500")
        self.assertIsNone(ipcore.load_cached_rate(self.path, now=lambda: 1000.0 + 3 * 24 * 3600))   # too old
        self.assertIsNone(ipcore.load_cached_rate(self.path, now=lambda: 500.0))                     # clock went back

    def test_broken_cache_file_is_ignored(self):
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write("{not json")
        self.assertIsNone(ipcore.load_cached_rate(self.path))
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump({"digits": "abc", "time": 1}, fh)
        self.assertIsNone(ipcore.load_cached_rate(self.path, now=lambda: 2.0))

    def test_key_setting_is_a_clean_string(self):
        self.assertEqual(ipcore._validate("rate_api_key", " abc\n"), "abc")
        self.assertEqual(ipcore._validate("rate_api_key", 5), "")
        self.assertEqual(ipcore.DEFAULT_SETTINGS["rate_api_key"], "")


class FirstRunDefaultTests(unittest.TestCase):
    def test_new_install_shows_everything_by_itself(self):
        d = ipcore.DEFAULT_SETTINGS
        for key in ("show_strip", "strip_embed", "show_speed", "show_usage", "show_weather",
                    "show_rate", "city_auto"):
            self.assertTrue(d[key], key)
        self.assertIsNone(d["city_lat"])

    def test_new_switches_are_validated(self):
        self.assertTrue(ipcore._validate("show_rate", "yes"))      # not a bool: back to the default
        self.assertFalse(ipcore._validate("city_auto", False))


if __name__ == "__main__":
    unittest.main()
