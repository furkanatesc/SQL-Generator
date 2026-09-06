"""Public API contract discovery endpoint (Sprint 30.0).

GET /api/v1 -> the machine-readable contract descriptor, wrapped in the
canonical success envelope. Public (no API key), side-effect-free,
deterministic. This is the reference endpoint the conformance guard holds
to the contract.
"""
from fastapi import APIRouter
from pydantic import BaseModel

from app.api.contract import API_V1_PREFIX, ApiResponse, contract_descriptor


class ContractDescriptor(BaseModel):
    version: str
    prefix: str
    request_id_header: str
    success_envelope_fields: list[str]
    pagination_fields: list[str]
    error_envelope: dict[str, list[str]]
    required_error_codes: list[str]


router = APIRouter(prefix=API_V1_PREFIX, tags=["api-contract"])


@router.get("", response_model=ApiResponse[ContractDescriptor])
def get_api_contract() -> ApiResponse[ContractDescriptor]:
    return ApiResponse[ContractDescriptor](
        data=ContractDescriptor(**contract_descriptor())
    )
