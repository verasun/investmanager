"""Voting system for consensus.

Implements simple majority voting with arbitrator tie-breaker.
"""

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from loguru import logger


class VoteValue(str, Enum):
    """Possible vote values."""
    ACCEPT = "accept"
    REJECT = "reject"
    ABSTAIN = "abstain"


@dataclass
class Vote:
    """A vote from a model."""
    model_id: str
    proposal_id: str
    value: VoteValue
    confidence: float = 0.5  # 0-1
    rationale: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "model_id": self.model_id,
            "proposal_id": self.proposal_id,
            "value": self.value.value,
            "confidence": self.confidence,
            "rationale": self.rationale,
        }


@dataclass
class VotingResult:
    """Result of a voting round."""
    proposal_id: str
    accept_count: int = 0
    reject_count: int = 0
    abstain_count: int = 0
    total_voters: int = 0
    winner: Optional[VoteValue] = None
    is_tie: bool = False
    arbitrator_decision: Optional[VoteValue] = None
    votes: list[Vote] = field(default_factory=list)

    @property
    def agreement_level(self) -> float:
        """Calculate agreement level (0-1)."""
        if self.total_voters == 0:
            return 0.0
        max_count = max(self.accept_count, self.reject_count, self.abstain_count)
        return max_count / self.total_voters

    @property
    def has_majority(self) -> bool:
        """Check if there's a clear majority."""
        threshold = self.total_voters / 2
        return self.accept_count > threshold or self.reject_count > threshold

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "proposal_id": self.proposal_id,
            "accept_count": self.accept_count,
            "reject_count": self.reject_count,
            "abstain_count": self.abstain_count,
            "total_voters": self.total_voters,
            "winner": self.winner.value if self.winner else None,
            "is_tie": self.is_tie,
            "arbitrator_decision": self.arbitrator_decision.value if self.arbitrator_decision else None,
            "agreement_level": self.agreement_level,
            "has_majority": self.has_majority,
        }


class VotingManager:
    """Manages voting for consensus."""

    def __init__(self, require_majority: bool = True):
        """
        Args:
            require_majority: If True, require >50% for consensus
        """
        self.require_majority = require_majority

    def tally_votes(self, votes: list[Vote]) -> dict[str, VotingResult]:
        """Tally votes for all proposals.

        Returns:
            Dict of proposal_id -> VotingResult
        """
        results = {}

        # Group votes by proposal
        for vote in votes:
            if vote.proposal_id not in results:
                results[vote.proposal_id] = VotingResult(
                    proposal_id=vote.proposal_id,
                    total_voters=0,
                )

            result = results[vote.proposal_id]
            result.votes.append(vote)
            result.total_voters += 1

            if vote.value == VoteValue.ACCEPT:
                result.accept_count += 1
            elif vote.value == VoteValue.REJECT:
                result.reject_count += 1
            else:
                result.abstain_count += 1

        # Determine winners
        for proposal_id, result in results.items():
            self._determine_winner(result)

        return results

    def _determine_winner(self, result: VotingResult):
        """Determine the winning vote for a result."""
        counts = {
            VoteValue.ACCEPT: result.accept_count,
            VoteValue.REJECT: result.reject_count,
            VoteValue.ABSTAIN: result.abstain_count,
        }

        # Find max count
        max_count = max(counts.values())
        winners = [v for v, c in counts.items() if c == max_count]

        if len(winners) == 1:
            result.winner = winners[0]
            result.is_tie = False
        else:
            # Tie between multiple values
            result.is_tie = True
            # Don't set winner yet - needs arbitrator

    def break_tie(
        self,
        result: VotingResult,
        arbitrator_vote: VoteValue,
    ) -> VoteValue:
        """Break a tie using arbitrator's vote.

        Args:
            result: The tied voting result
            arbitrator_vote: Arbitrator's vote value

        Returns:
            The final winning vote value
        """
        result.arbitrator_decision = arbitrator_vote
        result.winner = arbitrator_vote
        result.is_tie = False
        return arbitrator_vote

    def find_best_proposal(
        self,
        results: dict[str, VotingResult],
        arbitrator_proposal_id: Optional[str] = None,
    ) -> tuple[Optional[str], float]:
        """Find the best proposal based on voting results.

        Args:
            results: Voting results by proposal ID
            arbitrator_proposal_id: ID of arbitrator's proposal (for tie-breaking)

        Returns:
            Tuple of (winning_proposal_id, agreement_level)
        """
        if not results:
            return None, 0.0

        # Sort by accept count, then by agreement level
        sorted_results = sorted(
            results.items(),
            key=lambda x: (
                x[1].accept_count,
                x[1].agreement_level,
            ),
            reverse=True,
        )

        # Check for ties
        if len(sorted_results) > 1:
            top = sorted_results[0][1]
            second = sorted_results[1][1]

            if top.accept_count == second.accept_count:
                # Tie - prefer arbitrator's proposal if in top
                if arbitrator_proposal_id and arbitrator_proposal_id in results:
                    return arbitrator_proposal_id, results[arbitrator_proposal_id].agreement_level

                # Otherwise, pick randomly from tied proposals
                tied = [
                    (pid, r) for pid, r in sorted_results
                    if r.accept_count == top.accept_count
                ]
                winner = random.choice(tied)
                return winner[0], winner[1].agreement_level

        winner_id, winner_result = sorted_results[0]
        return winner_id, winner_result.agreement_level

    def check_consensus(
        self,
        results: dict[str, VotingResult],
        min_agreement: float = 0.5,
    ) -> bool:
        """Check if consensus has been reached.

        Args:
            results: Voting results
            min_agreement: Minimum agreement level required

        Returns:
            True if consensus reached
        """
        if not results:
            return False

        for result in results.values():
            if result.has_majority and result.agreement_level >= min_agreement:
                return True

        return False