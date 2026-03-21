"""Consensus coordinator.

Orchestrates multi-model discussions for complex tasks with
simple majority voting and arbitrator tie-breaker.
"""

import asyncio
import time
import uuid
from dataclasses import dataclass
from typing import Any, Optional
from loguru import logger

from .proposal import (
    Proposal,
    ProposalSet,
    ConsensusResult,
    Role,
    ProposalStatus,
)
from .voting import (
    VotingManager,
    Vote,
    VoteValue,
    VotingResult,
)


@dataclass
class ConsensusConfig:
    """Configuration for consensus process."""
    min_models: int = 3
    max_rounds: int = 3
    timeout_seconds: int = 60
    require_majority: bool = True
    min_agreement: float = 0.5


class ConsensusCoordinator:
    """Coordinates multi-model consensus discussions."""

    def __init__(
        self,
        config: Optional[ConsensusConfig] = None,
        voting_manager: Optional[VotingManager] = None,
    ):
        self.config = config or ConsensusConfig()
        self.voting = voting_manager or VotingManager(
            require_majority=self.config.require_majority,
        )

    async def run_consensus(
        self,
        messages: list[dict],
        models: list[str],
        arbitrator_model: str,
        execute_model_func,
        system_prompt: Optional[str] = None,
    ) -> ConsensusResult:
        """Run a consensus process for a complex task.

        Args:
            messages: The conversation messages
            models: List of model IDs to participate (must include arbitrator)
            arbitrator_model: ID of the model to act as arbitrator
            execute_model_func: Async function to call a model (model_id, messages, system_prompt) -> response
            system_prompt: Optional system prompt

        Returns:
            ConsensusResult with final response
        """
        start_time = time.time()
        trace_id = f"consensus_{uuid.uuid4().hex[:8]}"

        logger.info(
            f"[{trace_id}] Starting consensus with {len(models)} models, "
            f"arbitrator: {arbitrator_model}"
        )

        # Validate inputs
        if len(models) < self.config.min_models:
            raise ValueError(
                f"Need at least {self.config.min_models} models, got {len(models)}"
            )

        if arbitrator_model not in models:
            raise ValueError(
                f"Arbitrator {arbitrator_model} must be in participating models"
            )

        # Assign roles
        designer_models = [m for m in models if m != arbitrator_model]
        roles = {m: Role.DESIGNER for m in designer_models}
        roles[arbitrator_model] = Role.ARBITRATOR

        # Initialize proposal set
        task_description = messages[-1].get("content", "") if messages else ""
        proposal_set = ProposalSet(
            trace_id=trace_id,
            task_description=task_description,
        )

        total_tokens = 0
        final_response = None
        agreement_level = 0.0

        try:
            # Run consensus rounds
            for round_num in range(1, self.config.max_rounds + 1):
                proposal_set.round_number = round_num
                logger.info(f"[{trace_id}] Starting round {round_num}")

                # Phase 1: Generate proposals in parallel
                proposals = await self._generate_proposals(
                    trace_id=trace_id,
                    messages=messages,
                    models=models,
                    roles=roles,
                    execute_model_func=execute_model_func,
                    system_prompt=system_prompt,
                    previous_proposals=proposal_set if round_num > 1 else None,
                )

                for p in proposals:
                    proposal_set.add_proposal(p)
                    total_tokens += len(p.content) // 4  # Rough estimate

                # Phase 2: Discussion (models review each other's proposals)
                if round_num < self.config.max_rounds:
                    await self._run_discussion(
                        trace_id=trace_id,
                        proposal_set=proposal_set,
                        models=models,
                        roles=roles,
                        execute_model_func=execute_model_func,
                        system_prompt=system_prompt,
                    )

                # Phase 3: Voting
                votes = await self._collect_votes(
                    trace_id=trace_id,
                    proposal_set=proposal_set,
                    models=models,
                    roles=roles,
                    execute_model_func=execute_model_func,
                )

                # Tally votes
                results = self.voting.tally_votes(votes)

                # Check for consensus
                if self.voting.check_consensus(
                    results,
                    min_agreement=self.config.min_agreement,
                ):
                    logger.info(f"[{trace_id}] Consensus reached in round {round_num}")
                    winning_id, agreement_level = self.voting.find_best_proposal(
                        results,
                        arbitrator_proposal_id=arbitrator_model,
                    )
                    if winning_id:
                        winning_proposal = proposal_set.get_by_model(winning_id)
                        if winning_proposal:
                            final_response = winning_proposal.content
                    break

                # No consensus - continue to next round
                logger.info(
                    f"[{trace_id}] No consensus in round {round_num}, continuing..."
                )

            # If no consensus after all rounds, arbitrator synthesizes
            if final_response is None:
                logger.info(f"[{trace_id}] No consensus after max rounds, arbitrator synthesizing")
                final_response = await self._arbitrator_synthesize(
                    trace_id=trace_id,
                    proposal_set=proposal_set,
                    arbitrator_model=arbitrator_model,
                    execute_model_func=execute_model_func,
                    system_prompt=system_prompt,
                )
                agreement_level = 0.5  # Arbitrator decision

            latency_ms = int((time.time() - start_time) * 1000)

            return ConsensusResult(
                final_response=final_response or "Unable to reach consensus",
                participating_models=models,
                arbitrator_model=arbitrator_model,
                rounds=proposal_set.round_number,
                agreement_level=agreement_level,
                total_latency_ms=latency_ms,
                total_tokens_used=total_tokens,
                proposal_set=proposal_set,
            )

        except asyncio.TimeoutError:
            logger.error(f"[{trace_id}] Consensus timed out")
            # Fallback to arbitrator's initial proposal
            arbitrator_proposal = proposal_set.get_by_model(arbitrator_model)
            return ConsensusResult(
                final_response=arbitrator_proposal.content if arbitrator_proposal else "Consensus timed out",
                participating_models=models,
                arbitrator_model=arbitrator_model,
                rounds=proposal_set.round_number,
                agreement_level=0.0,
                total_latency_ms=int((time.time() - start_time) * 1000),
                total_tokens_used=total_tokens,
            )

    async def _generate_proposals(
        self,
        trace_id: str,
        messages: list[dict],
        models: list[str],
        roles: dict[str, Role],
        execute_model_func,
        system_prompt: Optional[str],
        previous_proposals: Optional[ProposalSet] = None,
    ) -> list[Proposal]:
        """Generate initial proposals from all models in parallel."""
        tasks = []

        for model_id in models:
            role = roles[model_id]
            prompt = self._build_proposal_prompt(
                messages=messages,
                role=role,
                previous_proposals=previous_proposals,
            )
            tasks.append(self._call_model(
                trace_id=trace_id,
                model_id=model_id,
                role=role,
                messages=[{"role": "user", "content": prompt}],
                execute_model_func=execute_model_func,
                system_prompt=system_prompt,
            ))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        proposals = []
        for model_id, result in zip(models, results):
            if isinstance(result, Exception):
                logger.warning(f"[{trace_id}] Model {model_id} failed: {result}")
                continue

            proposal = Proposal(
                proposal_id=f"prop_{model_id}_{uuid.uuid4().hex[:6]}",
                model_id=model_id,
                role=roles[model_id],
                content=result,
                confidence=0.7,  # Default confidence
                status=ProposalStatus.SUBMITTED,
            )
            proposals.append(proposal)

        return proposals

    def _build_proposal_prompt(
        self,
        messages: list[dict],
        role: Role,
        previous_proposals: Optional[ProposalSet] = None,
    ) -> str:
        """Build the prompt for proposal generation."""
        task = messages[-1].get("content", "") if messages else ""

        if role == Role.ARBITRATOR:
            if previous_proposals:
                # Synthesis mode
                proposals_text = "\n\n".join([
                    f"**{p.model_id}**:\n{p.content[:500]}..."
                    for p in previous_proposals.proposals
                ])
                return f"""作为仲裁者，请综合以下各方观点，给出最终答案。

原始问题：{task}

各方观点：
{proposals_text}

请给出您的综合分析和最终建议："""
            else:
                return f"""作为仲裁者，请分析以下问题并给出您的观点。

问题：{task}

请提供详细的分析和建议："""
        else:
            # Designer
            if previous_proposals:
                # Revision mode
                feedback_text = ""
                for p in previous_proposals.proposals:
                    if p.role == Role.ARBITRATOR:
                        feedback_text = f"仲裁者反馈：{p.rationale or '需要更好的方案'}"
                        break

                return f"""请根据反馈优化你的方案。

原始问题：{task}

{feedback_text}

请提供改进后的分析和建议："""
            else:
                return f"""请分析以下问题并给出你的观点和建议。

问题：{task}

请提供详细的分析："""

    async def _run_discussion(
        self,
        trace_id: str,
        proposal_set: ProposalSet,
        models: list[str],
        roles: dict[str, Role],
        execute_model_func,
        system_prompt: Optional[str],
    ):
        """Run discussion phase where models review each other's proposals."""
        # Each designer reviews others' proposals
        tasks = []

        for model_id in models:
            if roles[model_id] != Role.DESIGNER:
                continue

            # Get other proposals to review
            others = [
                p for p in proposal_set.proposals
                if p.model_id != model_id
            ]

            if not others:
                continue

            prompt = self._build_review_prompt(
                proposal_set.task_description,
                others,
            )

            tasks.append(self._call_model(
                trace_id=trace_id,
                model_id=model_id,
                role=roles[model_id],
                messages=[{"role": "user", "content": prompt}],
                execute_model_func=execute_model_func,
                system_prompt=system_prompt,
            ))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _build_review_prompt(
        self,
        task: str,
        proposals: list[Proposal],
    ) -> str:
        """Build prompt for reviewing proposals."""
        proposals_text = "\n\n".join([
            f"**{p.model_id}**:\n{p.content[:500]}..."
            for p in proposals
        ])

        return f"""请评价以下方案并提出改进建议。

原始问题：{task}

待评价方案：
{proposals_text}

请简要说明：
1. 你认同哪些观点？
2. 你认为哪些地方需要改进？
3. 你的建议是什么？"""

    async def _collect_votes(
        self,
        trace_id: str,
        proposal_set: ProposalSet,
        models: list[str],
        roles: dict[str, Role],
        execute_model_func,
    ) -> list[Vote]:
        """Collect votes from all models."""
        votes = []
        tasks = []

        for model_id in models:
            prompt = self._build_voting_prompt(
                proposal_set.task_description,
                proposal_set.proposals,
            )

            tasks.append(self._call_model(
                trace_id=trace_id,
                model_id=model_id,
                role=roles[model_id],
                messages=[{"role": "user", "content": prompt}],
                execute_model_func=execute_model_func,
                system_prompt=None,
            ))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for model_id, result in zip(models, results):
            if isinstance(result, Exception):
                logger.warning(f"[{trace_id}] Voting failed for {model_id}: {result}")
                continue

            # Parse vote from response
            vote = self._parse_vote(model_id, result, proposal_set.proposals)
            votes.append(vote)

        return votes

    def _build_voting_prompt(
        self,
        task: str,
        proposals: list[Proposal],
    ) -> str:
        """Build prompt for voting."""
        proposals_text = "\n\n".join([
            f"[{p.model_id}]\n{p.content[:300]}..."
            for p in proposals
        ])

        return f"""请为你认为最好的方案投票。

原始问题：{task}

方案列表：
{proposals_text}

请回复你支持的方案ID（如：支持 qwen3.5-plus）。

只回复一个方案ID，不要其他内容。"""

    def _parse_vote(
        self,
        model_id: str,
        response: str,
        proposals: list[Proposal],
    ) -> Vote:
        """Parse a vote from model response."""
        response_lower = response.lower()

        # Find which proposal is supported
        for proposal in proposals:
            if proposal.model_id.lower() in response_lower:
                return Vote(
                    model_id=model_id,
                    proposal_id=proposal.proposal_id,
                    value=VoteValue.ACCEPT,
                    confidence=0.7,
                    rationale=response[:200] if response else None,
                )

        # Default: vote for self if designer, or first proposal
        own_proposal = next(
            (p for p in proposals if p.model_id == model_id),
            proposals[0] if proposals else None
        )

        if own_proposal:
            return Vote(
                model_id=model_id,
                proposal_id=own_proposal.proposal_id,
                value=VoteValue.ACCEPT,
                confidence=0.5,
            )

        # Fallback abstain
        return Vote(
            model_id=model_id,
            proposal_id="unknown",
            value=VoteValue.ABSTAIN,
            confidence=0.0,
        )

    async def _arbitrator_synthesize(
        self,
        trace_id: str,
        proposal_set: ProposalSet,
        arbitrator_model: str,
        execute_model_func,
        system_prompt: Optional[str],
    ) -> str:
        """Have arbitrator synthesize a final response."""
        proposals_text = "\n\n".join([
            f"**{p.model_id}**:\n{p.content}"
            for p in proposal_set.proposals
        ])

        prompt = f"""作为仲裁者，各参与方未能达成共识。请综合以下观点，给出最终答案。

原始问题：{proposal_set.task_description}

各方观点：
{proposals_text}

请给出您的综合分析和最终建议（这是最终决策）："""

        return await self._call_model(
            trace_id=trace_id,
            model_id=arbitrator_model,
            role=Role.ARBITRATOR,
            messages=[{"role": "user", "content": prompt}],
            execute_model_func=execute_model_func,
            system_prompt=system_prompt,
        )

    async def _call_model(
        self,
        trace_id: str,
        model_id: str,
        role: Role,
        messages: list[dict],
        execute_model_func,
        system_prompt: Optional[str],
    ) -> str:
        """Call a model and return its response."""
        try:
            response = await execute_model_func(
                model_id=model_id,
                messages=messages,
                system_prompt=system_prompt,
            )
            return response
        except Exception as e:
            logger.error(f"[{trace_id}] Failed to call {model_id}: {e}")
            raise


# Global coordinator instance
_coordinator: Optional[ConsensusCoordinator] = None


def get_consensus_coordinator() -> ConsensusCoordinator:
    """Get or create the global consensus coordinator."""
    global _coordinator
    if _coordinator is None:
        _coordinator = ConsensusCoordinator()
    return _coordinator