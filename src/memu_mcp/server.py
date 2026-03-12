"""MCP (Model Context Protocol) server for memU."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
import uuid
from typing import Any

from pydantic import BaseModel

from memu.app.service import MemoryService
from memu.database.models import MemoryType

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as e:
    msg = "Please install 'mcp' package: pip install mcp"
    raise ImportError(msg) from e

logger = logging.getLogger("memu_mcp.server")

mcp_server = FastMCP("memu")

_service: MemoryService | None = None


class MCPUserModel(BaseModel):
    """Extended user scope model for MCP with agent and session support."""

    user_id: str | None = None
    agent_id: str | None = None
    session_id: str | None = None


def _apply_compat_patches(service: MemoryService) -> None:
    """Patch memu-py 1.4.0 bug: _patch_create_memory_item missing resource_id."""
    repo = service.database.memory_item_repo
    _orig_create_item = repo.create_item

    def _patched_create_item(**kw: Any) -> Any:
        kw.setdefault("resource_id", "")
        return _orig_create_item(**kw)

    repo.create_item = _patched_create_item  # type: ignore[method-assign]


def _apply_sqlite_compat_patches() -> None:
    """Patch memu-py 1.4.0 SQLite bugs before MemoryService construction.

    Bug 1: Resource/MemoryItem/MemoryCategory base models define
    ``embedding: list[float] | None`` as a Pydantic field.  The SQLite models
    attempt to shadow it with a ``@property`` + ``embedding_json`` pair, but
    Pydantic v2 ignores the property and keeps the inherited field.  SQLModel's
    ``table=True`` then fails because ``list`` has no SQLAlchemy type mapping.
    Fix: patch ``get_sqlalchemy_type`` to fall back to ``JSON`` for unmapped types.

    Bug 2: Table names use the ``sqlite_`` prefix which is reserved by SQLite.
    Fix: replace ``get_sqlite_sqlalchemy_models`` to use ``memu_`` prefix.

    Bug 3: The ``@property embedding`` descriptors from Bug 1 survive in the
    class ``__dict__`` and leak as raw ``property`` objects when Pydantic v2
    serialises instances, causing ``Object of type property is not JSON
    serializable``.  Fix: strip the descriptors before building table models
    so ``embedding`` falls back to the inherited Pydantic field (which Bug 1
    already maps to a ``JSON`` column).
    """
    import sqlmodel.main as _sqlmodel_main

    _orig_get_sa_type = _sqlmodel_main.get_sqlalchemy_type

    def _patched_get_sa_type(field: Any) -> Any:
        try:
            return _orig_get_sa_type(field)
        except ValueError:
            from sqlalchemy import JSON

            return JSON()

    _sqlmodel_main.get_sqlalchemy_type = _patched_get_sa_type

    import memu.database.sqlite.schema as _schema
    import memu.database.sqlite.sqlite as _sqlite_mod

    _schema._MODEL_CACHE.clear()

    def _patched_get_models(*, scope_model: type[BaseModel] | None = None) -> Any:
        from sqlalchemy import MetaData
        from sqlmodel import SQLModel

        from memu.database.sqlite.models import (
            SQLiteCategoryItemModel,
            SQLiteMemoryCategoryModel,
            SQLiteMemoryItemModel,
            SQLiteResourceModel,
            build_sqlite_table_model,
        )

        # Bug 3: strip @property descriptors so embedding works as a plain field.
        for _cls in (SQLiteResourceModel, SQLiteMemoryItemModel, SQLiteMemoryCategoryModel):
            if "embedding" in _cls.__dict__ and isinstance(_cls.__dict__["embedding"], property):
                delattr(_cls, "embedding")

        scope = scope_model or BaseModel
        cached = _schema._MODEL_CACHE.get(scope)
        if cached:
            return cached

        metadata_obj = MetaData()
        resource_model = build_sqlite_table_model(
            scope, SQLiteResourceModel, tablename="memu_resources", metadata=metadata_obj,
        )
        memory_category_model = build_sqlite_table_model(
            scope, SQLiteMemoryCategoryModel, tablename="memu_memory_categories", metadata=metadata_obj,
        )
        memory_item_model = build_sqlite_table_model(
            scope, SQLiteMemoryItemModel, tablename="memu_memory_items", metadata=metadata_obj,
        )
        category_item_model = build_sqlite_table_model(
            scope, SQLiteCategoryItemModel, tablename="memu_category_items", metadata=metadata_obj,
        )

        class _SQLiteBase(SQLModel):
            __abstract__ = True
            metadata = metadata_obj

        models = _schema.SQLiteSQLAModels(
            Base=_SQLiteBase,
            Resource=resource_model,
            MemoryCategory=memory_category_model,
            MemoryItem=memory_item_model,
            CategoryItem=category_item_model,
        )
        _schema._MODEL_CACHE[scope] = models
        return models

    _schema.get_sqlite_sqlalchemy_models = _patched_get_models
    _sqlite_mod.get_sqlite_sqlalchemy_models = _patched_get_models


def init_mcp_server(service: MemoryService) -> Any:
    """Bind a MemoryService instance to the MCP server."""
    global _service
    _apply_compat_patches(service)
    _service = service
    return mcp_server


def _get_service() -> MemoryService:
    if _service is None:
        msg = "MemoryService not initialized. Call init_mcp_server() or use the memu-mcp CLI."
        raise RuntimeError(msg)
    return _service


def _build_scope(
    user_id: str,
    agent_id: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    scope: dict[str, Any] = {"user_id": user_id}
    if agent_id:
        scope["agent_id"] = agent_id
    if session_id:
        scope["session_id"] = session_id
    return scope


def _json(result: Any) -> str:
    return json.dumps(result, default=str, ensure_ascii=False)


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------


@mcp_server.tool()
async def memorize(
    content: str,
    user_id: str,
    modality: str = "conversation",
    agent_id: str | None = None,
    session_id: str | None = None,
) -> str:
    """Save a conversation, document, or piece of knowledge to memory.

    Args:
        content: The text content to memorize.
        user_id: User identifier for scoping.
        modality: Content type - "conversation", "document", "image", "video", or "audio".
        agent_id: Optional agent identifier for multi-agent scoping.
        session_id: Optional session identifier for session scoping.
    """
    service = _get_service()
    scope = _build_scope(user_id, agent_id, session_id)

    filename = f"memu_mcp_{uuid.uuid4()}.txt"
    file_path = os.path.join(tempfile.gettempdir(), filename)
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        result = await service.memorize(
            resource_url=file_path,
            modality=modality,
            user=scope,
        )
        return _json(result)
    finally:
        if os.path.exists(file_path):
            with contextlib.suppress(OSError):
                os.remove(file_path)


@mcp_server.tool()
async def retrieve(
    query: str,
    user_id: str,
    agent_id: str | None = None,
    session_id: str | None = None,
) -> str:
    """Search for relevant memories based on a query.

    Args:
        query: The search query to find relevant memories.
        user_id: User identifier for scoping.
        agent_id: Optional agent identifier for multi-agent scoping.
        session_id: Optional session identifier for session scoping.
    """
    service = _get_service()
    scope = _build_scope(user_id, agent_id, session_id)
    result = await service.retrieve(
        queries=[{"role": "user", "content": {"text": query}}],
        where=scope,
    )
    return _json(result)


@mcp_server.tool()
async def list_memories(
    user_id: str,
    agent_id: str | None = None,
    session_id: str | None = None,
) -> str:
    """List all stored memory items for a user.

    Args:
        user_id: User identifier for scoping.
        agent_id: Optional agent identifier for multi-agent scoping.
        session_id: Optional session identifier for session scoping.
    """
    service = _get_service()
    scope = _build_scope(user_id, agent_id, session_id)
    result = await service.list_memory_items(where=scope)
    return _json(result)


@mcp_server.tool()
async def list_categories(
    user_id: str,
    agent_id: str | None = None,
    session_id: str | None = None,
) -> str:
    """List all memory categories for a user.

    Args:
        user_id: User identifier for scoping.
        agent_id: Optional agent identifier for multi-agent scoping.
        session_id: Optional session identifier for session scoping.
    """
    service = _get_service()
    scope = _build_scope(user_id, agent_id, session_id)
    result = await service.list_memory_categories(where=scope)
    return _json(result)


@mcp_server.tool()
async def create_memory(
    content: str,
    user_id: str,
    memory_type: MemoryType = "profile",
    categories: list[str] | None = None,
    agent_id: str | None = None,
    session_id: str | None = None,
) -> str:
    """Manually create a memory item.

    Args:
        content: The memory content to store.
        user_id: User identifier for scoping.
        memory_type: Type of memory - "profile", "event", "knowledge", "behavior", "skill", or "tool".
        categories: List of category names to assign the memory to.
        agent_id: Optional agent identifier for multi-agent scoping.
        session_id: Optional session identifier for session scoping.
    """
    service = _get_service()
    scope = _build_scope(user_id, agent_id, session_id)
    result = await service.create_memory_item(
        memory_type=memory_type,
        memory_content=content,
        memory_categories=categories or [],
        user=scope,
    )
    return _json(result)


@mcp_server.tool()
async def update_memory(
    memory_id: str,
    user_id: str,
    content: str | None = None,
    memory_type: MemoryType | None = None,
    categories: list[str] | None = None,
    agent_id: str | None = None,
    session_id: str | None = None,
) -> str:
    """Update an existing memory item.

    Args:
        memory_id: The ID of the memory item to update.
        user_id: User identifier for scoping.
        content: New memory content (optional).
        memory_type: New memory type (optional) - "profile", "event", "knowledge", "behavior", "skill", or "tool".
        categories: New list of category names (optional).
        agent_id: Optional agent identifier for multi-agent scoping.
        session_id: Optional session identifier for session scoping.
    """
    service = _get_service()
    scope = _build_scope(user_id, agent_id, session_id)
    result = await service.update_memory_item(
        memory_id=memory_id,
        memory_type=memory_type,
        memory_content=content,
        memory_categories=categories,
        user=scope,
    )
    return _json(result)


@mcp_server.tool()
async def delete_memory(
    memory_id: str,
    user_id: str,
    agent_id: str | None = None,
    session_id: str | None = None,
) -> str:
    """Delete a specific memory item by ID.

    Args:
        memory_id: The ID of the memory item to delete.
        user_id: User identifier for scoping.
        agent_id: Optional agent identifier for multi-agent scoping.
        session_id: Optional session identifier for session scoping.
    """
    service = _get_service()
    scope = _build_scope(user_id, agent_id, session_id)
    result = await service.delete_memory_item(
        memory_id=memory_id,
        user=scope,
    )
    return _json(result)


@mcp_server.tool()
async def clear_memory(
    user_id: str,
    agent_id: str | None = None,
    session_id: str | None = None,
) -> str:
    """Clear all memories for a user. This action is irreversible.

    Args:
        user_id: User identifier for scoping.
        agent_id: Optional agent identifier for multi-agent scoping.
        session_id: Optional session identifier for session scoping.
    """
    service = _get_service()
    scope = _build_scope(user_id, agent_id, session_id)
    result = await service.clear_memory(where=scope)
    return _json(result)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _resolve(cli_value: str | None, env_key: str, default: str | None = None) -> str | None:
    """Resolve a config value: CLI arg > env var > default."""
    if cli_value is not None:
        return cli_value
    return os.environ.get(env_key, default)


def _build_database_config(db: str, db_path: str | None, db_dsn: str | None) -> dict[str, Any]:
    if db == "sqlite":
        dsn = db_path or "sqlite:///memu.db"
        if not dsn.startswith("sqlite"):
            dsn = f"sqlite:///{dsn}"
        prefix = "sqlite:///"
        if dsn.startswith(prefix):
            raw_path = dsn[len(prefix):]
            expanded = os.path.expanduser(raw_path)
            parent = os.path.dirname(os.path.abspath(expanded))
            os.makedirs(parent, exist_ok=True)
            dsn = f"{prefix}{expanded}"
        return {
            "metadata_store": {"provider": "sqlite", "dsn": dsn},
        }
    if db == "postgres":
        if not db_dsn:
            msg = "PostgreSQL requires --db-dsn or MEMU_DB_DSN"
            raise ValueError(msg)
        return {
            "metadata_store": {"provider": "postgres", "dsn": db_dsn},
        }
    return {"metadata_store": {"provider": "inmemory"}}


def main() -> None:
    """CLI entry point for the memU MCP server."""
    import argparse

    with contextlib.suppress(ImportError):
        from dotenv import load_dotenv

        load_dotenv()

    parser = argparse.ArgumentParser(
        description="memU MCP Server - Expose MemoryService as MCP tools",
    )
    parser.add_argument("--api-key", default=None, help="LLM API key (env: OPENAI_API_KEY)")
    parser.add_argument("--base-url", default=None, help="LLM base URL (env: OPENAI_BASE_URL)")
    parser.add_argument("--chat-model", default=None, help="Chat model name (env: MEMU_CHAT_MODEL)")
    parser.add_argument("--embed-model", default=None, help="Embedding model name (env: MEMU_EMBED_MODEL)")
    parser.add_argument(
        "--embed-api-key", default=None, help="Embedding API key, if different from --api-key (env: MEMU_EMBED_API_KEY)"
    )
    parser.add_argument(
        "--embed-base-url",
        default=None,
        help="Embedding base URL, if different from --base-url (env: MEMU_EMBED_BASE_URL)",
    )
    parser.add_argument(
        "--db",
        default=None,
        choices=["inmemory", "sqlite", "postgres"],
        help="Storage backend (env: MEMU_DB, default: inmemory)",
    )
    parser.add_argument("--db-path", default=None, help="SQLite database path (env: MEMU_DB_PATH)")
    parser.add_argument("--db-dsn", default=None, help="PostgreSQL DSN (env: MEMU_DB_DSN)")
    parser.add_argument(
        "--transport",
        default="stdio",
        choices=["stdio", "sse"],
        help="MCP transport (default: stdio)",
    )

    args = parser.parse_args()

    api_key = _resolve(args.api_key, "OPENAI_API_KEY")
    if not api_key:
        parser.error("LLM API key is required. Set --api-key or OPENAI_API_KEY environment variable.")

    base_url = _resolve(args.base_url, "OPENAI_BASE_URL", "https://api.openai.com/v1")
    chat_model = _resolve(args.chat_model, "MEMU_CHAT_MODEL", "gpt-4o-mini")
    embed_model = _resolve(args.embed_model, "MEMU_EMBED_MODEL")
    embed_api_key = _resolve(args.embed_api_key, "MEMU_EMBED_API_KEY")
    embed_base_url = _resolve(args.embed_base_url, "MEMU_EMBED_BASE_URL")
    db = _resolve(args.db, "MEMU_DB", "inmemory") or "inmemory"
    db_path = _resolve(args.db_path, "MEMU_DB_PATH")
    db_dsn = _resolve(args.db_dsn, "MEMU_DB_DSN")

    if db == "sqlite":
        _apply_sqlite_compat_patches()

    llm_default: dict[str, Any] = {
        "api_key": api_key,
        "base_url": base_url,
        "chat_model": chat_model,
    }
    llm_profiles: dict[str, Any] = {"default": llm_default}
    if embed_model or embed_api_key or embed_base_url:
        llm_profiles["embedding"] = {
            "api_key": embed_api_key or api_key,
            "base_url": embed_base_url or base_url,
            "embed_model": embed_model,
        }

    database_config = _build_database_config(db, db_path, db_dsn)

    service = MemoryService(
        llm_profiles=llm_profiles,
        database_config=database_config,
        user_config={"model": MCPUserModel},
    )
    init_mcp_server(service)

    logger.info("Starting memU MCP server (transport=%s, db=%s)", args.transport, db)
    mcp_server.run(transport=args.transport)
