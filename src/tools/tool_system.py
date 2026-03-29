from typing import Any, Dict, List, Optional

class Tool:
    """Represents a single callable tool for the AI."""
    def __init__(self, name: str, description: str, parameters: Dict[str, Any], handler):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.handler = handler

    def to_declaration(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters
        }

    async def execute(self, args: Dict[str, Any]) -> Any:
        return await self.handler(**args)


class ToolRegistry:
    """Central registry for all tools."""
    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def get_declarations(self) -> List[Dict[str, Any]]:
        return [tool.to_declaration() for tool in self._tools.values()]
