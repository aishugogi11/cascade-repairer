"""Access-code validation — Phase 17, the iOS first-launch check.

One endpoint: the app POSTs the code the user typed, gets a clean 200/401,
and only then stores the code in the Keychain. The route itself is on the
gate's public allowlist (it is the gate's front door); the comparison logic
is shared with the middleware so the two can never disagree.
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from api.access_gate import code_is_valid

auth = APIRouter()


class ValidateRequest(BaseModel):
    code: str = Field(..., description="The shared demo access code.")


@auth.post("/validate", summary="Validate the demo access code")
def validate(request: ValidateRequest):
    if code_is_valid(request.code):
        return {"valid": True}
    return JSONResponse(
        status_code=401,
        content={"valid": False, "error": "invalid access code"},
    )
