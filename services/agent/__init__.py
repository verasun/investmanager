"""Agent Service - Full agentic capabilities for InvestManager.

This module provides:
- Tool Registry: Unified tool management for LLM function calling
- Planner: Task decomposition and execution planning
- Executor: ReAct loop for tool execution
- Reflector: Result evaluation and retry logic
- Agent Memory: Task history and pattern learning
- Autonomous Scheduler: Scheduled tasks and proactive notifications

Architecture:
┌─────────────────────────────────────────────────────────────────────┐
│                         AGENT SERVICE (:8002)                       │
├─────────────────────────────────────────────────────────────────────┤
│  User Request ──▶ Planner ──▶ Executor ──▶ Reflector ──▶ Response  │
│                                                                      │
│  Tool Registry: web_search, stock_data, analysis, backtest, report │
│  Agent Memory: Task history, execution traces, learned patterns     │
│  Autonomous Scheduler: Timed tasks, price alerts, news monitoring   │
└─────────────────────────────────────────────────────────────────────┘
"""

from .tools import ToolRegistry, BaseTool, ToolResult, register_default_tools
from .planner import Planner, ExecutionPlan, Step
from .executor import Executor, ReActLoop, ExecutionContext, ExecutionResult
from .reflector import Reflector, ReflectionResult
from .memory import AgentMemory
from .scheduler import AutonomousScheduler
from .service import AgentService, AgentResult, get_agent_service, create_agent_service

__all__ = [
    # Tools
    "ToolRegistry",
    "BaseTool",
    "ToolResult",
    "register_default_tools",
    # Planner
    "Planner",
    "ExecutionPlan",
    "Step",
    # Executor
    "Executor",
    "ReActLoop",
    "ExecutionContext",
    "ExecutionResult",
    # Reflector
    "Reflector",
    "ReflectionResult",
    # Memory
    "AgentMemory",
    # Scheduler
    "AutonomousScheduler",
    # Service
    "AgentService",
    "AgentResult",
    "get_agent_service",
    "create_agent_service",
]