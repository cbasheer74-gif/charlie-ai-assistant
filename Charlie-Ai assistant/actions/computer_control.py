#computer_control.py
import io
import json
import platform
import re
import string
import subprocess
import sys
from typing import Any

if platform.system() == "Windows":
    _WIN_HIDE: dict = {"creationflags": subprocess.CREATE_NO_WINDOW}
else:
    _WIN_HIDE: dict = {}
import time
import random
from pathlib import Path

from core import confirm

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE    = 0.05
    _PYAUTOGUI = True
except ImportError:
    _PYAUTOGUI = False

try:
    import pyperclip
    _PYPERCLIP = True
except ImportError:
    _PYPERCLIP = False

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


_BASE         = _base_dir()
_CONFIG_PATH  = _BASE / "config" / "api_keys.json"

def _load_config() -> dict:
    try:
        return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _platform_os() -> str:
    return {"Windows": "windows", "Darwin": "mac", "Linux": "linux"}.get(
        platform.system(), "linux"
    )

def _get_os() -> str:
    return _load_config().get("os_system", _platform_os()).lower()


def _get_api_key() -> str:
    return _load_config().get("gemini_api_key", "")

_SAFE_SCREENSHOT_ROOTS = (
    Path.home(),
)

_MAX_TEXT_CHARS = 50_000
_MAX_WINDOW_RESULTS = 20
_MAX_WINDOW_WAIT_SECONDS = 30.0

def _safe_screenshot_path(requested: str | None) -> Path:
    fallback = Path.home() / "Desktop" / "charlie_screenshot.png"
    if not requested:
        return fallback
    try:
        p = Path(requested).expanduser().resolve()
        for root in _SAFE_SCREENSHOT_ROOTS:
            if p.is_relative_to(root.resolve()):
                p.parent.mkdir(parents=True, exist_ok=True)
                return p
    except Exception:
        pass
    return fallback

def _require_pyautogui():
    if not _PYAUTOGUI:
        raise RuntimeError("PyAutoGUI not installed. Run: pip install pyautogui")


def _screen_bounds() -> tuple[int, int, int, int]:
    """Return virtual-desktop bounds, including secondary monitors on Windows."""
    _require_pyautogui()
    if _get_os() == "windows":
        try:
            import ctypes

            user32 = ctypes.windll.user32
            # SM_X/YVIRTUALSCREEN, SM_CX/CYVIRTUALSCREEN.
            left = int(user32.GetSystemMetrics(76))
            top = int(user32.GetSystemMetrics(77))
            width = int(user32.GetSystemMetrics(78))
            height = int(user32.GetSystemMetrics(79))
            if width > 0 and height > 0:
                return left, top, width, height
        except Exception:
            pass

    width, height = pyautogui.size()
    return 0, 0, int(width), int(height)


def _parse_screen_point(x: Any, y: Any, *, allow_current: bool = False) -> tuple[tuple[int, int] | None, str]:
    """Validate a coordinate before moving or clicking.

    A missing coordinate used to silently mean ``(0, 0)`` for move/drag, or
    "click wherever the cursor already is" for click.  That is a bad failure
    mode for an assistant, particularly after a model returned incomplete tool
    arguments.  Current-position clicks remain available only when *both*
    coordinates were intentionally omitted.
    """
    if x is None and y is None and allow_current:
        return None, ""
    if x is None or y is None:
        return None, "Both x and y coordinates are required."
    if isinstance(x, bool) or isinstance(y, bool):
        return None, "Coordinates must be integer screen positions."
    try:
        px, py = int(x), int(y)
    except (TypeError, ValueError):
        return None, "Coordinates must be integer screen positions."

    try:
        left, top, width, height = _screen_bounds()
    except Exception as exc:
        return None, f"Could not read screen bounds: {exc}"
    if not (left <= px < left + width and top <= py < top + height):
        return (None,
                f"Coordinates ({px}, {py}) are outside the visible desktop "
                f"({left},{top}) to ({left + width - 1},{top + height - 1}).")
    return (px, py), ""


def _validated_text(value: Any) -> tuple[str, str]:
    if not isinstance(value, str):
        return "", "Text must be a string."
    if not value:
        return "", "No text was provided."
    if len(value) > _MAX_TEXT_CHARS:
        return "", f"Text is too long ({len(value):,} characters; limit is {_MAX_TEXT_CHARS:,})."
    return value, ""


def _validated_key(value: Any) -> tuple[str, str]:
    if not isinstance(value, str) or not value.strip():
        return "", "A key name is required."
    key = value.strip().lower()
    _require_pyautogui()
    allowed = set(getattr(pyautogui, "KEYBOARD_KEYS", ()))
    if allowed and key not in allowed:
        return "", f"Unsupported key: '{value}'."
    return key, ""


def _validated_hotkey(value: Any) -> tuple[list[str], str]:
    if isinstance(value, str):
        keys = [part.strip().lower() for part in value.split("+")]
    elif isinstance(value, (list, tuple)):
        keys = [str(part).strip().lower() for part in value]
    else:
        return [], "Hotkey keys must be a '+'-separated string or a list."
    if not keys or any(not key for key in keys):
        return [], "Provide one or more key names, for example 'ctrl+c'."
    if len(keys) > 5:
        return [], "A hotkey can contain at most five keys."
    _require_pyautogui()
    allowed = set(getattr(pyautogui, "KEYBOARD_KEYS", ()))
    invalid = [key for key in keys if allowed and key not in allowed]
    if invalid:
        return [], f"Unsupported key(s): {', '.join(invalid)}."
    return keys, ""


def _as_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normal = value.strip().lower()
        if normal in {"true", "1", "yes", "on"}:
            return True
        if normal in {"false", "0", "no", "off"}:
            return False
    return default


def _summarize_params(params: dict) -> dict:
    """Keep secrets and long dictated text out of the terminal transcript."""
    secretish = {"text", "content", "password", "token", "secret"}
    out = {}
    for key, value in params.items():
        if key.lower() in secretish and isinstance(value, str):
            out[key] = f"<{len(value)} characters>"
        else:
            out[key] = value
    return out

_FIRST_NAMES = [
    "Alex", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Drew", "Quinn",
    "Avery", "Blake", "Cameron", "Dakota", "Emerson", "Finley", "Harper",
]
_LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Wilson", "Moore", "Taylor", "Anderson", "Thomas", "Jackson",
]
_DOMAINS = ["gmail.com", "yahoo.com", "outlook.com", "proton.me", "mail.com"]


def _random_data(data_type: str) -> str:
    dt = data_type.lower().strip()

    if dt == "first_name":
        return random.choice(_FIRST_NAMES)

    if dt == "last_name":
        return random.choice(_LAST_NAMES)

    if dt == "name":
        return f"{random.choice(_FIRST_NAMES)} {random.choice(_LAST_NAMES)}"

    if dt == "email":
        first = random.choice(_FIRST_NAMES).lower()
        last  = random.choice(_LAST_NAMES).lower()
        num   = random.randint(10, 999)
        return f"{first}.{last}{num}@{random.choice(_DOMAINS)}"

    if dt == "username":
        return f"{random.choice(_FIRST_NAMES).lower()}{random.randint(100, 9999)}"

    if dt == "password":
        chars = string.ascii_letters + string.digits + "!@#$%"
        raw   = (
            random.choice(string.ascii_uppercase)
            + random.choice(string.digits)
            + random.choice("!@#$%")
            + "".join(random.choices(chars, k=9))
        )
        return "".join(random.sample(raw, len(raw)))

    if dt == "phone":
        return f"+1{random.randint(200,999)}{random.randint(1_000_000, 9_999_999)}"

    if dt == "birthday":
        y = random.randint(1980, 2000)
        m = random.randint(1, 12)
        d = random.randint(1, 28)
        return f"{m:02d}/{d:02d}/{y}"

    if dt == "address":
        num    = random.randint(100, 9999)
        street = random.choice(["Main St", "Oak Ave", "Park Blvd", "Elm St", "Cedar Ln"])
        return f"{num} {street}"

    if dt == "zip_code":
        return str(random.randint(10000, 99999))

    if dt == "city":
        return random.choice(["New York", "Los Angeles", "Chicago", "Houston", "Phoenix"])

    return f"random_{data_type}_{random.randint(1000, 9999)}"

def _user_profile() -> dict:
    """Read identity fields from long-term memory."""
    try:
        from memory.memory_manager import load_memory
        identity = load_memory().get("identity", {})
        return {
            k: (v.get("value", "") if isinstance(v, dict) else str(v))
            for k, v in identity.items()
        }
    except Exception:
        pass
    return {}

def _paste_text(text: str, *, preserve_clipboard: bool) -> bool:
    """Paste text through the clipboard, optionally restoring its old value."""
    if not _PYPERCLIP:
        return False

    previous = None
    restore = preserve_clipboard
    if restore:
        try:
            previous = pyperclip.paste()
        except Exception:
            # Pasting still works even when this platform cannot read the old
            # clipboard; just do not claim that it was restored.
            restore = False

    try:
        pyperclip.copy(text)
        time.sleep(0.08)
        paste_key = "command" if _get_os() == "mac" else "ctrl"
        pyautogui.hotkey(paste_key, "v")
        # Give the focused app a moment to consume the clipboard before it is
        # restored. This avoids replacing the user's clipboard after an
        # ordinary smart-type operation.
        time.sleep(0.12)
        return True
    finally:
        if restore:
            try:
                pyperclip.copy(previous)
            except Exception:
                pass


def _type(text: str, interval: float = 0.03) -> str:
    _require_pyautogui()
    time.sleep(0.3)
    # PyAutoGUI cannot type most non-ASCII characters. Clipboard paste makes
    # dictated names and non-English text work without destroying the user's
    # existing clipboard contents.
    if any(ord(char) > 127 for char in text):
        if not _paste_text(text, preserve_clipboard=True):
            return "Cannot type non-English text without pyperclip. Install pyperclip and try again."
        return f"Typed {len(text)} characters."
    pyautogui.typewrite(text, interval=interval)
    return f"Typed {len(text)} characters."


def _smart_type(text: str, clear_first: bool = True) -> str:
    _require_pyautogui()
    if clear_first:
        _clear_field()
        time.sleep(0.1)

    if (len(text) > 20 or any(ord(char) > 127 for char in text)) and _PYPERCLIP:
        _paste_text(text, preserve_clipboard=True)
        return f"Typed {len(text)} characters."

    pyautogui.typewrite(text, interval=0.04)
    return f"Typed {len(text)} characters."


def _click(x=None, y=None, button: str = "left", clicks: int = 1) -> str:
    _require_pyautogui()
    if x is not None and y is not None:
        pyautogui.click(x, y, button=button, clicks=clicks)
        return f"{'Double-c' if clicks == 2 else 'C'}licked ({x}, {y}) [{button}]"
    pyautogui.click(button=button, clicks=clicks)
    return f"Clicked at current position [{button}]"


def _hotkey(*keys) -> str:
    _require_pyautogui()
    pyautogui.hotkey(*keys)
    return f"Hotkey: {'+'.join(keys)}"


def _press(key: str) -> str:
    _require_pyautogui()
    pyautogui.press(key)
    return f"Pressed: {key}"


def _scroll(direction: str = "down", amount: int = 3) -> str:
    _require_pyautogui()
    vertical   = direction in ("up", "down")
    clicks     = amount if direction in ("up", "right") else -amount
    pyautogui.scroll(clicks) if vertical else pyautogui.hscroll(clicks)
    return f"Scrolled {direction} ×{amount}"


def _move(x: int, y: int, duration: float = 0.3) -> str:
    _require_pyautogui()
    pyautogui.moveTo(x, y, duration=duration)
    return f"Mouse → ({x}, {y})"


def _drag(x1: int, y1: int, x2: int, y2: int, duration: float = 0.5) -> str:
    _require_pyautogui()
    pyautogui.moveTo(x1, y1, duration=0.2)
    pyautogui.dragTo(x2, y2, duration=duration, button="left")
    return f"Dragged ({x1},{y1}) → ({x2},{y2})"


def _clipboard_get() -> str:
    if _PYPERCLIP:
        return pyperclip.paste()
    _hotkey("ctrl", "c")
    time.sleep(0.2)
    return "(copied — pyperclip unavailable for read)"


def _clipboard_paste(text: str) -> str:
    if _PYPERCLIP:
        _require_pyautogui()
        _paste_text(text, preserve_clipboard=False)
        return f"Pasted {len(text)} characters."
    return "pyperclip not available"


def _screenshot(save_path: str | None = None) -> str:
    _require_pyautogui()
    path = _safe_screenshot_path(save_path)
    img  = pyautogui.screenshot()
    img.save(str(path))
    return f"Screenshot saved: {path}"


def _clear_field() -> str:
    _require_pyautogui()
    select_key = "command" if _get_os() == "mac" else "ctrl"
    pyautogui.hotkey(select_key, "a")
    time.sleep(0.1)
    pyautogui.press("delete")
    return "Field cleared"


def _windows_visible_windows() -> list[dict]:
    """Read visible top-level Windows without opening a shell.

    The previous focus implementation interpolated a window title into a
    PowerShell command and unconditionally reported success.  Native Win32
    APIs are both safer and let the assistant inspect the available targets
    before it acts.
    """
    if _platform_os() != "windows":
        return []
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        active = int(user32.GetForegroundWindow())
        records: list[dict] = []
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        @callback_type
        def visit(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            length = int(user32.GetWindowTextLengthW(hwnd))
            if length <= 0:
                return True
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, len(buffer))
            title = buffer.value.strip()
            if not title:
                return True
            rect = wintypes.RECT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return True
            records.append({
                "handle": int(hwnd),
                "title": title,
                "active": int(hwnd) == active,
                "bounds": (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)),
            })
            return True

        user32.EnumWindows(visit, 0)
        return records
    except Exception as exc:
        print(f"[ComputerControl] window enumeration failed: {exc}")
        return []


def _mac_window_titles() -> list[str]:
    script = (
        'tell application "System Events" to '
        'get name of every application process whose visible is true'
    )
    try:
        result = subprocess.run(
            ["osascript", "-e", script], capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return []
        return [name.strip() for name in result.stdout.split(",") if name.strip()]
    except Exception:
        return []


def _linux_window_titles() -> list[str]:
    try:
        result = subprocess.run(
            ["wmctrl", "-l"], capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return []
        titles = []
        for line in result.stdout.splitlines():
            # wmctrl: window-id, desktop, host, then title (which may contain spaces).
            parts = line.split(None, 3)
            if len(parts) == 4 and parts[3].strip():
                titles.append(parts[3].strip())
        return titles
    except Exception:
        return []


def _window_titles() -> list[str]:
    os_name = _platform_os()
    if os_name == "windows":
        return [record["title"] for record in _windows_visible_windows()]
    if os_name == "mac":
        return _mac_window_titles()
    if os_name == "linux":
        return _linux_window_titles()
    return []


def _window_query(title: Any) -> tuple[str, str]:
    if not isinstance(title, str) or not title.strip():
        return "", "A window title or app name is required."
    query = title.strip()
    if len(query) > 160:
        return "", "Window title is too long."
    return query, ""


def _matching_windows(query: str) -> list[dict]:
    wanted = query.casefold()
    return [record for record in _windows_visible_windows()
            if wanted in record["title"].casefold()]


def _active_window() -> str:
    os_name = _platform_os()
    if os_name == "windows":
        active = next((record for record in _windows_visible_windows() if record["active"]), None)
        return active["title"] if active else "No foreground window detected."

    if os_name == "mac":
        script = (
            'tell application "System Events" to '
            'get name of first application process whose frontmost is true'
        )
        try:
            result = subprocess.run(
                ["osascript", "-e", script], capture_output=True, text=True, timeout=5
            )
            title = result.stdout.strip()
            return title or "No foreground window detected."
        except Exception as exc:
            return f"Could not inspect the foreground window: {exc}"

    if os_name == "linux":
        try:
            result = subprocess.run(
                ["xdotool", "getactivewindow", "getwindowname"],
                capture_output=True, text=True, timeout=5,
            )
            title = result.stdout.strip()
            return title or "No foreground window detected."
        except FileNotFoundError:
            return "Foreground-window inspection requires xdotool on Linux."
        except Exception as exc:
            return f"Could not inspect the foreground window: {exc}"

    return "Foreground-window inspection is not supported on this OS."


def _list_windows() -> str:
    titles = _window_titles()
    if not titles:
        return "No visible application windows were found."
    active = _active_window()
    shown = titles[:_MAX_WINDOW_RESULTS]
    result = f"Visible windows ({len(titles)}):\n" + "\n".join(
        f"{'*' if title == active else '-'} {title}" for title in shown
    )
    if len(titles) > len(shown):
        result += f"\n... and {len(titles) - len(shown)} more."
    return result


def _display_info() -> str:
    try:
        left, top, width, height = _screen_bounds()
        cursor = pyautogui.position()
        return (
            f"Desktop bounds: ({left},{top}) to ({left + width - 1},{top + height - 1}); "
            f"cursor: ({cursor.x},{cursor.y})."
        )
    except Exception as exc:
        return f"Could not inspect the display: {exc}"


def _focus_window(title: str) -> str:
    query, error = _window_query(title)
    if error:
        return error
    os_name = _platform_os()

    if os_name == "windows":
        try:
            import ctypes

            matches = _matching_windows(query)
            if not matches:
                return f"No visible window matches '{query}'. Use list_windows to inspect available windows."
            target = matches[0]
            user32 = ctypes.windll.user32
            user32.ShowWindow(target["handle"], 9)  # SW_RESTORE
            user32.SetForegroundWindow(target["handle"])
            time.sleep(0.25)
            active = next((record for record in _windows_visible_windows() if record["active"]), None)
            if active and active["handle"] == target["handle"]:
                return f"Focused window: {target['title']}"
            return (f"Found '{target['title']}', but Windows did not allow it to become the "
                    "foreground window. Select it manually and continue.")
        except Exception as e:
            return f"focus_window (Windows) failed: {e}"

    if os_name == "mac":
        # Pass the title as an argv value, never interpolate it into AppleScript.
        script = (
            "on run argv\n"
            "  tell application \"System Events\"\n"
            "    set frontmost of (first application process whose name contains (item 1 of argv)) to true\n"
            "  end tell\n"
            "end run"
        )
        try:
            subprocess.run(
                ["osascript", "-e", script, query],
                capture_output=True, timeout=5,
            )
            time.sleep(0.3)
            return f"Focused window: {query}"
        except Exception as e:
            return f"focus_window (macOS) failed: {e}"

    if os_name == "linux":
        try:
            result = subprocess.run(
                ["wmctrl", "-a", query],
                capture_output=True, timeout=5,
            )
            if result.returncode == 0:
                time.sleep(0.3)
                return f"Focused window: {query}"
        except FileNotFoundError:
            pass
        try:
            result = subprocess.run(
                ["xdotool", "search", "--name", query, "windowactivate"],
                capture_output=True, timeout=5,
            )
            if result.returncode == 0:
                time.sleep(0.3)
                return f"Focused window: {query}"
            return f"No visible window matches '{query}'."
        except FileNotFoundError:
            return "focus_window (Linux) requires wmctrl or xdotool"
        except Exception as e:
            return f"focus_window (Linux) failed: {e}"

    return f"focus_window: unknown OS '{os_name}'"


def _wait_for_window(title: Any, seconds: Any) -> str:
    query, error = _window_query(title)
    if error:
        return error
    try:
        timeout = min(max(float(seconds if seconds is not None else 10), 0.2),
                      _MAX_WINDOW_WAIT_SECONDS)
    except (TypeError, ValueError):
        return "Wait time must be a number of seconds."

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if any(query.casefold() in item.casefold() for item in _window_titles()):
            return f"Window appeared: {query}"
        time.sleep(0.25)
    return f"Timed out after {timeout:g}s waiting for a window matching '{query}'."

def _screen_find(description: str) -> tuple[int, int] | None:
    description = (description or "").strip()
    if not description:
        return None
    if len(description) > 240:
        print("[ComputerControl] screen_find description was too long")
        return None
    api_key = _get_api_key()
    if not api_key:
        print("[ComputerControl] ⚠️ No API key for screen_find")
        return None

    try:
        from google import genai
        from google.genai import types as gtypes

        _require_pyautogui()
        # Use the captured frame's exact pixel dimensions. On Windows with
        # display scaling, pyautogui.size() can report logical pixels while the
        # screenshot and the click API use physical pixels, shifting targets.
        img   = pyautogui.screenshot()
        w, h  = img.size
        buf   = io.BytesIO()
        img.save(buf, format="PNG")
        image_bytes = buf.getvalue()

        prompt = (
            f"This is a screenshot of a {w}×{h} pixel screen. "
            f"Locate the UI element described as: '{description}'. "
            f"Reply with ONLY the center coordinates as: x,y "
            f"If the element is not visible, reply: NOT_FOUND"
        )

        from core import gemini
        response = gemini.call(
            [gtypes.Part.from_bytes(data=image_bytes, mime_type="image/png"), prompt],
            tier=gemini.FAST, timeout_ms=20_000,
        )
        if response is None:
            return None

        text = (response.text or "").strip()
        if "NOT_FOUND" in text.upper():
            return None

        match = re.search(r"(\d+)\s*,\s*(\d+)", text)
        if match:
            x, y = int(match.group(1)), int(match.group(2))
            # The vision prompt's coordinates describe the screenshot, so they
            # must be inside that exact image before they can become a click.
            if 0 <= x < w and 0 <= y < h:
                return x, y
            print(f"[ComputerControl] screen_find returned out-of-image coordinates: {x},{y}")

    except Exception as e:
        print(f"[ComputerControl] ⚠️ screen_find failed: {e}")

    return None


_CONFIRM_BEFORE_CLICK = (
    "buy", "purchase", "checkout", "pay", "payment", "place order",
    "book", "transfer", "send", "submit", "post", "publish", "share",
    "delete", "remove", "uninstall", "install", "confirm", "authorize",
    "allow", "grant access",
)

# These patterns describe safe IDE / OS dialog buttons that should never be
# routed through the confirmation gate.  VS Code's Workspace Trust banner is
# the primary case: clicking "Trust" or "Yes, I trust the authors" is an
# ordinary development action, not a financial or destructive one.
_SAFE_CLICK_BYPASS = (
    "trust",
    "yes, i trust",
    "i trust",
    "workspace trust",
    "restricted mode",
    "trust the authors",
    "trust this folder",
    "trust workspace",
)


def _needs_click_confirmation(description: str) -> bool:
    text = (description or "").casefold()
    # Known-safe IDE/OS dialog buttons bypass the gate entirely.
    if any(bypass in text for bypass in _SAFE_CLICK_BYPASS):
        return False
    return any(term in text for term in _CONFIRM_BEFORE_CLICK)


def _screen_click(description: str) -> str:
    """Click a described element, asking on the HUD before consequential clicks."""
    description = (description or "").strip()
    if not description:
        return "Describe the element to click."
    if len(description) > 240:
        return "Element description is too long."

    def click_current_match() -> str:
        coords = _screen_find(description)
        if not coords:
            return f"Element not found on screen: '{description}'"
        return _click(x=coords[0], y=coords[1])

    if _needs_click_confirmation(description):
        if confirm.pending_title():
            return "There is already a confirmation waiting on screen. Ask the user to answer that one first."
        return confirm.request(
            key="screen_click",
            title="Confirm an on-screen action",
            detail=(f"CHARLIE will find and click: {description}. "
                    "This may send, submit, buy, or otherwise change something."),
            # Re-find after the person confirms so stale coordinates cannot be
            # clicked after the screen has changed.
            run=click_current_match,
        )

    return click_current_match()

def computer_control(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    """
    Dispatch table for all computer control actions.

    parameters keys (all optional unless noted):
      action        : (required) one of the actions listed below
      text          : text to type or paste
      x, y          : screen coordinates
      button        : 'left' | 'right' (default: left)
      keys          : hotkey string, e.g. 'ctrl+c'
      key           : single key name, e.g. 'enter'
      direction     : 'up' | 'down' | 'left' | 'right'
      amount        : scroll amount (default: 3)
      seconds       : wait duration
      title         : window title fragment for focus_window / wait_for_window
      description   : natural-language element description for screen_find/click
      type          : data type for random_data
      field         : memory field name for user_data
      clear_first   : bool, clear field before typing (default: true)
      path          : save path for screenshot (must be inside home dir)

    Actions:
      type          — type text at cursor
      smart_type    — clear field + type (clipboard-backed)
      click         — left click
      double_click  — double left click
      right_click   — right click
      move          — move mouse
      drag          — click-drag between two points
      hotkey        — key combination
      press         — single key
      scroll        — scroll the wheel
      copy          — read clipboard
      paste         — write + paste clipboard
      screenshot    — capture screen (safe path only)
      wait          — sleep N seconds
       clear_field   — select-all + delete
       active_window — return the current foreground window title
       list_windows  — list visible application windows (read-only)
       display_info  — return desktop bounds and current cursor location
       focus_window  — bring window to foreground
       wait_for_window — wait briefly for an app/window after launch
       screen_find   — AI element finder (returns x,y)
       screen_click  — AI element finder + click (HUD confirmation for consequential actions)
      random_data   — generate fake form data
      user_data     — pull real data from memory
    """
    params = parameters if isinstance(parameters, dict) else {}
    raw_action = params.get("action", "")
    action = raw_action.lower().strip() if isinstance(raw_action, str) else ""

    if not action:
        return "No action specified for computer_control."

    if player:
        player.write_log(f"[Computer] {action}")

    print(f"[ComputerControl] ▶ {action}  {_summarize_params(params)}")

    try:

        if action == "type":
            text, error = _validated_text(params.get("text", ""))
            return error or _type(text)

        if action == "smart_type":
            text, error = _validated_text(params.get("text", ""))
            return error or _smart_type(text, clear_first=_as_bool(params.get("clear_first"), True))

        if action in ("click", "left_click"):
            point, error = _parse_screen_point(params.get("x"), params.get("y"), allow_current=True)
            return error or _click(*(point or (None, None)), "left", 1)

        if action == "double_click":
            point, error = _parse_screen_point(params.get("x"), params.get("y"), allow_current=True)
            return error or _click(*(point or (None, None)), "left", 2)

        if action == "right_click":
            point, error = _parse_screen_point(params.get("x"), params.get("y"), allow_current=True)
            return error or _click(*(point or (None, None)), "right", 1)

        if action == "move":
            point, error = _parse_screen_point(params.get("x"), params.get("y"))
            return error or _move(*point)

        if action == "drag":
            start, error = _parse_screen_point(params.get("x1"), params.get("y1"))
            if error:
                return error
            end, error = _parse_screen_point(params.get("x2"), params.get("y2"))
            return error or _drag(*start, *end)

        if action == "hotkey":
            keys, error = _validated_hotkey(params.get("keys", ""))
            return error or _hotkey(*keys)

        if action == "press":
            key, error = _validated_key(params.get("key", "enter"))
            return error or _press(key)

        if action == "scroll":
            direction = str(params.get("direction", "down")).lower().strip()
            if direction not in {"up", "down", "left", "right"}:
                return "Scroll direction must be up, down, left, or right."
            try:
                amount = min(max(abs(int(params.get("amount", 3))), 1), 100)
            except (TypeError, ValueError):
                return "Scroll amount must be an integer."
            return _scroll(direction=direction, amount=amount)

        if action == "copy":
            return _clipboard_get()

        if action == "paste":
            text, error = _validated_text(params.get("text", ""))
            return error or _clipboard_paste(text)

        if action == "screenshot":
            return _screenshot(params.get("path"))

        if action == "screen_find":
            coords = _screen_find(params.get("description", ""))
            return f"{coords[0]},{coords[1]}" if coords else "NOT_FOUND"

        if action == "screen_click":
            return _screen_click(params.get("description", ""))

        if action == "wait":
            try:
                secs = min(max(float(params.get("seconds", 1.0)), 0.0), 30.0)
            except (TypeError, ValueError):
                return "Wait time must be a number of seconds."
            time.sleep(secs)
            return f"Waited {secs}s"

        if action == "clear_field":
            return _clear_field()

        if action == "focus_window":
            return _focus_window(params.get("title", ""))

        if action == "active_window":
            return f"Active window: {_active_window()}"

        if action == "list_windows":
            return _list_windows()

        if action == "display_info":
            return _display_info()

        if action == "wait_for_window":
            return _wait_for_window(params.get("title", ""), params.get("seconds", 10))

        if action == "random_data":
            dt     = params.get("type", "name")
            result = _random_data(dt)
            print(f"[ComputerControl] 🎲 random {dt} → {result}")
            return result

        if action == "user_data":
            field   = params.get("field", "name")
            profile = _user_profile()
            value   = profile.get(field, "")
            if not value:
                value = _random_data(field)
                print(f"[ComputerControl] ⚠️ No '{field}' in memory, using random: {value}")
            return value

        return f"Unknown action: '{action}'"

    except Exception as e:
        print(f"[ComputerControl] ❌ {action}: {e}")
        return f"computer_control '{action}' failed: {e}"


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "computer_control",
    "description": "Direct computer control for desktop tasks. Use active_window/list_windows/display_info before coordinate actions when context is unclear; then focus_window, screen_find, and screen_click as needed. Supports typing, mouse, keyboard, scrolling, screenshots, and waiting for apps. A screen_click described as sending, submitting, buying, deleting, installing, or granting access puts a human confirmation on the HUD and does not run until the user presses it.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "type | smart_type | click | double_click | right_click | move | drag | hotkey | press | scroll | copy | paste | screenshot | wait | clear_field | active_window | list_windows | display_info | focus_window | wait_for_window | screen_find | screen_click | random_data | user_data"
            },
            "text": {
                "type": "STRING",
                "description": "Text to type or paste"
            },
            "x": {
                "type": "INTEGER",
                "description": "X coordinate"
            },
            "y": {
                "type": "INTEGER",
                "description": "Y coordinate"
            },
            "x1": {
                "type": "INTEGER",
                "description": "Drag starting X coordinate"
            },
            "y1": {
                "type": "INTEGER",
                "description": "Drag starting Y coordinate"
            },
            "x2": {
                "type": "INTEGER",
                "description": "Drag ending X coordinate"
            },
            "y2": {
                "type": "INTEGER",
                "description": "Drag ending Y coordinate"
            },
            "keys": {
                "type": "STRING",
                "description": "Key combination e.g. 'ctrl+c'"
            },
            "key": {
                "type": "STRING",
                "description": "Single key e.g. 'enter'"
            },
            "direction": {
                "type": "STRING",
                "description": "up | down | left | right"
            },
            "amount": {
                "type": "INTEGER",
                "description": "Scroll amount (default: 3)"
            },
            "seconds": {
                "type": "NUMBER",
                "description": "Seconds to wait (wait / wait_for_window; maximum 30)"
            },
            "title": {
                "type": "STRING",
                "description": "Window title or app name for focus_window / wait_for_window"
            },
            "description": {
                "type": "STRING",
                "description": "Element description for screen_find/screen_click. Describe any consequential target clearly; screen_click asks on the HUD before send/submit/buy/delete/install/access actions."
            },
            "type": {
                "type": "STRING",
                "description": "Data type for random_data"
            },
            "field": {
                "type": "STRING",
                "description": "Field for user_data: name|email|city"
            },
            "clear_first": {
                "type": "BOOLEAN",
                "description": "Clear field before typing (default: true)"
            },
            "path": {
                "type": "STRING",
                "description": "Save path for screenshot"
            }
        },
        "required": [
            "action"
        ]
    },
    "handler": computer_control,
}
