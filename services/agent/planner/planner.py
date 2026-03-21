"""Planner - Task decomposition and execution planning."""

import json
import uuid
from typing import Any, Optional

from loguru import logger

from .plan import (
    ExecutionPlan,
    Step,
    StepStatus,
    PlanRequest,
    PlanResponse,
)


class Planner:
    """Task planner that decomposes user requests into execution steps.

    Uses LLM to analyze requests and generate structured plans.
    """

    PLAN_SYSTEM_PROMPT = """你是一个任务规划器。分析用户请求，将其分解为可执行的步骤。

## 输出格式
请严格按照以下JSON格式输出，不要包含任何其他内容：
```json
{{
  "reasoning": "分析用户请求的推理过程",
  "steps": [
    {{
      "id": "step_1",
      "description": "步骤描述",
      "tool": "工具名称或null",
      "parameters": {{}},
      "dependencies": []
    }}
  ]
}}
```

## 规则
1. 每个步骤必须有唯一的id（格式：step_N）
2. dependencies 是前置步骤的id列表
3. tool 为 null 表示该步骤需要LLM推理而非工具调用
4. 步骤应该具体、可执行
5. 考虑步骤之间的依赖关系

## 可用工具
{tools_description}

## 用户请求
{goal}

请生成执行计划："""

    REFINEMENT_PROMPT = """根据执行结果，修正原计划。

原计划目标: {goal}

已完成的步骤:
{completed_steps}

失败的步骤:
{failed_steps}

错误信息:
{errors}

请输出修正后的执行计划（JSON格式）：
```json
{{
  "reasoning": "修正推理",
  "steps_to_retry": ["step_id"],
  "new_steps": [...],
  "skip_steps": ["step_id"]
}}
```"""

    def __init__(self, llm_provider=None, tool_registry=None):
        """Initialize planner.

        Args:
            llm_provider: LLM provider for plan generation
            tool_registry: Tool registry for available tools
        """
        self.llm_provider = llm_provider
        self.tool_registry = tool_registry

    def set_llm_provider(self, provider) -> None:
        """Set LLM provider."""
        self.llm_provider = provider

    def set_tool_registry(self, registry) -> None:
        """Set tool registry."""
        self.tool_registry = registry

    async def plan(
        self,
        goal: str,
        context: dict = None,
        patterns: list = None,
    ) -> ExecutionPlan:
        """Generate an execution plan for a goal.

        Args:
            goal: User's request/goal
            context: Optional context information
            patterns: Optional learned patterns to apply

        Returns:
            ExecutionPlan with steps
        """
        task_id = f"task_{uuid.uuid4().hex[:8]}"

        # Build tools description
        tools_desc = self._build_tools_description()

        # Check if we can use LLM for planning
        if self.llm_provider:
            try:
                plan = await self._plan_with_llm(goal, tools_desc, task_id, context)
                if plan:
                    return plan
            except Exception as e:
                logger.warning(f"LLM planning failed: {e}, falling back to rule-based")

        # Fallback to rule-based planning
        return self._plan_rule_based(goal, task_id, context)

    async def _plan_with_llm(
        self,
        goal: str,
        tools_desc: str,
        task_id: str,
        context: dict = None,
    ) -> Optional[ExecutionPlan]:
        """Generate plan using LLM."""
        prompt = self.PLAN_SYSTEM_PROMPT.format(
            tools_description=tools_desc,
            goal=goal,
        )

        try:
            # Call LLM
            response = await self.llm_provider.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=1500,
            )

            content = response.content.strip()

            # Extract JSON from response
            json_match = self._extract_json(content)
            if not json_match:
                logger.warning("No valid JSON found in LLM response")
                return None

            plan_data = json.loads(json_match)

            # Build execution plan
            steps = []
            for step_data in plan_data.get("steps", []):
                step = Step(
                    id=step_data.get("id", f"step_{len(steps) + 1}"),
                    description=step_data.get("description", ""),
                    tool_name=step_data.get("tool"),
                    parameters=step_data.get("parameters", {}),
                    dependencies=step_data.get("dependencies", []),
                )
                steps.append(step)

            return ExecutionPlan(
                task_id=task_id,
                goal=goal,
                steps=steps,
                context=context or {},
            )

        except Exception as e:
            logger.error(f"LLM planning error: {e}")
            return None

    def _plan_rule_based(
        self,
        goal: str,
        task_id: str,
        context: dict = None,
    ) -> ExecutionPlan:
        """Generate plan using rule-based approach."""
        goal_lower = goal.lower()
        steps = []

        # Detect task type and create appropriate steps
        if self._is_stock_analysis_task(goal_lower):
            steps = self._create_stock_analysis_steps(goal)
        elif self._is_search_task(goal_lower):
            steps = self._create_search_steps(goal)
        elif self._is_backtest_task(goal_lower):
            steps = self._create_backtest_steps(goal)
        elif self._is_report_task(goal_lower):
            steps = self._create_report_steps(goal)
        else:
            # Generic approach: single LLM step
            steps = [
                Step(
                    id="step_1",
                    description=f"处理用户请求: {goal}",
                    tool_name=None,  # LLM step
                    parameters={"query": goal},
                    dependencies=[],
                )
            ]

        return ExecutionPlan(
            task_id=task_id,
            goal=goal,
            steps=steps,
            context=context or {},
        )

    def _is_stock_analysis_task(self, goal: str) -> bool:
        """Check if this is a stock analysis task."""
        keywords = ["股票", "分析", "走势", "技术", "基本面", "股价"]
        return any(k in goal for k in keywords)

    def _is_search_task(self, goal: str) -> bool:
        """Check if this is a search task."""
        keywords = ["搜索", "查找", "查询", "最新", "新闻", "当前"]
        return any(k in goal for k in keywords)

    def _is_backtest_task(self, goal: str) -> bool:
        """Check if this is a backtest task."""
        keywords = ["回测", "策略", "模拟", "收益"]
        return any(k in goal for k in keywords)

    def _is_report_task(self, goal: str) -> bool:
        """Check if this is a report task."""
        keywords = ["报告", "总结", "汇总", "生成"]
        return any(k in goal for k in keywords)

    def _create_stock_analysis_steps(self, goal: str) -> list[Step]:
        """Create steps for stock analysis task."""
        # Extract stock symbol from goal
        symbol = self._extract_symbol(goal)

        return [
            Step(
                id="step_1",
                description=f"获取股票 {symbol or '目标'} 数据",
                tool_name="stock_data",
                parameters={"symbol": symbol, "days": 365} if symbol else {},
                dependencies=[],
            ),
            Step(
                id="step_2",
                description="进行技术分析",
                tool_name="stock_analysis",
                parameters={"symbol": symbol, "analysis_type": "technical"} if symbol else {},
                dependencies=["step_1"],
            ),
            Step(
                id="step_3",
                description="进行基本面分析",
                tool_name="stock_analysis",
                parameters={"symbol": symbol, "analysis_type": "fundamental"} if symbol else {},
                dependencies=["step_1"],
            ),
            Step(
                id="step_4",
                description="综合分析结果",
                tool_name=None,  # LLM synthesis
                parameters={},
                dependencies=["step_2", "step_3"],
            ),
        ]

    def _create_search_steps(self, goal: str) -> list[Step]:
        """Create steps for search task."""
        return [
            Step(
                id="step_1",
                description="执行网络搜索",
                tool_name="web_search",
                parameters={"query": goal},
                dependencies=[],
            ),
            Step(
                id="step_2",
                description="整理搜索结果",
                tool_name=None,
                parameters={},
                dependencies=["step_1"],
            ),
        ]

    def _create_backtest_steps(self, goal: str) -> list[Step]:
        """Create steps for backtest task."""
        symbol = self._extract_symbol(goal)

        return [
            Step(
                id="step_1",
                description=f"获取股票数据",
                tool_name="stock_data",
                parameters={"symbol": symbol, "days": 365} if symbol else {},
                dependencies=[],
            ),
            Step(
                id="step_2",
                description="执行策略回测",
                tool_name="backtest",
                parameters={"symbol": symbol, "strategy": "ma_cross"} if symbol else {},
                dependencies=["step_1"],
            ),
            Step(
                id="step_3",
                description="分析回测结果",
                tool_name=None,
                parameters={},
                dependencies=["step_2"],
            ),
        ]

    def _create_report_steps(self, goal: str) -> list[Step]:
        """Create steps for report generation."""
        symbol = self._extract_symbol(goal)

        return [
            Step(
                id="step_1",
                description="获取股票数据",
                tool_name="stock_data",
                parameters={"symbol": symbol} if symbol else {},
                dependencies=[],
            ),
            Step(
                id="step_2",
                description="分析股票",
                tool_name="stock_analysis",
                parameters={"symbol": symbol} if symbol else {},
                dependencies=["step_1"],
            ),
            Step(
                id="step_3",
                description="生成报告",
                tool_name="report",
                parameters={"symbol": symbol, "report_type": "comprehensive"} if symbol else {},
                dependencies=["step_2"],
            ),
        ]

    def _extract_symbol(self, text: str) -> Optional[str]:
        """Extract stock symbol from text."""
        import re

        # Match 6-digit codes (A-shares)
        match = re.search(r"\b(\d{6})\b", text)
        if match:
            return match.group(1)

        # Match US stock symbols (1-5 uppercase letters)
        match = re.search(r"\b([A-Z]{1,5})\b", text)
        if match:
            return match.group(1)

        # Match common Chinese stock names
        stock_names = {
            "茅台": "600519",
            "五粮液": "000858",
            "苹果": "AAPL",
            "腾讯": "00700",
            "阿里": "BABA",
        }
        for name, code in stock_names.items():
            if name in text:
                return code

        return None

    def _build_tools_description(self) -> str:
        """Build description of available tools."""
        if not self.tool_registry:
            return "无可用工具"

        return self.tool_registry.get_tools_description()

    def _extract_json(self, text: str) -> Optional[str]:
        """Extract JSON from text that may contain markdown."""
        # Try direct JSON parse first
        text = text.strip()
        if text.startswith("{"):
            return text

        # Look for JSON in code blocks
        import re

        # Match ```json ... ```
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if match:
            return match.group(1).strip()

        # Try to find JSON object directly
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            return match.group(0)

        return None

    async def revise(
        self,
        original_plan: ExecutionPlan,
        failed_steps: list[Step],
        errors: dict[str, str],
    ) -> ExecutionPlan:
        """Revise a plan after failures.

        Args:
            original_plan: The original execution plan
            failed_steps: Steps that failed
            errors: Error messages by step ID

        Returns:
            Revised execution plan
        """
        if not self.llm_provider:
            # Simple fallback: retry failed steps
            for step in original_plan.steps:
                if step.status == StepStatus.FAILED:
                    step.status = StepStatus.PENDING
                    step.error = None
            return original_plan

        # Use LLM to revise plan
        completed = [
            s.to_dict() for s in original_plan.steps
            if s.status == StepStatus.COMPLETED
        ]
        failed = [s.to_dict() for s in failed_steps]
        errors_str = "\n".join(f"- {k}: {v}" for k, v in errors.items())

        prompt = self.REFINEMENT_PROMPT.format(
            goal=original_plan.goal,
            completed_steps=json.dumps(completed, ensure_ascii=False, indent=2),
            failed_steps=json.dumps(failed, ensure_ascii=False, indent=2),
            errors=errors_str,
        )

        try:
            response = await self.llm_provider.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=1000,
            )

            content = response.content.strip()
            json_match = self._extract_json(content)

            if json_match:
                revision = json.loads(json_match)

                # Apply revision
                for step_id in revision.get("skip_steps", []):
                    step = original_plan.get_step(step_id)
                    if step:
                        step.status = StepStatus.SKIPPED

                for step_data in revision.get("new_steps", []):
                    new_step = Step(
                        id=step_data.get("id", f"step_{len(original_plan.steps) + 1}"),
                        description=step_data.get("description", ""),
                        tool_name=step_data.get("tool"),
                        parameters=step_data.get("parameters", {}),
                        dependencies=step_data.get("dependencies", []),
                    )
                    original_plan.steps.append(new_step)

                for step_id in revision.get("steps_to_retry", []):
                    step = original_plan.get_step(step_id)
                    if step:
                        step.status = StepStatus.PENDING
                        step.error = None

            return original_plan

        except Exception as e:
            logger.error(f"Plan revision failed: {e}")
            return original_plan


# Global planner instance
_planner: Optional[Planner] = None


def get_planner() -> Planner:
    """Get or create the global planner instance."""
    global _planner
    if _planner is None:
        _planner = Planner()
    return _planner