"""Tool layer (matrix row C6/architecture layer 4): MCP tool servers.

Each tool server is an **independent process** speaking the Model Context
Protocol over stdio (JSON-RPC 2.0 with content-length framing). The backend
spawns configured servers and bridges their tools into the agent's tool map —
``mcp.<server>.<tool>``. Availability is advertised at runtime
(``/api/capabilities``) and a missing/failed server degrades to a typed
"unavailable" message, never a crash.

Deliberately stdlib-only: the wire protocol subset implemented here
(``initialize``, ``tools/list``, ``tools/call``) is enough to interoperate
without any MCP SDK dependency.
"""