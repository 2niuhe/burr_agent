"""Agent package implementing a modular V4-style architecture.

Modules:
- state: Pydantic models for application and step state
- tools_manager: MCP tool discovery and invocation helper
- actions: Burr actions implementing prompt/router/planner/executor/etc.
- app: Application builder wiring actions into a graph
"""


