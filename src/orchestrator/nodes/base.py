"""Base class for task nodes."""

import json
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional

from loguru import logger


class TaskNode(ABC):
    """
    Abstract base class for task nodes.

    Task nodes are independent execution units that perform
    specific operations (data fetch, analysis, backtest, etc.).

    Each node:
    - Receives input via stdin as JSON
    - Returns output via stdout as JSON
    - Logs to stderr
    - Can be run as a standalone script
    """

    @abstractmethod
    def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """
        Execute the task.

        Args:
            input_data: Input parameters from the orchestrator

        Returns:
            Output data to pass to dependent tasks
        """
        pass

    def validate_input(self, input_data: dict[str, Any]) -> bool:
        """
        Validate input data before execution.

        Override this method to add custom validation.

        Args:
            input_data: Input parameters

        Returns:
            True if valid, False otherwise
        """
        return True

    def setup(self) -> None:
        """
        Setup method called before execute.

        Override to initialize resources, load configurations, etc.
        """
        pass

    def teardown(self) -> None:
        """
        Teardown method called after execute.

        Override to clean up resources.
        """
        pass

    def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """
        Full execution lifecycle: setup -> execute -> teardown.

        Args:
            input_data: Input parameters

        Returns:
            Output data with success status
        """
        try:
            # Validate
            if not self.validate_input(input_data):
                return {
                    "success": False,
                    "error": "Input validation failed",
                }

            # Setup
            self.setup()

            # Execute
            result = self.execute(input_data)

            return {
                "success": True,
                "output": result,
            }

        except Exception as e:
            logger.exception(f"Task execution failed: {e}")
            return {
                "success": False,
                "error": str(e),
            }

        finally:
            self.teardown()

    @classmethod
    def main(cls) -> None:
        """
        CLI entry point.

        Reads JSON from stdin, executes task, writes JSON to stdout.
        """
        # Configure logging to stderr
        logger.remove()
        logger.add(sys.stderr, level="INFO")

        # Read input from stdin
        try:
            input_json = sys.stdin.read()
            input_data = json.loads(input_json)
        except json.JSONDecodeError as e:
            error_output = json.dumps({
                "success": False,
                "error": f"Invalid JSON input: {e}",
            })
            print(error_output)
            sys.exit(1)

        # Create and run node
        node = cls()
        result = node.run(input_data.get("input", input_data))

        # Write output to stdout
        print(json.dumps(result, default=str))

    def _resolve_path(self, path: str, base_dir: Optional[Path] = None) -> Path:
        """
        Resolve a path, handling task:// URLs.

        Task URLs reference output from previous tasks:
        task://{task_id}/output -> data/task_outputs/{task_id}/

        Args:
            path: Path or task:// URL
            base_dir: Base directory for relative paths

        Returns:
            Resolved Path object
        """
        if path.startswith("task://"):
            # Extract task ID
            parts = path[7:].split("/")
            task_id = parts[0]
            subpath = "/".join(parts[1:]) if len(parts) > 1 else ""

            # Build output path
            output_dir = Path("data/task_outputs") / task_id
            if subpath:
                return output_dir / subpath
            return output_dir

        # Regular path
        path_obj = Path(path)
        if path_obj.is_absolute():
            return path_obj

        if base_dir:
            return base_dir / path_obj

        return path_obj

    def _ensure_output_dir(self, task_id: str) -> Path:
        """
        Ensure output directory exists for a task.

        Args:
            task_id: Task identifier

        Returns:
            Path to output directory
        """
        output_dir = Path("data/task_outputs") / task_id
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    def _save_output_file(
        self,
        task_id: str,
        filename: str,
        content: Any,
        format: str = "json",
    ) -> Path:
        """
        Save output to a file in the task output directory.

        Args:
            task_id: Task identifier
            filename: Output filename
            content: Content to save
            format: File format (json, text, binary)

        Returns:
            Path to saved file
        """
        output_dir = self._ensure_output_dir(task_id)
        output_path = output_dir / filename

        if format == "json":
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(content, f, default=str, indent=2)
        elif format == "binary":
            with open(output_path, "wb") as f:
                f.write(content)
        else:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(content)

        logger.info(f"Saved output to {output_path}")
        return output_path

    def _load_input_file(self, path: str, format: str = "json") -> Any:
        """
        Load input from a file.

        Args:
            path: Path to input file
            format: File format (json, text, binary)

        Returns:
            Loaded content
        """
        input_path = self._resolve_path(path)

        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        if format == "json":
            with open(input_path, "r", encoding="utf-8") as f:
                return json.load(f)
        elif format == "binary":
            with open(input_path, "rb") as f:
                return f.read()
        else:
            with open(input_path, "r", encoding="utf-8") as f:
                return f.read()


def run_node(node_class: type[TaskNode]) -> None:
    """
    Run a node as a standalone script.

    Usage:
        if __name__ == "__main__":
            run_node(MyNode)
    """
    node_class.main()