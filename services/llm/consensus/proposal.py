"""Proposal data structures for consensus system."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class ProposalStatus(str, Enum):
    """Status of a proposal."""
    DRAFT = "draft"
    SUBMITTED = "submitted"
    REVIEWED = "reviewed"
    REVISED = "revised"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class Role(str, Enum):
    """Role of a model in consensus."""
    DESIGNER = "designer"      # Proposes solutions
    ARBITRATOR = "arbitrator"  # Evaluates and breaks ties
    REVIEWER = "reviewer"      # Reviews proposals


@dataclass
class Proposal:
    """A proposal from a model."""
    proposal_id: str
    model_id: str
    role: Role
    content: str
    confidence: float = 0.5  # 0-1
    rationale: Optional[str] = None
    status: ProposalStatus = ProposalStatus.DRAFT
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    # Review feedback
    feedback: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "proposal_id": self.proposal_id,
            "model_id": self.model_id,
            "role": self.role.value,
            "content": self.content,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "status": self.status.value,
            "feedback": self.feedback,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


@dataclass
class ProposalSet:
    """Collection of proposals for a consensus round."""
    trace_id: str
    task_description: str
    proposals: list[Proposal] = field(default_factory=list)
    round_number: int = 1

    def add_proposal(self, proposal: Proposal):
        """Add a proposal to the set."""
        self.proposals.append(proposal)

    def get_by_model(self, model_id: str) -> Optional[Proposal]:
        """Get proposal by model ID."""
        for p in self.proposals:
            if p.model_id == model_id:
                return p
        return None

    def get_by_role(self, role: Role) -> list[Proposal]:
        """Get proposals by role."""
        return [p for p in self.proposals if p.role == role]

    def get_arbitrator_proposal(self) -> Optional[Proposal]:
        """Get the arbitrator's proposal."""
        for p in self.proposals:
            if p.role == Role.ARBITRATOR:
                return p
        return None

    def get_designer_proposals(self) -> list[Proposal]:
        """Get all designer proposals."""
        return [p for p in self.proposals if p.role == Role.DESIGNER]

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "trace_id": self.trace_id,
            "task_description": self.task_description,
            "proposals": [p.to_dict() for p in self.proposals],
            "round_number": self.round_number,
        }


@dataclass
class ConsensusResult:
    """Final result of a consensus process."""
    final_response: str
    participating_models: list[str]
    arbitrator_model: Optional[str] = None
    rounds: int = 1
    agreement_level: float = 0.0  # 0-1, higher = more agreement
    winning_proposal_id: Optional[str] = None
    proposal_set: Optional[ProposalSet] = None

    # Metrics
    total_latency_ms: int = 0
    total_tokens_used: int = 0

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "final_response": self.final_response,
            "participating_models": self.participating_models,
            "arbitrator_model": self.arbitrator_model,
            "rounds": self.rounds,
            "agreement_level": self.agreement_level,
            "winning_proposal_id": self.winning_proposal_id,
            "total_latency_ms": self.total_latency_ms,
            "total_tokens_used": self.total_tokens_used,
        }