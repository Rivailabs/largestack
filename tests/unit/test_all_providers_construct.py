"""Every provider adapter must at least CONSTRUCT and expose the chat/aclose
interface. Regression guard for GoogleProvider's broken httpx.Timeout (which
raised on construction, making Gemini unusable despite a "partial" matrix status).
"""

from __future__ import annotations

import glob
import importlib
import inspect
import os

import pytest

_MODULES = sorted(
    "largestack._core.providers." + os.path.basename(f)[:-3]
    for f in glob.glob("largestack/_core/providers/*_prov.py")
)


def _provider_class(mod_name):
    m = importlib.import_module(mod_name)
    return next(
        (
            c
            for n, c in inspect.getmembers(m, inspect.isclass)
            if n.endswith("Provider") and c.__module__ == mod_name
        ),
        None,
    )


@pytest.mark.parametrize("mod_name", _MODULES)
def test_provider_constructs_and_has_interface(mod_name):
    cls = _provider_class(mod_name)
    if cls is None:
        pytest.skip(f"no Provider class in {mod_name}")
    inst = None
    for args in [
        ("dummy-key",),
        ("dummy-key", "https://example.test"),
        ("dummy-key", "dummy-2"),
        ("us-east-1",),
    ]:
        try:
            inst = cls(*args)
            break
        except TypeError:
            continue  # wrong arity — try the next shape
    assert inst is not None, f"{cls.__name__} could not be constructed with dummy creds"
    assert hasattr(inst, "chat"), f"{cls.__name__} missing chat()"
    assert hasattr(inst, "aclose") or hasattr(inst, "close"), f"{cls.__name__} missing aclose/close"
