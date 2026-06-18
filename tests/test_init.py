"""Tests for peekai.init() re-entrancy via the patch registry."""

from __future__ import annotations

import peekai
from peekai.patches.registry import get_tracer


def test_init_reentrant_updates_active_tracer(tmp_path):
    # SDK flags off so the test stays fast and doesn't import heavy SDKs.
    t1 = peekai.init(
        db_path=str(tmp_path / "db1.db"), openai=False, anthropic=False, litellm=False
    )
    assert get_tracer() is t1

    t2 = peekai.init(
        db_path=str(tmp_path / "db2.db"), openai=False, anthropic=False, litellm=False
    )
    assert t1 is not t2
    # Re-init must point the registry (and thus installed patches) at the new tracer.
    assert get_tracer() is t2
