"""Executor - Execute plans and manage tool calls."""

import asyncio
import time
import uuid
from typing import Any, Optional

from loguru import logger

from ..planner import ExecutionPlan, Step, StepStatus
from ..tools import ToolResult
from .context import ExecutionContext, ExecutionResult
from .react_loop import ReActLoop


class Executor:
    """Plan executor with ReAct loop support.

    Executes plans step by step, managing parallel execution
    and tool calls.
    """

    def __init__(
        self,
        tool_registry=None,
        llm_provider=None,
        max_iterations: int = 10,
        max_retries: int = 2,
        parallel_execution: bool = True,
    ):
        """Initialize executor.

        Args:
            tool_registry: Registry of available tools
            llm_provider: LLM provider for reasoning
            max_iterations: Maximum ReAct iterations
            max_retries: Maximum retries for failed steps
            parallel_execution: Whether to execute independent steps in parallel
        """
        self.tool_registry = tool_registry
        self.llm_provider = llm_provider
        self.max_iterations = max_iterations
        self.max_retries = max_retries
        self.parallel_execution = parallel_execution

    def set_tool_registry(self, registry) -> None:
        """Set tool registry."""
        self.tool_registry = registry

    def set_llm_provider(self, provider) -> None:
        """Set LLM provider."""
        self.llm_provider = provider

    async def execute_plan(
        self,
        plan: ExecutionPlan,
        context: ExecutionContext = None,
    ) -> ExecutionResult:
        """Execute an execution plan.

        Args:
            plan: The execution plan
            context: Optional execution context

        Returns:
            ExecutionResult with outcome
        """
        start_time = time.time()

        if context is None:
            context = ExecutionContext(
                task_id=plan.task_id,
                trace_id=f"exec_{uuid.uuid4().hex[:8]}",
            )

        logger.info(f"Executing plan {plan.task_id} with {len(plan.steps)} steps")

        # Execute steps
        retry_count = 0
        while not plan.is_complete() and retry_count < self.max_retries:
            # Get ready steps
            ready_steps = plan.get_ready_steps()

            if not ready_steps:
                if plan.has_failures():
                    logger.warning(f"Plan {plan.task_id} has failures but no ready steps")
                    break
                # No ready steps but not complete - might be circular dependency
                logger.error(f"Plan {plan.task_id} has no ready steps but is not complete")
                break

            # Execute ready steps
            if self.parallel_execution and len(ready_steps) > 1:
                # Parallel execution
                results = await asyncio.gather(
                    *[self.execute_step(step, context) for step in ready_steps],
                    return_exceptions=True,
                )

                for step, result in zip(ready_steps, results):
                    if isinstance(result, Exception):
                        step.mark_failed(str(result))
                    elif isinstance(result, ToolResult):
                        if result.success:
                            step.mark_completed(result.data)
                            context.set_step_result(step.id, result.data)
                        else:
                            step.mark_failed(result.error or "Unknown error")
            else:
                # Sequential execution
                for step in ready_steps:
                    result = await self.execute_step(step, context)
                    if result.success:
                        step.mark_completed(result.data)
                        context.set_step_result(step.id, result.data)
                    else:
                        step.mark_failed(result.error or "Unknown error")

            # Check for failures and potentially retry
            if plan.has_failures() and retry_count < self.max_retries - 1:
                retry_count += 1
                logger.info(f"Retrying failed steps (attempt {retry_count})")
                # Reset failed steps for retry
                for step in plan.get_failed_steps():
                    step.status = StepStatus.PENDING
                    step.error = None

        # Calculate duration
        duration_ms = int((time.time() - start_time) * 1000)

        # Build result
        success = plan.is_complete() and not plan.has_failures()
        final_output = await self._synthesize_output(plan, context)

        return ExecutionResult(
            success=success,
            task_id=plan.task_id,
            steps=plan.steps,
            final_output=final_output,
            error=None if success else "Some steps failed",
            duration_ms=duration_ms,
            context=context,
        )

    async def execute_step(
        self,
        step: Step,
        context: ExecutionContext,
    ) -> ToolResult:
        """Execute a single step.

        Args:
            step: The step to execute
            context: Execution context

        Returns:
            ToolResult from execution
        """
        logger.info(f"Executing step {step.id}: {step.description}")
        step.mark_running()

        # Resolve parameters from context
        params = self._resolve_params(step.parameters, context)

        if step.tool_name:
            # Tool execution
            if not self.tool_registry:
                return ToolResult(
                    success=False,
                    error="No tool registry available",
                )

            if not self.tool_registry.has(step.tool_name):
                return ToolResult(
                    success=False,
                    error=f"Unknown tool: {step.tool_name}",
                )

            return await self.tool_registry.execute(step.tool_name, params)

        else:
            # LLM reasoning step
            return await self._llm_reasoning(step, context)

    async def _llm_reasoning(
        self,
        step: Step,
        context: ExecutionContext,
    ) -> ToolResult:
        """Execute an LLM reasoning step.

        Args:
            step: The step with reasoning task
            context: Execution context with previous results

        Returns:
            ToolResult with reasoning output
        """
        if not self.llm_provider:
            return ToolResult(
                success=False,
                error="No LLM provider available",
            )

        # Build prompt with context
        prompt = self._build_reasoning_prompt(step, context)

        try:
            response = await self.llm_provider.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=1000,
            )

            return ToolResult(
                success=True,
                data={"reasoning": response.content},
                metadata={"model": response.model},
            )

        except Exception as e:
            logger.error(f"LLM reasoning failed: {e}")
            return ToolResult(
                success=False,
                error=str(e),
            )

    def _build_reasoning_prompt(self, step: Step, context: ExecutionContext) -> str:
        """Build prompt for LLM reasoning step."""
        lines = [
            f"任务: {step.description}",
            "",
            "上下文信息:",
        ]

        # Add results from dependent steps
        for dep_id in step.dependencies:
            result = context.get_step_result(dep_id)
            if result:
                lines.append(f"### {dep_id} 结果:")
                lines.append(self._format_result(result))
                lines.append("")

        lines.append("请分析以上信息并给出结论:")

        return "\n".join(lines)

    def _format_result(self, result: Any, max_length: int = 1000) -> str:
        """Format a result for prompt."""
        if isinstance(result, str):
            return result[:max_length]

        if isinstance(result, dict):
            import json
            try:
                s = json.dumps(result, ensure_ascii=False, indent=2)
                return s[:max_length]
            except Exception:
                return str(result)[:max_length]

        return str(result)[:max_length]

    def _resolve_params(self, params: dict, context: ExecutionContext) -> dict:
        """Resolve parameter values from context.

        Handles parameter references like $step_id.field
        """
        resolved = {}

        for key, value in params.items():
            if isinstance(value, str) and value.startswith("$"):
                # Reference to context variable
                ref = value[1:]
                parts = ref.split(".")

                # Try to resolve
                if len(parts) == 1:
                    # Simple variable reference
                    resolved[key] = context.get_variable(parts[0])
                elif len(parts) == 2:
                    # Step result reference
                    step_result = context.get_step_result(parts[0])
                    if isinstance(step_result, dict):
                        resolved[key] = step_result.get(parts[1])
                    else:
                        resolved[key] = step_result
                else:
                    resolved[key] = value  # Keep as-is if can't resolve
            else:
                resolved[key] = value

        return resolved

    async def _synthesize_output(
        self,
        plan: ExecutionPlan,
        context: ExecutionContext,
    ) -> str:
        """Synthesize final output from execution results."""
        # Get all step results
        all_results = context.get_all_results()

        if not all_results:
            return "执行完成，但无结果"

        # Try to find a synthesis step or use LLM
        synthesis_step = None
        for step in plan.steps:
            if step.tool_name is None and step.status == StepStatus.COMPLETED:
                synthesis_step = step

        if synthesis_step and synthesis_step.id in all_results:
            result = all_results[synthesis_step.id]
            if isinstance(result, dict):
                return result.get("reasoning", str(result))
            return str(result)

        # Use ReAct loop to synthesize
        if self.llm_provider:
            react = ReActLoop(
                tool_registry=self.tool_registry,
                llm_provider=self.llm_provider,
                max_iterations=3,
            )

            # Build synthesis task
            task = f"总结以下执行结果:\n{self._format_all_results(all_results)}"
            return await react.run(task)

        # Fallback: format all results
        return self._format_all_results(all_results)

    def _format_all_results(self, results: dict) -> str:
        """Format all results for output."""
        lines = []
        for step_id, result in results.items():
            lines.append(f"### {step_id}")
            lines.append(self._format_result(result))
            lines.append("")
        return "\n".join(lines)


# Global executor instance
_executor: Optional[Executor] = None


def get_executor() -> Executor:
    """Get or create the global executor instance."""
    global _executor
    if _executor is None:
        _executor = Executor()
    return _executor