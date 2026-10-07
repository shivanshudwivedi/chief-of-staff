"""Opt-in Streamable HTTP MCP connectors. Configuration is operator-owned, never model-written."""

from __future__ import annotations
import asyncio
import hashlib
import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse
import jsonschema
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


class Connectors:
    def __init__(self):
        self.tools = {}
        self.servers = []

    async def request(self, server, operation, name=None, args=None):
        headers = {}
        env = server.get("token_env")
        if env:
            if not os.getenv(env):
                raise ValueError("Configured MCP token environment variable is missing")
            headers["Authorization"] = "Bearer " + os.environ[env]
        async with streamablehttp_client(server["url"], headers=headers, timeout=10, sse_read_timeout=20) as (
            read,
            write,
            _,
        ):
            async with ClientSession(read, write) as session:
                await session.initialize()
                if operation == "list":
                    tools, cursor = [], None
                    for _ in range(5):
                        page = await session.list_tools(cursor=cursor)
                        tools.extend(page.tools)
                        cursor = page.nextCursor
                        if not cursor:
                            break
                    return tools[:100]
                result = await session.call_tool(name, arguments=args)
                if result.isError:
                    text = " ".join(getattr(c, "text", "") for c in result.content)
                    raise ValueError("MCP tool failed: " + text[:1000])
                return result.model_dump(mode="json", exclude_none=True)

    def discover(self):
        config = os.getenv("COS_MCP_CONFIG", "")
        if not config:
            return
        try:
            items = json.loads(Path(config).read_text())["servers"]
            if not isinstance(items, list) or len(items) > 8:
                raise ValueError("Configure at most eight servers")
        except Exception:
            self.servers = [{"name": "MCP configuration", "status": "invalid", "tool_count": 0}]
            return
        for server in items:
            name = str(server.get("name", "MCP"))[:80]
            status = {"name": name, "status": "offline", "tool_count": 0}
            self.servers.append(status)
            try:
                parsed = urlparse(server["url"])
                if parsed.username or parsed.password or parsed.query or parsed.fragment:
                    raise ValueError("MCP credentials must be provided through token_env")
                if parsed.scheme != "https" and not (
                    parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
                ):
                    raise ValueError("Use HTTPS or HTTP loopback")
                tools = asyncio.run(asyncio.wait_for(self.request(server, "list"), timeout=25))
                slug = re.sub(r"[^a-zA-Z0-9_]", "_", name)[:18]
                for tool in tools:
                    digest = hashlib.sha256((name + server["url"] + tool.name).encode()).hexdigest()[:8]
                    alias = "mcp_" + slug + "_" + re.sub(r"[^a-zA-Z0-9_]", "_", tool.name)[:28] + "_" + digest
                    self.tools[alias] = {
                        "server": server,
                        "remote": tool.name,
                        "read_only": tool.name in server.get("read_only_tools", []),
                        "schema": {
                            "type": "function",
                            "name": alias,
                            "strict": False,
                            "description": f"LIVE connector {name}: {tool.description or tool.name}"[:1500],
                            "parameters": tool.inputSchema,
                        },
                    }
                status.update(status="connected", tool_count=len(tools))
            except Exception as exc:
                # Never expose credential-bearing URLs or response headers in dashboard errors.
                status["error"] = (
                    type(exc).__name__ + ": connector unavailable; verify config and authentication"
                )

    def select(self, query, limit=12):
        words = set(re.findall(r"[a-z0-9]+", query.lower()))

        def score(item):
            description = item[1]["schema"]["description"].lower() + " " + item[1]["remote"].lower()
            return sum(len(w) > 2 and w in description for w in words)

        scored = sorted(self.tools.items(), key=score, reverse=True)
        return [name for name, _ in scored if score((name, self.tools[name])) > 0][:limit]

    def schemas(self, names):
        return [self.tools[n]["schema"] for n in names if n in self.tools]

    def validate(self, name, args):
        jsonschema.validate(args, self.tools[name]["schema"]["parameters"])

    def invoke(self, name, args, *, timeout=25):
        entry = self.tools[name]
        return asyncio.run(
            asyncio.wait_for(
                self.request(entry["server"], "call", entry["remote"], args), timeout=min(25, timeout)
            )
        )
