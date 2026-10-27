"""Pause one real token request before Hydra persists its response.

Only the selected subject, client and grant type are observed. Incoming hook
payloads can contain credentials and are never retained or returned.
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from json import JSONDecodeError
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, ValidationError

type GrantType = Literal["authorization_code", "refresh_token"]


class _Identity(BaseModel):
    model_config = ConfigDict(extra="ignore", hide_input_in_errors=True)
    subject: UUID


class _Session(BaseModel):
    model_config = ConfigDict(extra="ignore", hide_input_in_errors=True)
    id_token: _Identity


class _TokenRequest(BaseModel):
    model_config = ConfigDict(extra="ignore", hide_input_in_errors=True)
    client_id: str
    grant_types: list[str]


class _Envelope(BaseModel):
    model_config = ConfigDict(extra="ignore", hide_input_in_errors=True)
    session: _Session
    request: _TokenRequest


class MockTokenHookObservationDTO(BaseModel):
    subject: UUID
    client_id: str
    grant_type: GrantType
    arrivals: int


@dataclass(slots=True)
class _Plan:
    arrived: asyncio.Event = field(default_factory=asyncio.Event)
    release: asyncio.Event = field(default_factory=asyncio.Event)
    arrivals: int = 0


def create_hydra_token_hook_router(
    require_key: Callable[[Request], None], *, gate_timeout_seconds: float = 10.0
) -> APIRouter:
    router = APIRouter()
    plans: dict[tuple[UUID, GrantType], _Plan] = {}

    @router.put("/hydra/token-plans/{subject}/{grant}", status_code=204)
    async def arm(subject: UUID, grant: GrantType, request: Request) -> Response:
        require_key(request)
        key = (subject, grant)
        if key in plans:
            raise HTTPException(status_code=409, detail="A test plan is already armed.")
        plans[key] = _Plan()
        return Response(status_code=204)

    @router.get("/hydra/token-plans/{subject}/{grant}/arrived")
    async def arrived(
        subject: UUID, grant: GrantType, request: Request
    ) -> MockTokenHookObservationDTO:
        require_key(request)
        plan = plans.get((subject, grant))
        if plan is None:
            raise HTTPException(status_code=404)
        try:
            async with asyncio.timeout(gate_timeout_seconds):
                await plan.arrived.wait()
        except TimeoutError:
            raise HTTPException(status_code=409, detail="The test hook did not arrive.") from None
        return MockTokenHookObservationDTO(
            subject=subject, client_id="inframeld-cli", grant_type=grant, arrivals=plan.arrivals
        )

    @router.post("/hydra/token-plans/{subject}/{grant}/release", status_code=204)
    async def release(subject: UUID, grant: GrantType, request: Request) -> Response:
        require_key(request)
        plan = plans.get((subject, grant))
        if plan is not None:
            plan.release.set()
        return Response(status_code=204)

    @router.delete("/hydra/token-plans/{subject}/{grant}", status_code=204)
    async def remove(subject: UUID, grant: GrantType, request: Request) -> Response:
        require_key(request)
        plan = plans.pop((subject, grant), None)
        if plan is not None:
            plan.release.set()
        return Response(status_code=204)

    @router.post("/internal/test/hydra/token", status_code=204)
    async def receive(request: Request) -> Response:
        require_key(request)
        try:
            event = _Envelope.model_validate(await request.json())
        except (ValidationError, JSONDecodeError):
            raise HTTPException(status_code=400, detail="Invalid test hook payload.") from None
        if event.request.client_id != "inframeld-cli":
            return Response(status_code=204)
        for grant in ("authorization_code", "refresh_token"):
            if grant not in event.request.grant_types:
                continue
            plan = plans.get((event.session.id_token.subject, grant))
            if plan is None or plan.arrivals:
                continue
            plan.arrivals += 1
            plan.arrived.set()
            try:
                async with asyncio.timeout(gate_timeout_seconds):
                    await plan.release.wait()
            except TimeoutError:
                raise HTTPException(
                    status_code=403, detail="The test token hook was not released."
                ) from None
        return Response(status_code=204)

    return router
