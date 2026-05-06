"""
conftest.py — pytest root configuration for BetterParameters offline tests.

Injects adsk stubs into sys.path BEFORE any test module is imported so that
`import adsk.core / adsk.fusion` in BetterParameters.py resolves to stubs.
Also adds the BetterParameters source dir so update_state.py is importable.
"""
import sys
import os

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
STUBS_DIR = os.path.join(TESTS_DIR, "stubs")
BP_SRC_DIR = os.path.abspath(os.path.join(TESTS_DIR, "..", "BetterParameters"))

# Stubs must come first so adsk resolves to stubs, not the real Fusion extension.
for path in (STUBS_DIR, BP_SRC_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)
