import pytest
from src.comparator import ScopeComparator
from src.models import DeclaredScope, ObservedEffects


def test_comparator_exact_match():
    comp = ScopeComparator()
    declared = DeclaredScope(write=["/workspace/report.txt"])
    observed = ObservedEffects(
        files_created=["/workspace/report.txt"],
        files_modified=[],
        files_deleted=[],
        files_read=[]
    )
    res = comp.compare(declared, observed)
    assert res.match is True
    assert len(res.unexpected_effects) == 0


def test_comparator_unexpected_write():
    comp = ScopeComparator()
    declared = DeclaredScope(write=["/workspace/report.txt"])
    observed = ObservedEffects(
        files_created=["/workspace/report.txt", "/workspace/extra.txt"],
        files_modified=[],
        files_deleted=[],
        files_read=[]
    )
    res = comp.compare(declared, observed)
    assert res.match is False
    assert any("create /workspace/extra.txt" in e for e in res.unexpected_effects)


def test_comparator_unexpected_read():
    comp = ScopeComparator()
    declared = DeclaredScope(write=["/workspace/report.txt"])
    observed = ObservedEffects(
        files_created=["/workspace/report.txt"],
        files_modified=[],
        files_deleted=[],
        files_read=["/workspace/secrets/api_key"]
    )
    res = comp.compare(declared, observed)
    assert res.match is False
    assert any("read /workspace/secrets/api_key" in e for e in res.unexpected_effects)
