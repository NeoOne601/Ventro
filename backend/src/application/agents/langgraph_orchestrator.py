"""
LangGraph State Machine - Central Orchestrator for MAS-VGFR
Implements the Supervisor (Tool-Calling) Architecture described in the blueprint.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Annotated, Any, Literal

import structlog
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from ..config import get_settings
from ...domain.entities import (
    ReconciliationSession,
    ReconciliationStatus,
)
from ...domain.interfaces import (
    IDocumentStore,
    ILLMClient,
    IProgressPublisher,
    IReconciliationRepository,
    IVectorStore,
)

logger = structlog.get_logger(__name__)
settings = get_settings()


class AgentState(TypedDict):
    """Shared global state matrix for all agents in the LangGraph."""
    session_id: str
    po_document_id: str
    grn_document_id: str
    invoice_document_id: str

    # Documents
    po_parsed: dict[str, Any] | None
    grn_parsed: dict[str, Any] | None
    invoice_parsed: dict[str, Any] | None

    # Extraction results
    po_line_items: list[dict[str, Any]]
    grn_line_items: list[dict[str, Any]]
    invoice_line_items: list[dict[str, Any]]
    extracted_citations: list[dict[str, Any]]

    # Quantitative validation
    quantitative_report: dict[str, Any] | None
    math_discrepancies: list[dict[str, Any]]

    # Compliance
    compliance_report: dict[str, Any] | None

    # Reconciliation
    line_item_matches: list[dict[str, Any]]
    reconciliation_verdict: dict[str, Any] | None

    # SAMR
    samr_metrics: dict[str, Any] | None
    samr_alert_triggered: bool

    # Workpaper
    workpaper: dict[str, Any] | None

    # Agent coordination
    messages: Annotated[list[dict[str, Any]], add_messages]
    current_agent: str
    agent_trace: list[dict[str, Any]]
    errors: list[str]
    status: str
    iteration_count: int


class LangGraphOrchestrator:
    """
    Orchestrates the multi-agent workflow using LangGraph state machines.
    Implements cyclic, event-driven agent coordination with exception handling.
    """

    def __init__(
        self,
        llm_client: ILLMClient,
        vector_store: IVectorStore,
        document_store: IDocumentStore,
        reconciliation_repo: IReconciliationRepository,
        progress_publisher: IProgressPublisher,
    ) -> None:
        self.llm = llm_client
        self.vector_store = vector_store
        self.doc_store = document_store
        self.recon_repo = reconciliation_repo
        self.progress = progress_publisher

        # Import agents lazily to avoid circular imports
        from .extraction_agent import ExtractionAgent
        from .quantitative_agent import QuantitativeAgent
        from .compliance_agent import ComplianceAgent
        from .reconciliation_agent import ReconciliationAgent
        from .drafting_agent import DraftingAgent
        from .samr_agent import SAMRAgent

        self.extraction_agent = ExtractionAgent(llm_client, vector_store)
        self.quantitative_agent = QuantitativeAgent(llm_client)
        self.compliance_agent = ComplianceAgent(llm_client)
        self.reconciliation_agent = ReconciliationAgent(llm_client)
        self.drafting_agent = DraftingAgent(llm_client)
        self.samr_agent = SAMRAgent(llm_client)

        self.graph = self._build_graph()

    def _build_graph(self) -> Any:
        """Build and compile the LangGraph state machine."""
        workflow = StateGraph(AgentState)

        # Add agent nodes
        workflow.add_node("supervisor", self._supervisor_node)
        workflow.add_node("extraction", self._extraction_node)
        workflow.add_node("quantitative", self._quantitative_node)
        workflow.add_node("compliance", self._compliance_node)
        workflow.add_node("samr", self._samr_node)
        workflow.add_node("reconciliation", self._reconciliation_node)
        workflow.add_node("drafting", self._drafting_node)

        # Entry point
        workflow.set_entry_point("supervisor")

        # Supervisor routes to appropriate agent
        workflow.add_conditional_edges(
            "supervisor",
            self._supervisor_router,
            {
                "extraction": "extraction",
                "quantitative": "quantitative",
                "compliance": "compliance",
                "samr": "samr",
                "reconciliation": "reconciliation",
                "drafting": "drafting",
                "end": END,
            },
        )

        # Sequential flow with supervisor checkpoints
        workflow.add_edge("extraction", "supervisor")
        workflow.add_edge("quantitative", "supervisor")
        workflow.add_edge("compliance", "supervisor")
        workflow.add_edge("samr", "supervisor")
        workflow.add_edge("reconciliation", "supervisor")
        workflow.add_edge("drafting", END)

        return workflow.compile()

    def _supervisor_router(self, state: AgentState) -> str:
        """Supervisor routing logic based on current state."""
        status = state["status"]
        iteration = state.get("iteration_count", 0)

        # Safety limit
        if iteration > 20:
            logger.warning("max_iterations_reached", session_id=state["session_id"])
            return "end"

        # Check for fatal errors
        if len(state.get("errors", [])) > 3:
            return "end"

        if status == "initialized":
            return "extraction"
        elif status == "extracted":
            return "quantitative"
        elif status == "quantified":
            return "compliance"
        elif status == "compliance_checked":
            return "samr" if settings.samr_enabled else "reconciliation"
        elif status == "samr_complete":
            return "reconciliation"
        elif status == "reconciled":
            return "drafting"
        else:
            return "end"

    async def _supervisor_node(self, state: AgentState) -> dict[str, Any]:
        """Central supervisor - manages state and logs progress."""
        session_id = state["session_id"]
        status = state["status"]

        logger.info("supervisor_checkpoint", session_id=session_id, status=status)

        await self.progress.publish(session_id, {
            "event": "supervisor_checkpoint",
            "status": status,
            "iteration": state.get("iteration_count", 0),
            "timestamp": time.time(),
        })

        return {
            "current_agent": "supervisor",
            "iteration_count": state.get("iteration_count", 0) + 1,
            "agent_trace": state.get("agent_trace", []) + [{
                "agent": "supervisor",
                "checkpoint": status,
                "timestamp": time.time(),
            }],
        }

    async def _extraction_node(self, state: AgentState) -> dict[str, Any]:
        """Run the Extraction Agent."""
        session_id = state["session_id"]
        logger.info("extraction_agent_start", session_id=session_id)

        await self.progress.publish(session_id, {
            "event": "agent_started",
            "agent": "extraction",
            "message": "Extracting and indexing line items from all documents...",
        })

        try:
            result = await self.extraction_agent.run(state)
            await self.progress.publish(session_id, {
                "event": "agent_completed",
                "agent": "extraction",
                "items_extracted": len(result.get("po_line_items", [])),
            })
            return {**result, "status": "extracted"}
        except Exception as e:
            logger.error("extraction_failed", session_id=session_id, error=str(e))
            return {"errors": state.get("errors", []) + [f"Extraction: {e}"], "status": "extracted"}

    async def _quantitative_node(self, state: AgentState) -> dict[str, Any]:
        """Run the Quantitative Agent."""
        session_id = state["session_id"]
        logger.info("quantitative_agent_start", session_id=session_id)

        await self.progress.publish(session_id, {"event": "agent_started", "agent": "quantitative",
                                                  "message": "Performing mathematical validation..."})

        try:
            result = await self.quantitative_agent.run(state)
            return {**result, "status": "quantified"}
        except Exception as e:
            logger.error("quantitative_failed", session_id=session_id, error=str(e))
            return {"errors": state.get("errors", []) + [f"Quantitative: {e}"], "status": "quantified"}

    async def _compliance_node(self, state: AgentState) -> dict[str, Any]:
        """Run the Compliance Agent."""
        session_id = state["session_id"]
        await self.progress.publish(session_id, {"event": "agent_started", "agent": "compliance",
                                                  "message": "Evaluating regulatory compliance..."})
        try:
            result = await self.compliance_agent.run(state)
            return {**result, "status": "compliance_checked"}
        except Exception as e:
            logger.error("compliance_failed", session_id=session_id, error=str(e))
            return {"errors": state.get("errors", []) + [f"Compliance: {e}"], "status": "compliance_checked"}

    async def _samr_node(self, state: AgentState) -> dict[str, Any]:
        """Run Shadow Agent Memory Reconciliation."""
        session_id = state["session_id"]
        await self.progress.publish(session_id, {"event": "agent_started", "agent": "samr",
                                                  "message": "Running SAMR hallucination detection..."})
        try:
            result = await self.samr_agent.run(state)

            if result.get("samr_alert_triggered"):
                await self.progress.publish(session_id, {
                    "event": "samr_alert",
                    "severity": "high",
                    "message": "⚠️ SAMR Alert: Reasoning divergence detected. Human review required.",
                    "metrics": result.get("samr_metrics"),
                })

            return {**result, "status": "samr_complete"}
        except Exception as e:
            logger.error("samr_failed", session_id=session_id, error=str(e))
            return {"errors": state.get("errors", []) + [f"SAMR: {e}"], "status": "samr_complete",
                    "samr_alert_triggered": False}

    async def _reconciliation_node(self, state: AgentState) -> dict[str, Any]:
        """Run the Reconciliation Agent - core three-way match."""
        session_id = state["session_id"]
        await self.progress.publish(session_id, {"event": "agent_started", "agent": "reconciliation",
                                                  "message": "Performing three-way match reconciliation..."})
        try:
            result = await self.reconciliation_agent.run(state)
            await self.progress.publish(session_id, {
                "event": "agent_completed",
                "agent": "reconciliation",
                "verdict": result.get("reconciliation_verdict", {}).get("status"),
            })
            return {**result, "status": "reconciled"}
        except Exception as e:
            logger.error("reconciliation_failed", session_id=session_id, error=str(e))
            return {"errors": state.get("errors", []) + [f"Reconciliation: {e}"], "status": "reconciled"}

    async def _drafting_node(self, state: AgentState) -> dict[str, Any]:
        """Run the Drafting Agent - generate audit workpaper."""
        session_id = state["session_id"]
        await self.progress.publish(session_id, {"event": "agent_started", "agent": "drafting",
                                                  "message": "Generating audit workpaper..."})
        try:
            result = await self.drafting_agent.run(state)
            await self.progress.publish(session_id, {
                "event": "workflow_complete",
                "message": "✅ Reconciliation complete. Workpaper generated.",
            })
            return {**result, "status": "completed"}
        except Exception as e:
            logger.error("drafting_failed", session_id=session_id, error=str(e))
            return {"errors": state.get("errors", []) + [f"Drafting: {e}"], "status": "completed"}

    async def run_reconciliation(self, session: ReconciliationSession) -> AgentState:
        """Entry point: run the full reconciliation workflow for a session."""
        initial_state: AgentState = {
            "session_id": session.id,
            "po_document_id": session.po_document_id,
            "grn_document_id": session.grn_document_id,
            "invoice_document_id": session.invoice_document_id,
            "po_parsed": None,
            "grn_parsed": None,
            "invoice_parsed": None,
            "po_line_items": [],
            "grn_line_items": [],
            "invoice_line_items": [],
            "extracted_citations": [],
            "quantitative_report": None,
            "math_discrepancies": [],
            "compliance_report": None,
            "line_item_matches": [],
            "reconciliation_verdict": None,
            "samr_metrics": None,
            "samr_alert_triggered": False,
            "workpaper": None,
            "messages": [],
            "current_agent": "supervisor",
            "agent_trace": [],
            "errors": [],
            "status": "initialized",
            "iteration_count": 0,
        }

        logger.info("reconciliation_workflow_start", session_id=session.id)
        final_state = await self.graph.ainvoke(initial_state)
        logger.info("reconciliation_workflow_complete", session_id=session.id,
                    status=final_state.get("status"))
        return final_state
