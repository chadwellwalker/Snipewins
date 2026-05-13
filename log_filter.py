"""
log_filter.py — drop trace-level noise from the log capture.

Why this exists:
    The engine emits ~2,000 trace lines per valued row across tags like
    SUBSET_PARSE_RESULT, SERIAL_PARSE, TOPPS_FAMILY_PARSE, etc. A 97-row
    scan produces 200,000+ log lines, most of which is line-level
    parsing telemetry useful only when debugging a specific card.
    Writing all of that to disk slows the scan AND makes last_scan.log
    impossible to scroll.

    This module wraps stdout/stderr at the run_app.py / run_scan_once.py
    level so the chattiest tags are suppressed from the captured log AND
    the terminal. The engine is unchanged — every print still happens,
    we just decline to write the noisiest ones to disk.

    To restore full output (for debugging a specific row), set
    SNIPEWINS_VERBOSE=1 in the environment before launch:
        Windows cmd:    set SNIPEWINS_VERBOSE=1 && python run_app.py
        PowerShell:     $env:SNIPEWINS_VERBOSE="1"; python run_app.py
        Mac/Linux:      SNIPEWINS_VERBOSE=1 python run_app.py
"""
from __future__ import annotations

import os
from typing import Iterable


# Tags that fire MANY times per scan and provide trace-level detail useful
# only when debugging a specific card. Curated 2026-05-08 from a 97-row
# valuation where these tags accounted for ~80% of all log volume:
#   SUBSET_PARSE_RESULT  59,432
#   SUBSET_PARSE_GUARD   51,742
#   SERIAL_PARSE         34,631
#   TOPPS_FAMILY_PARSE    8,381
#   TOPPS_FAMILY_GUARD    8,370
#   ... etc.
#
# Tags NOT in this list (because they're either rare or load-bearing for
# the funnel diagnosis): ENGINE_STAGE, PREPARE_SUMMARY, PREPARE_DROP,
# PREPARE_HANDOFF_TRACE, VALUATION_HANDOFF_GATE, PREMIUM_SHAPE_TITLE_RESCUE,
# CANDIDATE_DROP, INTAKE_TIME_DROP, ROUTING_REJECT, ROUTING_PASS, anything
# with ERROR / FAIL / WARN.
_DEFAULT_NOISY_TAGS: tuple = (
    "[SUBSET_PARSE_RESULT]",
    "[SUBSET_PARSE_GUARD]",
    "[SERIAL_PARSE]",
    "[TOPPS_FAMILY_PARSE]",
    "[TOPPS_FAMILY_GUARD]",
    "[PARALLEL_FAMILY_RAW]",
    "[PARALLEL_FAMILY_ASSIGN]",
    "[PLAYER_ANCHOR_REPAIR]",
    "[AUTO_IDENTITY]",
    "[AUTO_MATCH_ASSERT]",
    "[COMP_KEEP_NEAR]",
    "[PRICE_CHAIN_TRACE]",
    "[PREMIUM_BUCKET]",
    "[PREMIUM_PARALLEL_DROP]",
    "[PREMIUM_COMP_REJECT]",
)


def is_verbose_mode() -> bool:
    """True if SNIPEWINS_VERBOSE=1 in the environment."""
    return str(os.environ.get("SNIPEWINS_VERBOSE", "")).strip() in {"1", "true", "yes", "on"}


def is_noisy_line(line: str, noisy_tags: Iterable[str] = _DEFAULT_NOISY_TAGS) -> bool:
    """True if `line` starts with one of the noisy trace tags."""
    if not line:
        return False
    s = line.lstrip()
    for tag in noisy_tags:
        if s.startswith(tag):
            return True
    return False


class FilteringTee:
    """
    Drop-in replacement for the Tee class used in run_app.py and
    run_scan_once.py. Writes to all underlying streams unless the line
    matches a noisy trace tag AND verbose mode is OFF.

    Verbose mode (SNIPEWINS_VERBOSE=1) bypasses the filter entirely so
    every line goes to every stream. Used when actively debugging.
    """

    def __init__(self, *streams, noisy_tags: Iterable[str] = _DEFAULT_NOISY_TAGS):
        self._streams = streams
        self._noisy_tags = tuple(noisy_tags)
        self._verbose = is_verbose_mode()
        # Buffer partial writes (Python sometimes calls write() with
        # incomplete lines) so we can match the tag at the start.
        self._buffer = ""

    def write(self, data):
        if not data:
            return
        # Verbose mode: pass through without filtering.
        if self._verbose:
            self._fanout(data)
            return
        # Filter mode: split on newlines, drop noisy lines.
        text = self._buffer + str(data)
        # Keep last partial line in the buffer if the chunk doesn't end with \n.
        if text.endswith("\n"):
            chunks = text.split("\n")
            self._buffer = ""
            # Drop the empty trailing element from the split-on-trailing-\n.
            chunks = chunks[:-1]
            kept = "\n".join(c for c in chunks if not is_noisy_line(c, self._noisy_tags))
            if kept:
                self._fanout(kept + "\n")
        else:
            # Incomplete line: keep building. Most real terminal output
            # lines end with \n so this branch is mostly hit during
            # progress-bar style writes, which we don't filter.
            lines = text.split("\n")
            self._buffer = lines[-1]
            full = lines[:-1]
            kept = "\n".join(c for c in full if not is_noisy_line(c, self._noisy_tags))
            if kept:
                self._fanout(kept + "\n")

    def _fanout(self, data: str) -> None:
        for s in self._streams:
            try:
                s.write(data)
            except Exception:
                pass

    def flush(self):
        # Flush any buffered partial line (without filtering — we don't
        # know if it's complete).
        if self._buffer and not self._verbose:
            if not is_noisy_line(self._buffer, self._noisy_tags):
                self._fanout(self._buffer)
            self._buffer = ""
        for s in self._streams:
            try:
                s.flush()
            except Exception:
                pass
