"""Tests for CLI commands."""

import sys, os

sys.path.insert(0, ".")


def test_cli_imports():
    from largestack._cli.main import (
        dashboard,
        doctor,
        explain,
        graph,
        knowledge_add,
        knowledge_list,
        list_templates,
        providers,
        version,
    )

    assert callable(version)
    assert callable(doctor)
    assert callable(explain)
    assert callable(list_templates)
    assert callable(providers)
    assert callable(graph)
    assert callable(knowledge_add)
    assert callable(knowledge_list)


def test_cli_commands_import():
    from largestack._cli.commands import register_commands

    assert callable(register_commands)


def test_version_format():
    """Version should be semver."""
    from largestack import __version__

    parts = __version__.split(".")
    assert len(parts) == 3
    assert all(p.isdigit() for p in parts)
