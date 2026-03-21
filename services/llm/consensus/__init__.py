"""Multi-model consensus system.

Provides consensus-based decision making using multiple models
with simple majority voting and arbitrator tie-breaker.
"""

from .coordinator import ConsensusCoordinator, get_consensus_coordinator
from .proposal import Proposal, ProposalSet, ConsensusResult, Role, ProposalStatus
from .voting import VotingManager, Vote, VoteValue, VotingResult

__all__ = [
    # Coordinator
    "ConsensusCoordinator",
    "get_consensus_coordinator",
    # Proposal
    "Proposal",
    "ProposalSet",
    "ConsensusResult",
    "Role",
    "ProposalStatus",
    # Voting
    "VotingManager",
    "Vote",
    "VoteValue",
    "VotingResult",
]