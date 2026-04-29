from __future__ import annotations

from pydantic import BaseModel, Field

from app.reasoning.state import AgentState
from app.retrieval.evidence_packs import EvidencePack, EvidencePackBuilder, EvidencePackBuilderConfig, build_evidence_pack
from app.retrieval.hybrid_retriever import HybridRetrievalResult


class AgentEvidenceBuildResult(BaseModel):
    pack: EvidencePack
    selected_evidence_ids: list[str] = Field(default_factory=list)
    candidate_chunk_ids: list[str] = Field(default_factory=list)
    missing_coverage: list[str] = Field(default_factory=list)


class AgentEvidenceBuilder:
    def __init__(self, config: EvidencePackBuilderConfig | None = None) -> None:
        self.config = config or EvidencePackBuilderConfig()
        self._builder = EvidencePackBuilder(self.config)

    def build(self, retrieval_result: HybridRetrievalResult) -> AgentEvidenceBuildResult:
        pack = self._builder.build(retrieval_result)
        return AgentEvidenceBuildResult(
            pack=pack,
            selected_evidence_ids=[item.evidence_id for item in pack.all_evidence],
            candidate_chunk_ids=list(pack.candidate_chunk_ids),
            missing_coverage=list(pack.missing_coverage),
        )


def build_agent_evidence(
    retrieval_result: HybridRetrievalResult,
    *,
    config: EvidencePackBuilderConfig | None = None,
) -> AgentEvidenceBuildResult:
    pack = build_evidence_pack(retrieval_result, config=config)
    return AgentEvidenceBuildResult(
        pack=pack,
        selected_evidence_ids=[item.evidence_id for item in pack.all_evidence],
        candidate_chunk_ids=list(pack.candidate_chunk_ids),
        missing_coverage=list(pack.missing_coverage),
    )


def apply_evidence_build_result(state: AgentState, result: AgentEvidenceBuildResult) -> AgentState:
    state.retrieved_evidence = []
    state.citations = []
    state.add_evidence(result.pack.all_evidence)
    state.latest_evidence_pack_type = result.pack.pack_type.value
    state.latest_missing_coverage = list(result.missing_coverage)
    state.latest_candidate_chunk_ids = list(result.candidate_chunk_ids)
    state.latest_selected_evidence_ids = list(result.selected_evidence_ids)
    state.latest_pack_notes = list(result.pack.notes)
    for note in result.pack.notes:
        state.add_reasoning_note(note)
    return state
