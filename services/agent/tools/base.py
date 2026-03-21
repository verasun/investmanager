"""Tool base classes and result types."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from pydantic import BaseModel


class ToolResult(BaseModel):
    """Result from tool execution."""

    success: bool = True
    data: Any = None
    error: Optional[str] = None
    metadata: dict = {}

    class Config:
        arbitrary_types_allowed = True


class BaseTool(ABC):
    """Base class for all agent tools.

    Tools are the building blocks that the agent can use to accomplish tasks.
    Each tool should have:
    - A unique name
    - A description for the LLM to understand when to use it
    - JSON Schema for parameters
    - An async execute method
    """

    name: str
    description: str
    parameters: dict  # JSON Schema for parameters
    timeout: int = 60  # Default timeout in seconds

    @abstractmethod
    async def execute(self, **params) -> ToolResult:
        """Execute the tool with given parameters.

        Args:
            **params: Tool-specific parameters

        Returns:
            ToolResult with success status, data, and optional error
        """
        pass

    def to_openai_tool(self) -> dict:
        """Convert to OpenAI function calling format.

        Returns:
            Dict in OpenAI tool format
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def to_anthropic_tool(self) -> dict:
        """Convert to Anthropic tool format.

        Returns:
            Dict in Anthropic tool format
        """
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }

    def validate_params(self, params: dict) -> tuple[bool, Optional[str]]:
        """Validate parameters against schema.

        Args:
            params: Parameters to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        import jsonschema
        from jsonschema import validate, ValidationError

        try:
            validate(instance=params, schema=self.parameters)
            return True, None
        except ValidationError as e:
            return False, str(e)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}: {self.name}>"


@dataclass
class ToolInfo:
    """Information about a tool for display/debugging."""

    name: str
    description: str
    parameters: dict
    timeout: int

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "timeout": self.timeout,
        }