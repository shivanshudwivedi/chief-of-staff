# Live MCP connectors

The app ships with a replayable simulated workspace. To work against real services, connect operator-configured MCP servers over Streamable HTTP. The adapter implements discovery, tool schemas, validation, invocation, and result/error logging using the official MCP Python SDK. This release supports tool calls, not MCP resources, prompts, OAuth browser flows, stdio, or server-triggered sampling.

## Try a local live connector

```bash
uv run python scripts/example_mcp.py
# In another terminal, from this repository:
mkdir -p data
cp docs/connectors.example.json data/connectors.json
```

Set `COS_MCP_CONFIG=data/connectors.json` in `.env`, restart the server, and open Connectors. Workspace notes should show Connected with two tools. In OpenAI mode, ask “Read my Workspace notes” or “Create a Workspace note with the content: Finish the launch memo.” The write is proposed in Approvals; it only creates the note after approval. Notes persist in a separate SQLite database.

## Connect your services

Use a Streamable HTTP MCP endpoint supplied by a service you trust:

```json
{
  "servers": [{
    "name": "My workspace",
    "url": "https://your-server.example/mcp",
    "token_env": "WORKSPACE_MCP_TOKEN",
    "read_only_tools": ["search", "list_events"]
  }]
}
```

Keep `WORKSPACE_MCP_TOKEN` in `.env`; credentials do not belong in JSON or URLs. HTTPS is required except on loopback. Restart to rediscover tools; the dashboard shows connection errors without exposing tokens or URLs. At most eight servers and 100 tools per server are discovered, with a five-page limit. Missing/offline connectors do not break the local app.

Every remote tool is treated as a mutation unless its exact remote name appears in `read_only_tools`. Review the server's behavior before exempting a tool: model names and MCP `readOnlyHint` annotations are not used as authorization. The app validates inputs against the discovered schema, proposes mutations, and never blindly retries a failed remote call.

Tool search includes relevant live tool descriptions in addition to the inherited capability taxonomy. A run initially offers at most 12 live schemas, expandable to 20 through `find_tools`. Names are connector-prefixed and hashed to prevent collisions. Responses are stored in the execution journal and bounded before going into model context.

Connection sessions are opened per discovery or invocation for simple lifecycle management. This adds overhead compared with pooling. The adapter uses bounded timeouts, does not follow server instructions as system instructions, and does not implement automatic reconnect-and-retry for mutations. Server-specific authorization, rate limits, reliability and permission scope remain the operator's responsibility.

Implementation reference: [official MCP Python SDK, v1 maintenance line](https://github.com/modelcontextprotocol/python-sdk/tree/v1.x). The dependency stays below version 2 to keep the tested API contract.
