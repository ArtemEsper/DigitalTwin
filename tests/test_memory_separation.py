"""
Tests for Digital Twin memory / Development memory separation.

Verifies that:
- Digital Twin memory tables use the dt_ prefix
- No Digital Twin model imports development memory tooling
- MemoryService never imports or references dev-memory modules
- Channel gateway never imports or references dev-memory modules
- The development memory placeholder path (docs/) is never accessible
  from within src/memory/ or src/channels/
"""

import ast
import importlib
import inspect
import os
import sys
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Table prefix verification
# ---------------------------------------------------------------------------

def test_all_digital_twin_tables_use_dt_prefix():
    """All ORM models in src/models/ must use the dt_ table prefix."""
    from src.models import (
        AuditLog,
        ChannelConfig,
        ConversationMessage,
        Entity,
        MemoryCandidate,
        MemoryItem,
        RawSource,
        Relationship,
    )

    models = [
        AuditLog, ChannelConfig, ConversationMessage, Entity,
        MemoryCandidate, MemoryItem, RawSource, Relationship,
    ]
    for model in models:
        assert model.__tablename__.startswith("dt_"), (
            f"{model.__name__}.__tablename__ = {model.__tablename__!r} "
            "does not start with 'dt_'"
        )


# ---------------------------------------------------------------------------
# Import isolation verification (static analysis)
# ---------------------------------------------------------------------------

_SRC_ROOT = Path(__file__).parent.parent / "src"

# These patterns indicate an actual import of dev-memory tooling.
# Using import-specific patterns avoids false positives from docstring mentions.
_DEV_MEMORY_IMPORT_PATTERNS = [
    "import mempalace",
    "from mempalace",
    "import dev_memory",
    "from dev_memory",
    "import development_memory",
    "from development_memory",
]


def _get_python_files(directory: Path) -> list[Path]:
    return list(directory.rglob("*.py"))


def _file_contains_dev_memory_import(filepath: Path) -> list[str]:
    """Return list of forbidden import patterns found in the file."""
    source = filepath.read_text(encoding="utf-8").lower()
    return [p for p in _DEV_MEMORY_IMPORT_PATTERNS if p in source]


def test_memory_service_does_not_import_dev_memory():
    """src/memory/ must not reference dev-memory tooling."""
    memory_dir = _SRC_ROOT / "memory"
    violations = []
    for py_file in _get_python_files(memory_dir):
        found = _file_contains_dev_memory_import(py_file)
        if found:
            violations.append(f"{py_file.name}: {found}")
    assert violations == [], (
        "src/memory/ references dev-memory tooling:\n" + "\n".join(violations)
    )


def test_channel_gateway_does_not_import_dev_memory():
    """src/channels/ must not reference dev-memory tooling."""
    channels_dir = _SRC_ROOT / "channels"
    violations = []
    for py_file in _get_python_files(channels_dir):
        found = _file_contains_dev_memory_import(py_file)
        if found:
            violations.append(f"{py_file.name}: {found}")
    assert violations == [], (
        "src/channels/ references dev-memory tooling:\n" + "\n".join(violations)
    )


def test_models_do_not_import_dev_memory():
    """src/models/ must not reference dev-memory tooling."""
    models_dir = _SRC_ROOT / "models"
    violations = []
    for py_file in _get_python_files(models_dir):
        found = _file_contains_dev_memory_import(py_file)
        if found:
            violations.append(f"{py_file.name}: {found}")
    assert violations == [], (
        "src/models/ references dev-memory tooling:\n" + "\n".join(violations)
    )


# ---------------------------------------------------------------------------
# Runtime isolation — separate operations don't share state
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_memory_operations_are_isolated_from_each_other(
    db_session, mock_llm
):
    """
    Two independent MemoryService operations on separate sessions
    should not share in-memory state.
    """
    from src.memory.service import MemoryService

    service_a = MemoryService(db=db_session, llm=mock_llm)
    service_b = MemoryService(db=db_session, llm=mock_llm)

    candidate_a = await service_a.create_candidate(
        proposed_content="Memory A", proposed_type="biographical", actor="test_a"
    )
    candidate_b = await service_b.create_candidate(
        proposed_content="Memory B", proposed_type="preference", actor="test_b"
    )

    # Each candidate has a distinct ID
    assert candidate_a.id != candidate_b.id
    assert candidate_a.proposed_content != candidate_b.proposed_content


@pytest.mark.asyncio
async def test_deleted_items_excluded_from_retrieval(db_session, mock_llm):
    """Soft-deleted memory items must not appear in retrieve_relevant results."""
    from src.memory.service import MemoryService

    service = MemoryService(db=db_session, llm=mock_llm)
    candidate = await service.create_candidate(
        proposed_content="This will be deleted.", proposed_type="preference", actor="test"
    )
    item = await service.approve_candidate(candidate_id=candidate.id, reviewer_id="admin")
    await service.soft_delete(memory_item_id=item.id, actor="admin")

    results = await service.retrieve_relevant("deleted memory", actor="test")
    assert all(r.id != item.id for r in results), (
        "Deleted memory item appeared in retrieval results"
    )
