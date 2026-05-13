"""
Recovery bootstrap for the main Streamlit app.

This restores app launchability by executing the latest compiled app artifact
from __pycache__ when the source file has been lost.
"""

from __future__ import annotations

import marshal
from pathlib import Path


def _load_compiled_app() -> None:
    pyc_path = Path(__file__).with_name("__pycache__") / "streamlit_app.cpython-314.pyc"
    if not pyc_path.exists():
        raise FileNotFoundError(f"Missing compiled recovery artifact: {pyc_path}")

    with pyc_path.open("rb") as fh:
        fh.read(16)
        code = marshal.load(fh)

    globals_dict = globals()
    globals_dict["__file__"] = str(Path(__file__).resolve())
    globals_dict["__package__"] = None
    exec(code, globals_dict, globals_dict)


_load_compiled_app()
