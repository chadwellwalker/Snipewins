"""
Windows/cp1252-safe text for stdout/stderr and diagnostic print paths.

Streamlit on Windows often runs with a legacy console encoding; print() of titles
or labels containing arrows, smart punctuation, or emoji can raise UnicodeEncodeError
and abort scans. This module normalizes text before it hits the console.
"""

from __future__ import annotations

import builtins
import sys
from typing import Any, List, Optional, TextIO

_UNICODE_REPLACEMENTS: List[tuple[str, str]] = [
    ("\u2192", "->"),
    ("\u2190", "<-"),
    ("\u2194", "<->"),
    ("\u2022", "-"),
    ("\u2026", "..."),
    ("\u2014", "-"),
    ("\u2013", "-"),
    ("\u201c", '"'),
    ("\u201d", '"'),
    ("\u2018", "'"),
    ("\u2019", "'"),
    ("\u00a0", " "),
    ("\u2011", "-"),
    ("\u2032", "'"),
    ("\u2033", '"'),
    ("\ufeff", ""),
]

_PRINT_PATCHED = False
_ORIGINAL_PRINT = builtins.print


def safe_console_text(obj: Any, *, max_len: Optional[int] = None) -> str:
    """Return a string safe for cp1252 consoles; never raises."""
    try:
        if obj is None:
            s = ""
        else:
            s = str(obj)
    except Exception:
        return ""
    for u, rep in _UNICODE_REPLACEMENTS:
        s = s.replace(u, rep)
    try:
        s = s.encode("cp1252", errors="replace").decode("cp1252")
    except Exception:
        try:
            s = s.encode("ascii", errors="replace").decode("ascii")
        except Exception:
            s = ""
    if max_len is not None and max_len >= 0 and len(s) > max_len:
        s = s[:max_len]
    return s


def safe_print(*args: Any, sep: str = " ", end: str = "\n", file: Optional[TextIO] = None, flush: bool = False) -> None:
    """Like print() but sanitizes args; targets stdout/stderr by default."""
    f = sys.stdout if file is None else file
    line = sep.join(safe_console_text(a) for a in args) + end
    try:
        f.write(line)
        if flush:
            f.flush()
    except Exception:
        try:
            fb = line.encode("ascii", errors="replace").decode("ascii")
            f.write(fb)
            if flush:
                f.flush()
        except Exception:
            pass


def install_cp1252_safe_print_once() -> None:
    """Patch builtins.print once so diagnostics never die on cp1252 (Windows)."""
    global _PRINT_PATCHED
    if _PRINT_PATCHED:
        return
    _PRINT_PATCHED = True

    def _patched_print(*args: Any, **kwargs: Any) -> None:
        sep = kwargs.pop("sep", " ")
        end = kwargs.pop("end", "\n")
        file = kwargs.pop("file", None)
        flush = kwargs.pop("flush", False)
        if kwargs:
            return _ORIGINAL_PRINT(*args, sep=sep, end=end, file=file, flush=flush, **kwargs)
        f: TextIO = sys.stdout if file is None else file
        if f is not sys.stdout and f is not sys.stderr:
            return _ORIGINAL_PRINT(*args, sep=sep, end=end, file=file, flush=flush)
        line = sep.join(safe_console_text(a) for a in args) + end
        try:
            f.write(line)
            if flush:
                f.flush()
        except Exception:
            try:
                f.write(line.encode("ascii", errors="replace").decode("ascii"))
                if flush:
                    f.flush()
            except Exception:
                pass

    builtins.print = _patched_print  # type: ignore[assignment]


def safe_traceback_print_exc() -> None:
    """Like traceback.print_exc() but survives cp1252 stderr when frame text is exotic."""
    import traceback

    try:
        traceback.print_exc()
    except Exception:
        try:
            safe_print(traceback.format_exc(), file=sys.stderr)
        except Exception:
            pass


def verify_encoding_safe_helpers() -> bool:
    """Tiny self-check for sanitization (importable / manual run)."""
    assert "->" in safe_console_text("A -> B")
    assert "->" in safe_console_text("A \u2192 B")
    assert "..." in safe_console_text("value\u2026")
    assert "-" in safe_console_text("\u2022 item")
    assert safe_console_text(None) == ""
    assert safe_console_text(42) == "42"
    return True


if __name__ == "__main__":
    verify_encoding_safe_helpers()
    safe_print("encoding_safe: self-check OK")
