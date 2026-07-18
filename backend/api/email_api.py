"""Email debug endpoint — Phase 39.

POST /v1/email/test sends the canned deliverability test through the guarded
send module. Deliberately NOT on the access-gate allowlist, so it inherits
the X-Access-Code requirement automatically — safe to leave in place after
the event, and it doubles as the morning email smoke.

The response is the module's status dict verbatim: "disabled" and "error"
are honest visible outcomes, never 500s (a failed email must never look
like a broken service).
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from api.email_client import send_email

email_api = APIRouter()

TEST_SUBJECT = "Cascade test send"
TEST_BODY = (
    "This is a deliverability test from the Cascade service. "
    "No action is needed."
)


class TestSendRequest(BaseModel):
    to: str = Field(..., description="Recipient address for the test send.")


@email_api.post("/test", summary="Send the canned deliverability test email")
async def test_send(request: TestSendRequest):
    if "@" not in request.to:
        return JSONResponse(
            status_code=400, content={"error": "invalid recipient address"}
        )
    return await send_email(to=request.to, subject=TEST_SUBJECT, text=TEST_BODY)
