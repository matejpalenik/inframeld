"""Gate fixed-target native delivery without adding production control endpoints."""

import asyncio
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal
from uuid import UUID

import httpx2
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field


class Phase(StrEnum):
    ADMIT = "admit"
    SETTINGS = "settings"
    PASSWORD_SAVED = "password-saved"


class Position(StrEnum):
    BEFORE = "before"
    AFTER = "after"


class Action(StrEnum):
    PAUSE = "pause"
    FAIL = "fail"


_KEY = "inframeld-native-recovery-hook-test-only"


class NativeEvidenceObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[2] = Field(alias="schemaVersion")
    event_type: str = Field(alias="eventType")
    identity_id: UUID = Field(alias="identityId")
    recovery_flow_id: UUID | None = Field(default=None, alias="recoveryFlowId")
    event_kind: str | None = Field(default=None, alias="eventKind")
    settings_flow_id: UUID | None = Field(default=None, alias="settingsFlowId")
    session_id: UUID | None = Field(default=None, alias="sessionId")
    source_recovery_flow_id: UUID | None = Field(default=None, alias="sourceRecoveryFlowId")


class NativeDeliveryPlan(BaseModel):
    position: Position = Position.BEFORE
    action: Action = Action.PAUSE


@dataclass(slots=True)
class _Delivery:
    plan: NativeDeliveryPlan | None = None
    used: bool = False
    arrived: asyncio.Event = field(default_factory=asyncio.Event)
    release: asyncio.Event = field(default_factory=asyncio.Event)
    observations: list[NativeEvidenceObservation] = field(
        default_factory=lambda: list[NativeEvidenceObservation]()
    )
    statuses: list[int] = field(default_factory=lambda: list[int]())


def create_native_recovery_forwarder_router() -> APIRouter:
    router = APIRouter(prefix="/internal/test/native-recovery")
    deliveries: dict[tuple[UUID, Phase], _Delivery] = {}

    def authenticate(request: Request) -> None:
        if request.headers.getlist("X-Inframeld-Recovery-Key") != [_KEY]:
            raise HTTPException(401)

    @router.put("/controls/{identity}/{phase}")
    async def configure(
        identity: UUID, phase: Phase, plan: NativeDeliveryPlan, request: Request
    ) -> Response:
        authenticate(request)
        prior = deliveries.get((identity, phase))
        if prior is not None:
            prior.release.set()
        deliveries[(identity, phase)] = _Delivery(plan=plan)
        return Response(status_code=204)

    @router.post("/controls/{identity}/{phase}/wait")
    async def wait(identity: UUID, phase: Phase, request: Request) -> Response:
        authenticate(request)
        state = deliveries.setdefault((identity, phase), _Delivery())
        try:
            await asyncio.wait_for(state.arrived.wait(), 10)
        except TimeoutError:
            raise HTTPException(504) from None
        return Response(status_code=204)

    @router.post("/controls/{identity}/{phase}/release")
    async def release(identity: UUID, phase: Phase, request: Request) -> Response:
        authenticate(request)
        deliveries.setdefault((identity, phase), _Delivery()).release.set()
        return Response(status_code=204)

    @router.get("/observations/{identity}/{phase}")
    async def observations(identity: UUID, phase: Phase, request: Request) -> dict[str, object]:
        authenticate(request)
        state = deliveries.setdefault((identity, phase), _Delivery())
        return {
            "received": [
                e.model_dump(mode="json", by_alias=True, exclude_unset=True)
                for e in state.observations
            ],
            "statuses": state.statuses,
        }

    @router.delete("/controls/{identity}/{phase}")
    async def clear(identity: UUID, phase: Phase, request: Request) -> Response:
        authenticate(request)
        state = deliveries.setdefault((identity, phase), _Delivery())
        state.plan = None
        state.release.set()
        return Response(status_code=204)

    @router.post("/{phase}")
    async def forward(phase: Phase, request: Request) -> Response:
        authenticate(request)
        body = await request.body()
        if len(body) > 8192:
            raise HTTPException(413)
        evidence = NativeEvidenceObservation.model_validate_json(body)
        state = deliveries.setdefault((evidence.identity_id, phase), _Delivery())
        state.observations.append(evidence)
        plan = (
            state.plan
            if not state.used or (state.plan is not None and state.plan.action == Action.FAIL)
            else None
        )
        state.used = True

        async def gate(position: str) -> None:
            if plan is None or plan.position != position:
                return
            state.arrived.set()
            if plan.action == Action.FAIL:
                raise HTTPException(503)
            try:
                await asyncio.wait_for(state.release.wait(), 10)
            except TimeoutError:
                raise HTTPException(504) from None

        await gate(Position.BEFORE)
        try:
            async with httpx2.AsyncClient(
                timeout=5.0, trust_env=False, follow_redirects=False
            ) as client:
                response = await client.post(
                    f"http://recovery-callbacks:8081/internal/v2/identity-recovery/{phase}",
                    content=body,
                    headers={"X-Inframeld-Recovery-Key": _KEY, "Content-Type": "application/json"},
                )
        except httpx2.TransportError:
            raise HTTPException(503) from None
        state.statuses.append(response.status_code)
        await gate(Position.AFTER)
        return Response(
            status_code=response.status_code,
            content=response.content,
            media_type=response.headers.get("content-type"),
        )

    return router
