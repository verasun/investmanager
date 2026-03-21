"""ReAct Loop - Reasoning and Acting loop for tool execution."""

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from loguru import logger


@dataclass
class Thought:
    """A thought in the ReAct loop."""

    reasoning: str
    action: Optional[str] = None
    action_input: dict = field(default_factory=dict)
    is_final: bool = False
    final_answer: str = ""


@dataclass
class Observation:
    """An observation from tool execution."""

    action: str
    result: Any
    success: bool = True
    error: Optional[str] = None


class ReActLoop:
    """ReAct (Reasoning + Acting) loop implementation.

    Follows the pattern:
    1. Thought: Think about what to do next
    2. Action: Execute a tool
    3. Observation: Observe the result
    4. Repeat until final answer
    """

    REACT_PROMPT = """你是一个智能助手，使用 ReAct 格式进行思考和行动。

## 格式说明
每一步你需要输出:
- Thought: 思考下一步该做什么
- Action: 要执行的工具名称
- Action Input: 工具输入参数（JSON格式）
- Observation: 工具执行结果（系统自动填充）

当任务完成时，输出:
- Thought: 思考过程
- Final Answer: 最终答案

## 可用工具
{tools_description}

## 任务
{task}

## 已执行步骤
{history}

请输出下一步思考："""

    PARSE_PROMPT = """从以下文本中提取 Thought 和 Action：

{text}

请输出JSON格式：
```json
{{
  "thought": "思考内容",
  "action": "工具名称或FINAL",
  "action_input": {{}},
  "final_answer": "最终答案（如果已完成）"
}}
```"""

    def __init__(
        self,
        tool_registry=None,
        llm_provider=None,
        max_iterations: int = 10,
    ):
        """Initialize ReAct loop.

        Args:
            tool_registry: Registry of available tools
            llm_provider: LLM provider for reasoning
            max_iterations: Maximum iterations before stopping
        """
        self.tool_registry = tool_registry
        self.llm_provider = llm_provider
        self.max_iterations = max_iterations

    async def run(
        self,
        task: str,
        context: dict = None,
    ) -> str:
        """Run the ReAct loop for a task.

        Args:
            task: The task to accomplish
            context: Optional context information

        Returns:
            Final answer string
        """
        history = []
        tools_desc = self._build_tools_description()

        for iteration in range(self.max_iterations):
            logger.info(f"ReAct iteration {iteration + 1}/{self.max_iterations}")

            # Build prompt with history
            history_str = self._format_history(history)
            prompt = self.REACT_PROMPT.format(
                tools_description=tools_desc,
                task=task,
                history=history_str,
            )

            # Get LLM response
            try:
                thought = await self._get_thought(prompt, context)

                if thought.is_final:
                    logger.info(f"ReAct completed with final answer")
                    return thought.final_answer

                if not thought.action:
                    # No action specified, ask for clarification or give final answer
                    return thought.reasoning

                # Execute the action
                observation = await self._execute_action(
                    thought.action,
                    thought.action_input,
                )

                # Add to history
                history.append({
                    "thought": thought.reasoning,
                    "action": thought.action,
                    "action_input": thought.action_input,
                    "observation": observation.result if observation.success else f"Error: {observation.error}",
                })

            except Exception as e:
                logger.error(f"ReAct iteration failed: {e}")
                history.append({
                    "thought": "Error occurred",
                    "action": "error",
                    "observation": str(e),
                })

        # Max iterations reached
        logger.warning("ReAct reached max iterations")
        return self._synthesize_partial_result(history)

    async def _get_thought(self, prompt: str, context: dict = None) -> Thought:
        """Get the next thought from LLM."""
        if not self.llm_provider:
            # Fallback: simple heuristic
            return Thought(
                reasoning="No LLM available, executing directly",
                is_final=True,
                final_answer="Unable to process without LLM",
            )

        response = await self.llm_provider.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=800,
        )

        content = response.content.strip()

        # Parse the response
        return self._parse_thought(content)

    def _parse_thought(self, text: str) -> Thought:
        """Parse LLM response into a Thought."""
        text = text.strip()

        # Check for Final Answer
        if "Final Answer:" in text or "最终答案:" in text:
            # Extract final answer
            answer = text
            for marker in ["Final Answer:", "最终答案:", "Final Answer：", "最终答案："]:
                if marker in answer:
                    answer = answer.split(marker)[-1].strip()
                    break
            return Thought(
                reasoning=text,
                is_final=True,
                final_answer=answer,
            )

        # Parse action
        action = None
        action_input = {}
        reasoning = text

        # Try to extract Action and Action Input
        import re

        # Match "Action: xxx" pattern
        action_match = re.search(r"Action[:：]\s*(\w+)", text, re.IGNORECASE)
        if action_match:
            action = action_match.group(1)

        # Match "Action Input: {...}" pattern
        input_match = re.search(r"Action Input[:：]\s*(\{[\s\S]*?\})", text, re.IGNORECASE)
        if input_match:
            try:
                action_input = json.loads(input_match.group(1))
            except json.JSONDecodeError:
                action_input = {}

        # Extract Thought
        thought_match = re.search(r"Thought[:：]\s*([^\n]+)", text, re.IGNORECASE)
        if thought_match:
            reasoning = thought_match.group(1).strip()

        return Thought(
            reasoning=reasoning,
            action=action,
            action_input=action_input,
        )

    async def _execute_action(
        self,
        action: str,
        action_input: dict,
    ) -> Observation:
        """Execute an action using the tool registry."""
        if not self.tool_registry:
            return Observation(
                action=action,
                result=None,
                success=False,
                error="No tool registry available",
            )

        if not self.tool_registry.has(action):
            return Observation(
                action=action,
                result=None,
                success=False,
                error=f"Unknown tool: {action}",
            )

        result = await self.tool_registry.execute(action, action_input)

        return Observation(
            action=action,
            result=result.data if result.success else None,
            success=result.success,
            error=result.error,
        )

    def _build_tools_description(self) -> str:
        """Build description of available tools."""
        if not self.tool_registry:
            return "No tools available"
        return self.tool_registry.get_tools_description()

    def _format_history(self, history: list) -> str:
        """Format execution history for prompt."""
        if not history:
            return "暂无已执行步骤"

        lines = []
        for i, step in enumerate(history, 1):
            lines.append(f"### 步骤 {i}")
            lines.append(f"Thought: {step.get('thought', '')}")
            lines.append(f"Action: {step.get('action', '')}")
            lines.append(f"Action Input: {json.dumps(step.get('action_input', {}), ensure_ascii=False)}")
            lines.append(f"Observation: {step.get('observation', '')}")
            lines.append("")

        return "\n".join(lines)

    def _synthesize_partial_result(self, history: list) -> str:
        """Synthesize a result from partial execution history."""
        if not history:
            return "任务未能完成，请重试或简化请求"

        # Get the last observation
        last_obs = history[-1].get("observation", "")
        if last_obs and not last_obs.startswith("Error"):
            return f"部分完成。最后结果: {last_obs[:500]}"

        return "任务执行中断，请重试或提供更多信息"


# Convenience function
async def run_react_loop(
    task: str,
    tool_registry=None,
    llm_provider=None,
    max_iterations: int = 10,
) -> str:
    """Run a ReAct loop for a task.

    Args:
        task: The task to accomplish
        tool_registry: Registry of available tools
        llm_provider: LLM provider for reasoning
        max_iterations: Maximum iterations

    Returns:
        Final answer string
    """
    loop = ReActLoop(
        tool_registry=tool_registry,
        llm_provider=llm_provider,
        max_iterations=max_iterations,
    )
    return await loop.run(task)