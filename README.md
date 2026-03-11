# memu-mcp

MCP (Model Context Protocol) server for [memU](https://github.com/NevaMind-AI/memU) — expose MemoryService as MCP tools with cloud authentication.

## Installation

```bash
uvx --from git+https://github.com/De13ruyne/memU-mcp@local-sdk memu-mcp
```

## Authentication

memu-mcp requires a **memU API key** obtained from the [memU platform](https://app.memu.so/).

1. Sign up at [memu.so](https://memu.so) and navigate to the API Keys section.
2. Create a new API key for your project.
3. Pass the key to the MCP server via the `MEMU_API_KEY` environment variable or `--memu-api-key` CLI argument.

Every tool call is validated against the memU cloud API (`api.memu.so`). Tokens are cached locally for 5 minutes to minimize latency.

## Usage

### CLI

```bash
# Minimal — requires MEMU_API_KEY and OPENAI_API_KEY env vars
memu-mcp

# Explicit arguments
memu-mcp \
  --memu-api-key <your-memu-token> \
  --api-key <your-openai-key> \
  --db sqlite \
  --db-path ./memu.db \
  --transport stdio
```

### MCP Client Configuration

Add to your MCP client config (Cursor, Claude Desktop, etc.):

```json
{
  "mcpServers": {
    "memu": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/De13ruyne/memU-mcp@local-sdk", "memu-mcp"],
      "env": {
        "MEMU_API_KEY": "<your-memu-token>",
        "OPENAI_API_KEY": "<your-openai-key>"
      }
    }
  }
}
```

### Programmatic

```python
from memu.app.service import MemoryService
from memu_mcp import init_mcp_server, mcp_server

service = MemoryService(...)
init_mcp_server(service)
mcp_server.run(transport="stdio")
```

## Environment Variables

| Variable | Description | Required |
|---|---|---|
| `MEMU_API_KEY` | memU OAuth token for cloud authentication | Yes |
| `MEMU_API_BASE_URL` | Custom memU API base URL (default: `https://api.memu.so`) | No |
| `OPENAI_API_KEY` | OpenAI-compatible API key for LLM | Yes |
| `OPENAI_BASE_URL` | LLM base URL (default: `https://api.openai.com/v1`) | No |
| `MEMU_CHAT_MODEL` | Chat model name (default: `gpt-4o-mini`) | No |
| `MEMU_EMBED_MODEL` | Embedding model name | No |
| `MEMU_EMBED_API_KEY` | Separate API key for embeddings | No |
| `MEMU_EMBED_BASE_URL` | Separate base URL for embeddings | No |
| `MEMU_DB` | Storage backend: `inmemory`, `sqlite`, `postgres` | No |
| `MEMU_DB_PATH` | SQLite database file path | No |
| `MEMU_DB_DSN` | PostgreSQL connection string | No |

## Tools

| Tool | Description |
|---|---|
| `memorize` | Save conversations, documents, or knowledge to memory |
| `retrieve` | Search for relevant memories based on a query |
| `list_memories` | List all stored memory items for a user |
| `list_categories` | List all memory categories for a user |
| `create_memory` | Manually create a memory item |
| `update_memory` | Update an existing memory item |
| `delete_memory` | Delete a specific memory item |
| `clear_memory` | Clear all memories for a user (irreversible) |

## Development

```bash
# Install dev dependencies
uv sync --group dev

# Run tests
pytest

# Lint
ruff check src tests
mypy src tests
```

## License

Apache-2.0
