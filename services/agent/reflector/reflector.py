"""Reflector - Execution result evaluation and retry logic."""

import json
from typing import Any, Optional

from loguru import logger

from ..planner import ExecutionPlan, Step, StepStatus
from ..executor import ExecutionResult
from .evaluation import ReflectionResult, StepEvaluation


class Reflector:
    """Evaluates execution results and decides on retry/correction.

    Analyzes:
    - Whether the goal was achieved
    - Why steps failed
    - What corrections to apply
    - Whether to retry
    """

    REFLECT_PROMPT = """你是执行评估专家。分析任务执行结果并给出评估。

## 原始目标
{goal}

## 执行步骤
{steps}

## 执行结果
{results}

## 失败信息
{errors}

请评估:
1. 是否达成目标? (是/否/部分)
2. 完成度 (0.0-1.0)
3. 失败原因
4. 建议的修正方案

输出JSON格式:
```json
{{
  "goal_achieved": true/false,
  "partial_achievement": 0.0-1.0,
  "failure_reasons": {{"step_id": "原因"}},
  "corrections": [
    {{"step_id": "xxx", "action": "retry/skip/modify", "new_params": {{}}}}
  ],
  "should_retry": true/false,
  "summary": "评估总结"
}}
```"""

    def __init__(
        self,
        llm_provider=None,
        max_retries: int = 3,
        retry_threshold: float = 0.5,
    ):
        """Initialize reflector.

        Args:
            llm_provider: LLM provider for reasoning
            max_retries: Maximum retry attempts
            retry_threshold: Minimum achievement score to consider successful
        """
        self.llm_provider = llm_provider
        self.max_retries = max_retries
        self.retry_threshold = retry_threshold

    def set_llm_provider(self, provider) -> None:
        """Set LLM provider."""
        self.llm_provider = provider

    async def reflect(
        self,
        plan: ExecutionPlan,
        result: ExecutionResult,
    ) -> ReflectionResult:
        """Reflect on execution results.

        Args:
            plan: The execution plan
            result: The execution result

        Returns:
            ReflectionResult with evaluation
        """
        # Get failed steps
        failed_steps = plan.get_failed_steps()

        if not failed_steps and result.success:
            # All steps succeeded
            return ReflectionResult(
                goal_achieved=True,
                partial_achievement=1.0,
                summary="所有步骤成功完成",
            )

        # Use LLM for detailed reflection if available
        if self.llm_provider:
            try:
                reflection = await self._reflect_with_llm(plan, result)
                if reflection:
                    return reflection
            except Exception as e:
                logger.warning(f"LLM reflection failed: {e}")

        # Fallback to rule-based reflection
        return self._reflect_rule_based(plan, result)

    async def _reflect_with_llm(
        self,
        plan: ExecutionPlan,
        result: ExecutionResult,
    ) -> Optional[ReflectionResult]:
        """Use LLM for reflection."""
        # Build prompt
        steps_info = []
        for step in plan.steps:
            steps_info.append({
                "id": step.id,
                "description": step.description,
                "tool": step.tool_name,
                "status": step.status.value,
                "error": step.error,
            })

        results_info = result.context.get_all_results() if result.context else {}
        errors = {s.id: s.error for s in plan.get_failed_steps() if s.error}

        prompt = self.REFLECT_PROMPT.format(
            goal=plan.goal,
            steps=json.dumps(steps_info, ensure_ascii=False, indent=2),
            results=json.dumps(
                {k: str(v)[:500] for k, v in results_info.items()},
                ensure_ascii=False,
                indent=2,
            ),
            errors=json.dumps(errors, ensure_ascii=False, indent=2),
        )

        try:
            response = await self.llm_provider.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=800,
            )

            content = response.content.strip()

            # Extract JSON
            import re
            json_match = re.search(r"\{[\s\S]*\}", content)
            if not json_match:
                return None

            data = json.loads(json_match.group(0))

            return ReflectionResult(
                goal_achieved=data.get("goal_achieved", False),
                partial_achievement=data.get("partial_achievement", 0.0),
                failed_steps=list(data.get("failure_reasons", {}).keys()),
                failure_reasons=data.get("failure_reasons", {}),
                corrections=data.get("corrections", []),
                should_retry=data.get("should_retry", False),
                summary=data.get("summary", ""),
            )

        except Exception as e:
            logger.error(f"LLM reflection error: {e}")
            return None

    def _reflect_rule_based(
        self,
        plan: ExecutionPlan,
        result: ExecutionResult,
    ) -> ReflectionResult:
        """Rule-based reflection when LLM is not available."""
        failed_steps = plan.get_failed_steps()
        completed, total = plan.progress()

        partial_achievement = completed / total if total > 0 else 0.0

        failure_reasons = {}
        corrections = []

        for step in failed_steps:
            failure_reasons[step.id] = step.error or "Unknown error"

            # Suggest corrections based on error type
            if step.error:
                if "not found" in step.error.lower() or "未找到" in step.error:
                    corrections.append({
                        "step_id": step.id,
                        "action": "modify",
                        "new_params": {},
                    })
                elif "timeout" in step.error.lower() or "超时" in step.error:
                    corrections.append({
                        "step_id": step.id,
                        "action": "retry",
                    })
                else:
                    corrections.append({
                        "step_id": step.id,
                        "action": "retry",
                    })

        should_retry = (
            partial_achievement < self.retry_threshold
            and len(failed_steps) > 0
        )

        return ReflectionResult(
            goal_achieved=partial_achievement >= self.retry_threshold,
            partial_achievement=partial_achievement,
            failed_steps=[s.id for s in failed_steps],
            failure_reasons=failure_reasons,
            corrections=corrections,
            should_retry=should_retry,
            summary=f"完成度: {partial_achievement:.1%}, 失败步骤: {len(failed_steps)}",
        )

    async def should_retry(
        self,
        reflection: ReflectionResult,
        attempt: int,
    ) -> bool:
        """Decide whether to retry.

        Args:
            reflection: Reflection result
            attempt: Current attempt number

        Returns:
            True if should retry
        """
        if attempt >= self.max_retries:
            return False

        if reflection.goal_achieved:
            return False

        if reflection.partial_achievement >= self.retry_threshold:
            return False

        return reflection.should_retry or len(reflection.failed_steps) > 0

    async def evaluate_step(
        self,
        step: Step,
        result: Any,
    ) -> StepEvaluation:
        """Evaluate a single step's result.

        Args:
            step: The step
            result: The step's result

        Returns:
            StepEvaluation
        """
        if step.status == StepStatus.COMPLETED:
            return StepEvaluation(
                step_id=step.id,
                success=True,
                score=1.0,
            )

        if step.status == StepStatus.FAILED:
            return StepEvaluation(
                step_id=step.id,
                success=False,
                score=0.0,
                issues=[step.error or "Unknown error"],
                suggestions=["Check parameters", "Retry the step"],
            )

        return StepEvaluation(
            step_id=step.id,
            success=False,
            score=0.5,
            issues=["Step not completed"],
        )


# Global reflector instance
_reflector: Optional[Reflector] = None


def get_reflector() -> Reflector:
    """Get or create the global reflector instance."""
    global _reflector
    if _reflector is None:
        _reflector = Reflector()
    return _reflector