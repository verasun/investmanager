"""Agent Service - Core agent implementation."""

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from loguru import logger
from pydantic import BaseModel

from .tools import ToolRegistry, get_tool_registry, register_default_tools
from .planner import Planner, ExecutionPlan, get_planner
from .executor import Executor, ExecutionContext, ExecutionResult, get_executor
from .reflector import Reflector, ReflectionResult, get_reflector
from .memory import AgentMemory, get_agent_memory
from .scheduler import AutonomousScheduler, get_scheduler


@dataclass
class AgentResult:
    """Result from agent execution."""

    trace_id: str
    success: bool
    output: str
    steps: list = field(default_factory=list)
    duration_ms: int = 0
    plan: Optional[ExecutionPlan] = None
    reflection: Optional[ReflectionResult] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "trace_id": self.trace_id,
            "success": self.success,
            "output": self.output,
            "steps": [s.to_dict() if hasattr(s, "to_dict") else str(s) for s in self.steps],
            "duration_ms": self.duration_ms,
        }


class AgentService:
    """Main agent service integrating all components.

    Flow:
    1. Receive user request
    2. Find relevant patterns from memory
    3. Generate execution plan
    4. Execute plan with tools
    5. Reflect on results
    6. Learn from execution
    7. Return result
    """

    def __init__(
        self,
        llm_provider=None,
        tool_registry: ToolRegistry = None,
        planner: Planner = None,
        executor: Executor = None,
        reflector: Reflector = None,
        memory: AgentMemory = None,
        scheduler: AutonomousScheduler = None,
        max_retries: int = 2,
    ):
        """Initialize agent service.

        Args:
            llm_provider: LLM provider for reasoning
            tool_registry: Tool registry
            planner: Task planner
            executor: Plan executor
            reflector: Result reflector
            memory: Agent memory
            scheduler: Autonomous scheduler
            max_retries: Maximum retry attempts
        """
        self.llm_provider = llm_provider

        # Initialize or use provided components
        self.tools = tool_registry or get_tool_registry()
        self.planner = planner or get_planner()
        self.executor = executor or get_executor()
        self.reflector = reflector or get_reflector()
        self.memory = memory or get_agent_memory()
        self.scheduler = scheduler or get_scheduler()

        self.max_retries = max_retries

        # Set up cross-references
        self._setup_components()

    def _setup_components(self) -> None:
        """Set up cross-references between components."""
        self.planner.set_tool_registry(self.tools)
        self.planner.set_llm_provider(self.llm_provider)

        self.executor.set_tool_registry(self.tools)
        self.executor.set_llm_provider(self.llm_provider)

        self.reflector.set_llm_provider(self.llm_provider)

        self.scheduler.set_agent_service(self)

    def set_llm_provider(self, provider) -> None:
        """Set LLM provider for all components."""
        self.llm_provider = provider
        self.planner.set_llm_provider(provider)
        self.executor.set_llm_provider(provider)
        self.reflector.set_llm_provider(provider)

    def register_tool(self, tool) -> None:
        """Register a tool."""
        self.tools.register(tool)

    async def run(
        self,
        user_request: str,
        user_id: str = None,
        context: dict = None,
    ) -> AgentResult:
        """Run the agent on a user request.

        Args:
            user_request: User's request/goal
            user_id: Optional user ID
            context: Optional context information

        Returns:
            AgentResult with execution outcome
        """
        start_time = time.time()
        trace_id = f"agent_{uuid.uuid4().hex[:8]}"

        logger.info(f"[{trace_id}] Agent processing: {user_request[:50]}...")

        try:
            # 1. Find relevant patterns from memory
            patterns = []
            if user_id:
                try:
                    patterns = await self.memory.find_relevant_patterns(user_request)
                    logger.info(f"[{trace_id}] Found {len(patterns)} relevant patterns")
                except Exception as e:
                    logger.warning(f"[{trace_id}] Pattern search failed: {e}")

            # 2. Generate execution plan
            plan = await self.planner.plan(
                goal=user_request,
                context=context or {},
                patterns=patterns,
            )
            logger.info(f"[{trace_id}] Generated plan with {len(plan.steps)} steps")

            # 3. Execute plan
            exec_context = ExecutionContext(
                task_id=plan.task_id,
                user_id=user_id,
                trace_id=trace_id,
            )

            result = await self.executor.execute_plan(plan, exec_context)
            logger.info(f"[{trace_id}] Execution completed, success={result.success}")

            # 4. Reflect if not fully successful
            reflection = None
            retry_count = 0

            while not result.success and retry_count < self.max_retries:
                reflection = await self.reflector.reflect(plan, result)

                if not await self.reflector.should_retry(reflection, retry_count):
                    break

                # Revise plan and retry
                logger.info(f"[{trace_id}] Retrying (attempt {retry_count + 1})")
                plan = await self.planner.revise(
                    plan,
                    plan.get_failed_steps(),
                    {s.id: s.error for s in plan.get_failed_steps()},
                )

                result = await self.executor.execute_plan(plan, exec_context)
                retry_count += 1

            # 5. Save execution to memory
            if user_id:
                try:
                    await self.memory.save_task(
                        task_id=plan.task_id,
                        user_id=user_id,
                        goal=user_request,
                        plan=plan.to_dict(),
                        status="completed" if result.success else "failed",
                        result=result.to_dict(),
                        success=result.success,
                    )

                    # Learn from execution
                    await self.memory.learn_from_execution(
                        plan.to_dict(),
                        result.to_dict(),
                        result.success,
                    )
                except Exception as e:
                    logger.warning(f"[{trace_id}] Memory save failed: {e}")

            duration_ms = int((time.time() - start_time) * 1000)

            return AgentResult(
                trace_id=trace_id,
                success=result.success,
                output=result.final_output,
                steps=result.steps,
                duration_ms=duration_ms,
                plan=plan,
                reflection=reflection,
            )

        except Exception as e:
            logger.error(f"[{trace_id}] Agent execution failed: {e}")
            duration_ms = int((time.time() - start_time) * 1000)

            return AgentResult(
                trace_id=trace_id,
                success=False,
                output=f"执行失败: {str(e)}",
                duration_ms=duration_ms,
            )

    async def schedule_task(
        self,
        user_id: str,
        name: str,
        prompt: str,
        trigger,
        notify_on_complete: bool = True,
    ):
        """Create a scheduled task.

        Args:
            user_id: User ID
            name: Task name
            prompt: Task prompt
            trigger: Trigger configuration
            notify_on_complete: Whether to notify

        Returns:
            ScheduledTask
        """
        return await self.scheduler.create_task(
            user_id=user_id,
            name=name,
            prompt=prompt,
            trigger=trigger,
            notify_on_complete=notify_on_complete,
        )

    async def list_scheduled_tasks(self, user_id: str = None):
        """List scheduled tasks."""
        return await self.scheduler.list_tasks(user_id)

    async def cancel_scheduled_task(self, task_id: str) -> bool:
        """Cancel a scheduled task."""
        return await self.scheduler.delete_task(task_id)

    async def start_scheduler(self) -> None:
        """Start the autonomous scheduler."""
        await self.scheduler.start()

    async def stop_scheduler(self) -> None:
        """Stop the autonomous scheduler."""
        await self.scheduler.stop()

    async def get_task_history(
        self,
        user_id: str,
        limit: int = 10,
    ) -> list[dict]:
        """Get task history for a user."""
        return await self.memory.get_user_tasks(user_id, limit)


# Global agent service instance
_agent_service: Optional[AgentService] = None


def get_agent_service() -> AgentService:
    """Get or create the global agent service instance."""
    global _agent_service
    if _agent_service is None:
        _agent_service = AgentService()
        # Register default tools
        register_default_tools(_agent_service.tools)
    return _agent_service


def create_agent_service(llm_provider=None) -> AgentService:
    """Create a new agent service instance.

    Args:
        llm_provider: LLM provider

    Returns:
        AgentService instance
    """
    service = AgentService(llm_provider=llm_provider)
    register_default_tools(service.tools)
    return service