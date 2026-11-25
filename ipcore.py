"""Core (non-graphical) logic of Mostafa-MultiWidget.

Kept free of any tkinter / tray imports so it can be tested anywhere.
"""
import datetime
import ipaddress
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from logging.handlers import RotatingFileHandler

import requests

__version__ = "1.1.1"
__author__ = "Mostafa Mandegari"

APP_NAME = "Mostafa MultiWidget"
LEGACY_STARTUP_NAMES = ("MyIP Widget", "Mostafa-IP-Widget")  # older versions used this name in the Windows start-up list
APP_DIR_NAME = "MyIPWidget"
REQUEST_TIMEOUT = 6
OFFLINE_AFTER_FAILURES = 2  # consecutive failed checks before showing "No Internet"

HEADERS = {"User-Agent": f"Mostafa-MultiWidget/{__version__}", "Connection": "close"}  # no kept-open sockets

log = logging.getLogger("myip")


# --------------------------------------------------------------------------
# Files / settings
# --------------------------------------------------------------------------
def app_data_dir():
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    path = os.path.join(base, APP_DIR_NAME)
    try:
        os.makedirs(path, exist_ok=True)
        return path
    except OSError:
        fallback = os.path.join(tempfile.gettempdir(), APP_DIR_NAME)
        os.makedirs(fallback, exist_ok=True)
        return fallback


def setup_logging():
    """Write a small rotating log file (the app has no console window)."""
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    try:
        handler = RotatingFileHandler(
            os.path.join(app_data_dir(), "myip-widget.log"),
            maxBytes=200_000, backupCount=1, encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(handler)
    except OSError:
        log.addHandler(logging.NullHandler())
    return log


DEFAULT_SETTINGS = {
    "x": None,
    "y": None,
    "opacity": 0.7,
    "interval": 10,
    "show_details": True,
    "pinned": False,   # False: pop-up from the tray icon; True: stays on the desktop
    "show_speed": True,
    "show_usage": True,     # today's downloaded / uploaded volume
    "show_weather": True,   # only shown once a city has been chosen
    "show_strip": True,     # the small always-visible bar beside the clock
    "strip_embed": False,   # Windows 10: build the bar into the taskbar itself (opt-in)
    "strip_x": None,
    "strip_y": None,
    "city_name": "",
    "city_lat": None,
    "city_lon": None,
}


def _validate(key, value):
    """Return a safe value for a setting, or the default if it is invalid."""
    default = DEFAULT_SETTINGS[key]
    try:
        if key in ("x", "y", "strip_x", "strip_y"):
            if value is None:
                return None
            if isinstance(value, bool):
                return default
            return int(value)
        if key == "opacity":
            return min(1.0, max(0.2, float(value)))
        if key == "interval":
            return min(300, max(5, int(value)))
        if key in ("show_details", "pinned", "show_speed", "show_usage", "show_weather", "show_strip", "strip_embed"):
            return value if isinstance(value, bool) else default
        if key == "city_name":
            return _clean(value, 60) if isinstance(value, str) else default
        if key in ("city_lat", "city_lon"):
            if value is None or isinstance(value, bool):
                return None
            number = float(value)
            limit = 90 if key == "city_lat" else 180
            return number if -limit <= number <= limit else None
    except (TypeError, ValueError):
        pass
    return default


class Settings:
    def __init__(self, path=None):
        self.path = path or os.path.join(app_data_dir(), "settings.json")
        self.data = dict(DEFAULT_SETTINGS)

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except (OSError, ValueError):
            return self
        if isinstance(raw, dict):
            for key in DEFAULT_SETTINGS:
                if key in raw:
                    self.data[key] = _validate(key, raw[key])
        return self

    def save(self):
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh, indent=2)
            os.replace(tmp, self.path)
        except OSError:
            log.exception("Could not save settings")

    def get(self, key):
        return self.data[key]

    def set(self, key, value, save=True):
        self.data[key] = _validate(key, value)
        if save:
            self.save()


# --------------------------------------------------------------------------
# Network lookups
# --------------------------------------------------------------------------
# Step 1: a cheap request that only returns the public IP (tried in order).
# ip-api.com comes first: it is the same service the original program used, and it answers over
# plain http. With a VPN / proxy that routes some sites differently from others, https services
# may see a different address than the one you actually browse with.
IP_ENDPOINTS = [
    "http://ip-api.com/json/?fields=query",
    "https://api.ipify.org?format=json",
    "https://ipv4.icanhazip.com",
    "https://ifconfig.me/ip",
]

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def _clean(value, limit=60):
    if value is None:
        return ""
    return _CONTROL_CHARS.sub("", str(value)).strip()[:limit]


def _clean_code(value):
    value = _clean(value, 8)
    return value.upper() if re.fullmatch(r"[A-Za-z]{2}", value) else ""


def _parse_ip(text):
    text = (text or "").strip()
    return str(ipaddress.ip_address(text))  # raises ValueError if not an IP


def fetch_public_ip(http=requests, endpoints=None):
    """Return the current public IP as a string, or None if it cannot be found."""
    for url in endpoints or IP_ENDPOINTS:
        try:
            resp = http.get(url, timeout=REQUEST_TIMEOUT, headers=HEADERS)
            resp.raise_for_status()
            if "json" in url:
                data = resp.json()
                return _parse_ip(data.get("ip") or data.get("query") or "")
            return _parse_ip(resp.text)
        except Exception as exc:  # network errors, bad data, ...
            log.debug("IP source %s failed: %s", url, exc)
    return None


# Step 2: details (country, city, provider) - only asked when the IP changes.
def _from_ipwho(d):
    if not d.get("success"):
        raise ValueError("ipwho.is returned an error")
    conn = d.get("connection") or {}
    return {
        "country": _clean(d.get("country")),
        "code": _clean_code(d.get("country_code")),
        "city": _clean(d.get("city")),
        "isp": _clean(conn.get("isp") or conn.get("org")),
    }


def _from_ipapi_co(d):
    if d.get("error"):
        raise ValueError("ipapi.co returned an error")
    return {
        "country": _clean(d.get("country_name")),
        "code": _clean_code(d.get("country_code")),
        "city": _clean(d.get("city")),
        "isp": _clean(d.get("org")),
    }


def _from_ip_api(d):
    if d.get("status") != "success":
        raise ValueError("ip-api returned an error")
    return {
        "country": _clean(d.get("country")),
        "code": _clean_code(d.get("countryCode")),
        "city": _clean(d.get("city")),
        "isp": _clean(d.get("isp")),
    }


DETAIL_SOURCES = [
    ("http://ip-api.com/json/{ip}", _from_ip_api),  # first: same service as the original program
    ("https://ipwho.is/{ip}", _from_ipwho),
    ("https://ipapi.co/{ip}/json/", _from_ipapi_co),
]


def lookup_location(ip, http=requests, sources=None):
    """Return {'country','code','city','isp'} for an IP, or None if all sources fail."""
    for template, parser in sources or DETAIL_SOURCES:
        try:
            resp = http.get(template.format(ip=ip), timeout=REQUEST_TIMEOUT, headers=HEADERS)
            resp.raise_for_status()
            info = parser(resp.json())
            if info["country"] or info["code"]:
                return info
        except Exception as exc:
            log.debug("Details source %s failed: %s", template, exc)
    return None


# --------------------------------------------------------------------------
# Background monitor
# --------------------------------------------------------------------------
def make_state(ip=None, location=None):
    """The dictionary the user interface displays."""
    if not ip:
        return {"online": False, "ip": "", "country": "", "code": "",
                "city": "", "isp": "", "located": False}
    loc = location or {}
    return {
        "online": True,
        "ip": ip,
        "country": loc.get("country", ""),
        "code": loc.get("code", ""),
        "city": loc.get("city", ""),
        "isp": loc.get("isp", ""),
        "located": bool(location),
    }


class IPMonitor(threading.Thread):
    """Checks the public IP regularly and reports changes through on_update(state)."""

    def __init__(self, on_update, interval_fn, fetch_ip=fetch_public_ip, lookup=lookup_location):
        super().__init__(daemon=True, name="ip-monitor")
        self._on_update = on_update
        self._interval_fn = interval_fn
        self._fetch_ip = fetch_ip
        self._lookup = lookup
        self._stop_evt = threading.Event()
        self._wake = threading.Event()
        self._force = False
        self._ip = None
        self._location = None
        self._failures = 0
        self._last_state = None

    # -- control ----------------------------------------------------------
    def refresh(self):
        self._force = True
        self._wake.set()

    def stop(self):
        self._stop_evt.set()
        self._wake.set()

    # -- work -------------------------------------------------------------
    def poll_once(self, force=False):
        ip = self._fetch_ip()
        if ip is None:
            self._failures += 1
            if self._failures >= OFFLINE_AFTER_FAILURES or self._last_state is None or force:
                self._ip = None
                self._location = None
                self._emit(make_state(), force)
            return
        self._failures = 0
        if force or ip != self._ip or self._location is None:
            self._location = self._lookup(ip)
            self._ip = ip
        self._emit(make_state(ip, self._location), force)

    def _emit(self, state, force=False):
        if force or state != self._last_state:
            self._last_state = state
            self._on_update(state)

    def run(self):
        while not self._stop_evt.is_set():
            force, self._force = self._force, False
            try:
                self.poll_once(force)
            except Exception:
                log.exception("Unexpected error while checking the IP")
            try:
                wait = max(5, int(self._interval_fn()))
            except Exception:
                wait = 10
            self._wake.wait(timeout=wait)
            self._wake.clear()


# --------------------------------------------------------------------------
# About / updates
# --------------------------------------------------------------------------
REPO_URL = "https://github.com/coxvpn/Mostafa-MultiWidget"
RELEASES_PAGE = REPO_URL + "/releases/latest"
RELEASES_API = "https://api.github.com/repos/coxvpn/Mostafa-MultiWidget/releases/latest"


def version_tuple(text):
    """'v1.2.3' -> (1, 2, 3); None if there is no number in it."""
    numbers = re.findall(r"\d+", str(text or ""))
    return tuple(int(n) for n in numbers[:3]) if numbers else None


def is_newer(latest, current):
    a, b = version_tuple(latest), version_tuple(current)
    return bool(a and b and a > b)


def check_for_update(http=requests):
    """Asks GitHub for the newest release.

    Returns {'tag': '1.2.0'}; {'tag': ''} when no release exists yet; None if it could not be asked.
    """
    try:
        resp = http.get(RELEASES_API, timeout=REQUEST_TIMEOUT,
                        headers={**HEADERS, "Accept": "application/vnd.github+json"})
        if getattr(resp, "status_code", getattr(resp, "status", 200)) == 404:
            return {"tag": ""}
        resp.raise_for_status()
        return {"tag": _clean(resp.json().get("tag_name"), 40)}
    except Exception as exc:
        log.debug("Update check failed: %s", exc)
        return None


# --------------------------------------------------------------------------
# Live network speed
# --------------------------------------------------------------------------
_LOOPBACK = re.compile(r"loopback|^lo\d*$", re.IGNORECASE)


def format_speed(bytes_per_second):
    """1536 -> '1.5 KB/s'."""
    value = max(0.0, float(bytes_per_second))
    if value < 1024:
        return f"{int(value)} B/s"
    if value < 1024 ** 2:
        return f"{value / 1024:.1f} KB/s"
    if value < 1024 ** 3:
        return f"{value / 1024 ** 2:.2f} MB/s"
    return f"{value / 1024 ** 3:.2f} GB/s"


def read_counters():
    """{interface: (bytes_sent, bytes_received)} - empty if it cannot be read."""
    try:
        import psutil
        return {name: (c.bytes_sent, c.bytes_recv)
                for name, c in psutil.net_io_counters(pernic=True).items()}
    except Exception:
        return {}


class SpeedMeter:
    """Current download / upload speed, worked out from the adapters' byte counters.

    With a VPN the same traffic passes through two adapters (the real one and the
    tunnel). Adding them would show double the real speed, so only the busiest
    adapter is used for each direction.
    """

    def __init__(self, reader=read_counters, clock=time.monotonic):
        self._reader = reader
        self._clock = clock
        self._prev = None
        self._prev_time = 0.0
        self.down_bytes = 0   # bytes moved during the last interval (for the daily total)
        self.up_bytes = 0

    def update(self):
        """Call about once a second. Returns (download, upload) in bytes per second."""
        now = self._clock()
        current = {name: values for name, values in self._reader().items()
                   if not _LOOPBACK.search(name)}
        down_b = up_b = 0
        seconds = 0.0
        if self._prev is not None and now > self._prev_time:
            seconds = now - self._prev_time
            for name, (sent, received) in current.items():
                before = self._prev.get(name)
                if before is None:
                    continue
                up_b = max(up_b, max(0, sent - before[0]))
                down_b = max(down_b, max(0, received - before[1]))
        self._prev, self._prev_time = current, now
        self.down_bytes, self.up_bytes = down_b, up_b
        if seconds <= 0:
            return 0.0, 0.0
        return down_b / seconds, up_b / seconds


def format_bytes(count):
    """1536 -> '1.5 KB'."""
    value = max(0.0, float(count))
    if value < 1024:
        return f"{int(value)} B"
    if value < 1024 ** 2:
        return f"{value / 1024:.1f} KB"
    if value < 1024 ** 3:
        return f"{value / 1024 ** 2:.1f} MB"
    return f"{value / 1024 ** 3:.2f} GB"


class DailyUsage:
    """Downloaded / uploaded bytes for today, kept in a small file so a restart does not lose them.

    It counts while the program is running; the total starts again at zero after midnight.
    """

    SAVE_EVERY = 30  # seconds

    def __init__(self, path=None, today=None, clock=time.monotonic):
        self.path = path or os.path.join(app_data_dir(), "usage.json")
        self._today = today or (lambda: datetime.date.today().isoformat())
        self._clock = clock
        self.date = self._today()
        self.down = 0
        self.up = 0
        self._dirty = False
        self._last_save = clock()
        self._load()

    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            if isinstance(raw, dict) and raw.get("date") == self.date:
                self.down = max(0, int(raw.get("down", 0)))
                self.up = max(0, int(raw.get("up", 0)))
        except (OSError, ValueError, TypeError):
            pass

    def add(self, down_bytes, up_bytes):
        day = self._today()
        if day != self.date:
            self.date, self.down, self.up = day, 0, 0
        if down_bytes or up_bytes:
            self.down += max(0, int(down_bytes))
            self.up += max(0, int(up_bytes))
            self._dirty = True

    def save(self, force=False):
        if not self._dirty:
            return
        if not force and self._clock() - self._last_save < self.SAVE_EVERY:
            return
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump({"date": self.date, "down": self.down, "up": self.up}, fh)
            os.replace(tmp, self.path)
            self._dirty = False
            self._last_save = self._clock()
        except OSError:
            log.exception("Could not save the daily usage")


# --------------------------------------------------------------------------
# Weather (Open-Meteo: free, no key) - for a city the user chooses
# --------------------------------------------------------------------------
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


def search_cities(query, http=requests, limit=8, language="fa"):
    """Cities matching a name: a list (maybe empty), or None if the search could not be made."""
    query = (query or "").strip()
    if len(query) < 2:
        return []
    try:
        resp = http.get(GEOCODE_URL, timeout=REQUEST_TIMEOUT, headers=HEADERS,
                        params={"name": query, "count": limit, "language": language, "format": "json"})
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        log.debug("City search failed: %s", exc)
        return None
    found = []
    for item in (data.get("results") or []) if isinstance(data, dict) else []:
        try:
            lat, lon = float(item["latitude"]), float(item["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        name = _clean(item.get("name"), 40)
        if not name or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        found.append({"name": name, "region": _clean(item.get("admin1"), 40),
                      "country": _clean(item.get("country"), 40), "lat": lat, "lon": lon})
    return found


def fetch_weather(lat, lon, http=requests):
    """{'temp': degrees Celsius, 'code': WMO weather code} or None."""
    try:
        resp = http.get(FORECAST_URL, timeout=REQUEST_TIMEOUT, headers=HEADERS,
                        params={"latitude": f"{float(lat):.4f}", "longitude": f"{float(lon):.4f}",
                                "current": "temperature_2m,weather_code", "timezone": "auto"})
        resp.raise_for_status()
        current = resp.json()["current"]
        return {"temp": float(current["temperature_2m"]), "code": int(current["weather_code"])}
    except Exception as exc:
        log.debug("Weather lookup failed: %s", exc)
        return None


def weather_symbol(code):
    """A simple symbol for a WMO weather code (drawn by Segoe UI Symbol on Windows)."""
    if code == 0:
        return "\u2600"            # sun
    if code in (1, 2):
        return "\u26C5"            # sun behind cloud
    if code == 3:
        return "\u2601"            # cloud
    if code in (45, 48):
        return "\u224B"            # fog
    if code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82):
        return "\u2602"            # rain (umbrella)
    if code in (71, 73, 75, 77, 85, 86):
        return "\u2744"            # snow
    if code in (95, 96, 99):
        return "\u26A1"            # thunderstorm
    return "\u2601"


def format_temp(celsius):
    return f"{int(round(celsius))}\u00B0C"


class WeatherMonitor(threading.Thread):
    """Looks up the weather of the chosen city now and then; reports through on_update(result)."""

    def __init__(self, on_update, location_fn, fetch=fetch_weather, interval=1800, retry=120):
        super().__init__(daemon=True, name="weather-monitor")
        self._on_update = on_update
        self._location_fn = location_fn
        self._fetch = fetch
        self._interval = interval
        self._retry = retry
        self._stop_evt = threading.Event()
        self._wake = threading.Event()

    def refresh(self):
        self._wake.set()

    def stop(self):
        self._stop_evt.set()
        self._wake.set()

    def poll_once(self):
        """Returns True when no retry is needed soon."""
        location = self._location_fn()
        if not location:
            self._on_update(None)
            return True
        result = self._fetch(*location)
        self._on_update(result)
        return result is not None

    def run(self):
        while not self._stop_evt.is_set():
            try:
                ok = self.poll_once()
            except Exception:
                log.exception("Unexpected error while checking the weather")
                ok = False
            self._wake.wait(timeout=self._interval if ok else self._retry)
            self._wake.clear()


# --------------------------------------------------------------------------
# Windows helpers (safe no-ops elsewhere)
# --------------------------------------------------------------------------
IS_WINDOWS = sys.platform == "win32"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_mutex_handle = None


def system_is_dark():
    if not IS_WINDOWS:
        return False
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            return winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
    except OSError:
        return False


def startup_command():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    return f'"{sys.executable}" "{os.path.abspath(sys.argv[0])}"'


def is_startup_enabled():
    if not IS_WINDOWS:
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            for name in (APP_NAME,) + LEGACY_STARTUP_NAMES:
                try:
                    winreg.QueryValueEx(key, name)
                    return True
                except FileNotFoundError:
                    pass
            return False
    except OSError:
        return False


def set_startup(enabled):
    """Turn 'start with Windows' on or off. Returns True on success."""
    if not IS_WINDOWS:
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            for old in LEGACY_STARTUP_NAMES:   # no double start-up entry after the rename
                try:
                    winreg.DeleteValue(key, old)
                except FileNotFoundError:
                    pass
            if enabled:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, startup_command())
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        log.exception("Could not change the startup setting")
        return False


def acquire_single_instance():
    """Return False if another copy of the widget is already running."""
    global _mutex_handle
    if not IS_WINDOWS:
        return True
    import ctypes
    _mutex_handle = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\MyIPWidgetSingleInstance")
    return ctypes.windll.kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


def copy_to_clipboard(text):
    """Copy text with Windows' own 'clip' tool so it stays after the app quits."""
    if not IS_WINDOWS:
        return False
    try:
        subprocess.run(
            ["clip"], input=text.encode("ascii", "ignore"), check=True,
            creationflags=0x08000000,  # CREATE_NO_WINDOW
            timeout=5,
        )
        return True
    except Exception:
        return False
