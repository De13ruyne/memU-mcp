# memu-mcp

MCP (Model Context Protocol) server for [memU](https://memu.so) — expose the memU Cloud API as MCP tools.

## Installation

```bash
uvx --from git+https://github.com/De13ruyne/memU-mcp memu-mcp
```

## Authentication

memu-mcp requires a **memU API key** obtained from the [memU platform](https://app.memu.so/).

1. Sign up at [memu.so](https://memu.so) and navigate to the API Keys section.
2. Create a new API key for your project.
3. Pass the key to the MCP server via the `MEMU_API_KEY` environment variable or `--memu-api-key` CLI argument.

All tool calls are authenticated via Bearer token against the memU Cloud API (`api.memu.so`).

## Usage

### CLI

```bash
# Requires MEMU_API_KEY env var
memu-mcp

# Explicit arguments
memu-mcp \
  --memu-api-key <your-memu-token> \
  --transport stdio
```

### MCP Client Configuration

Add to your MCP client config (Cursor, Claude Desktop, etc.):

```json
{
  "mcpServers": {
    "memu": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/De13ruyne/memU-mcp", "memu-mcp"],
      "env": {
        "MEMU_API_KEY": "<your-memu-token>"
      }
    }
  }
}
```

### Programmatic

```python
from memu_mcp import MemuCloudClient, init_mcp_server, mcp_server

client = MemuCloudClient(api_key="your-key")
init_mcp_server(client)
mcp_server.run(transport="stdio")
```

## Environment Variables

| Variable | Description | Required |
|---|---|---|
| `MEMU_API_KEY` | memU API key for cloud authentication | Yes |
| `MEMU_API_BASE_URL` | Custom memU API base URL (default: `https://api.memu.so`) | No |

## Tools

| Tool | Description |
|---|---|
| `memorize` | Save a conversation to memU cloud memory (async, returns task_id) |
| `get_task_status` | Check the status of an async memorization task |
| `retrieve` | Search for relevant memories based on a query |
| `list_categories` | List all memory categories for a user |
| `delete_memory` | Delete a specific memory item by ID |
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
