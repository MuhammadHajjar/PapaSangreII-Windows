"""Every test writes into its own temporary folder, never a real save.

`paths.writable_root()` decides where config, keys, settings and the save go;
from source it is the repository itself, and a test that saved there once
overwrote a real save in another port.  So it is pointed at a temp dir for
the whole run.
"""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from papasangre2.util import paths      # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_saves(tmp_path_factory, monkeypatch):
    root = str(tmp_path_factory.mktemp('writable'))
    monkeypatch.setattr(paths, 'writable_root', lambda: root)
    monkeypatch.setenv('LOCALAPPDATA', root)
    yield
