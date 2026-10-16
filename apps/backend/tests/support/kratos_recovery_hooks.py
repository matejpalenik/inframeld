"""Observe real Kratos hooks using an in-memory, test-only callback service.

Acknowledgments here are observations, not durable cleanup records. This probe
does not block product access, revoke Hydra grants, or implement reconciliation.
"""

import asyncio
import secrets
from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, SecretStr

RecoveryPhase = Literal["admit", "complete"]
TEST_RECOVERY_KEY = SecretStr("inframeld-recovery-hook-test-only")


class RecoveryEventRequest(BaseModel):
    """Identify the recovery flow, human and phase reported by Kratos."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    schema_version: Literal[1] = Field(alias="schemaVersion")
    flow_id: UUID = Field(alias="flowId")
    identity_id: UUID = Field(alias="identityId")
    event_kind: Literal["recovery"] = Field(alias="eventKind")
    phase: RecoveryPhase


class MockRecoveryPlanRequest(BaseModel):
    """Choose whether a flow's callbacks pause or reject a selected phase."""

    pause: bool = False
    reject_phase: RecoveryPhase | None = None


class MockRecoverySnapshotResponse(BaseModel):
    """Report callback arrivals and local acceptance, without proving delivery."""

    received: list[RecoveryEventRequest]
    acknowledged: list[RecoveryPhase]


def _gates() -> dict[RecoveryPhase, asyncio.Event]:
    """Create separate, initially closed release gates for one flow."""
    return {"admit": asyncio.Event(), "complete": asyncio.Event()}


@dataclass(slots=True)
class _FlowObservation:
    """Own one flow's in-memory controls, callback history and release gates."""

    plan: MockRecoveryPlanRequest = field(default_factory=MockRecoveryPlanRequest)
    operation_id: UUID = field(default_factory=uuid4)
    received: list[RecoveryEventRequest] = field(default_factory=list[RecoveryEventRequest])
    acknowledged: list[RecoveryPhase] = field(default_factory=list[RecoveryPhase])
    gates: dict[RecoveryPhase, asyncio.Event] = field(default_factory=_gates)


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
_observations: dict[UUID, _FlowObservation] = {}


def _require_key(request: Request) -> None:
    """Require one matching test-key header - otherwise raise HTTP 401."""
    values = request.headers.getlist("X-Inframeld-Recovery-Key")
    if len(values) != 1 or not secrets.compare_digest(
        values[0], TEST_RECOVERY_KEY.get_secret_value()
    ):
        raise HTTPException(status_code=401, detail="Invalid test service credential.")


@app.get("/health/ready")
async def ready() -> Response:
    """Return HTTP 200 when the callback recorder is responding."""
    return Response(status_code=200)


@app.put("/plans/{flow_id}", status_code=204)
async def configure(flow_id: UUID, plan: MockRecoveryPlanRequest, request: Request) -> Response:
    """Store a flow's plan - return 204, or 409 if callbacks have started."""
    _require_key(request)
    observation = _observations.setdefault(flow_id, _FlowObservation())
    if observation.received:
        raise HTTPException(status_code=409, detail="The test flow has already started.")
    observation.plan = plan
    return Response(status_code=204)


@app.get("/observations/{flow_id}")
async def snapshot(flow_id: UUID, request: Request) -> MockRecoverySnapshotResponse:
    """Return callback observations, or empty lists for an unknown flow."""
    _require_key(request)
    observation = _observations.get(flow_id)
    return MockRecoverySnapshotResponse(
        received=list(observation.received) if observation is not None else [],
        acknowledged=list(observation.acknowledged) if observation is not None else [],
    )


@app.post("/plans/{flow_id}/release/{phase}", status_code=204)
async def release(flow_id: UUID, phase: RecoveryPhase, request: Request) -> Response:
    """Open a phase gate - return 204 even when the flow is unknown."""
    _require_key(request)
    observation = _observations.get(flow_id)
    if observation is not None:
        observation.gates[phase].set()
    return Response(status_code=204)


@app.post("/internal/v1/identity-recovery/{phase}", status_code=202)
async def receive(phase: RecoveryPhase, event: RecoveryEventRequest, request: Request) -> Response:
    """Record a Kratos callback and apply this flow's test controls.

    Args:
        phase: URL phase, which must match the callback body.
        event: Recovery flow, identity and phase reported by Kratos.
        request: Incoming request carrying the test-service key.

    Returns:
        HTTP 202 with an in-memory receipt after local acceptance.

    Raises:
        HTTPException: 401 for an invalid key - 409 for a phase mismatch,
            an unreleased ten-second pause, or deliberate test rejection.

    Arrival is recorded before waiting or rejecting. Local acceptance does
    not prove Kratos received the response or that cleanup was persisted.
    """
    _require_key(request)
    if event.phase != phase:
        raise HTTPException(status_code=409, detail="The test phase does not match.")

    observation = _observations.setdefault(event.flow_id, _FlowObservation())
    observation.received.append(event)
    if observation.plan.pause:
        try:
            async with asyncio.timeout(10.0):
                await observation.gates[phase].wait()
        except TimeoutError:
            raise HTTPException(status_code=409, detail="Test callback was not released.") from None

    if observation.plan.reject_phase == phase:
        # Avoid provider retry delays when testing callback rejection.
        raise HTTPException(status_code=409, detail="Injected test callback failure.")

    observation.acknowledged.append(phase)
    return JSONResponse(
        content={
            "operationId": str(observation.operation_id),
            "eventKind": "recovery",
            "phase": phase,
            "recorded": True,
        },
        status_code=202,
    )
