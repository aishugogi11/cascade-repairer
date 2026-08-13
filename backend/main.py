import uvicorn
from fastapi import (
    FastAPI,
)
import os
import sys

sys.path.append("api")

from api.hello import hello
from api.vb_test import vb_test
from api.concurrency_spike import concurrency_spike
from api.disruption import disruption
from api.sabre_tools import sabre_tools
from api.outbound_call import outbound_call
from api.cascade_demo import cascade_demo
from api.web_call import web_call
from api.itinerary_ui import itinerary_ui
from api.booking_ui import booking_ui
from api.cascade_ui import cascade_ui
from api.demo import demo
from api.legal import legal
from api.mobile_voice import mobile_voice
from api.access_gate import access_gate_middleware
from api.auth import auth
from api.email_api import email_api
from api.ml_api import ml_api
from api.trip_builder_api import trip_builder_api
from api.build_ui import build_ui
from api.whatsapp_ui import whatsapp_ui
from api.whatsapp_demo import whatsapp_demo


app = FastAPI(
    title="Vocal Bridge Training API",
    version="1.0",
    description="Vocal Bridge Training API",
)

app.middleware("http")(access_gate_middleware)

app.include_router(
    hello,
    prefix="/v1/hello",
    tags=["hello"],
)

app.include_router(
    vb_test,
    prefix="/v1/vb_test",
    tags=["vb_test"],
)

app.include_router(
    concurrency_spike,
    prefix="/v1/concurrency_spike",
    tags=["concurrency_spike"],
)

app.include_router(
    disruption,
    prefix="/v1/disruption",
    tags=["disruption"],
)

app.include_router(
    sabre_tools,
    prefix="/v1/sabre_tools",
    tags=["sabre_tools"],
)

app.include_router(
    outbound_call,
    prefix="/v1/outbound_call",
    tags=["outbound_call"],
)

app.include_router(
    cascade_demo,
    prefix="/v1/cascade_demo",
    tags=["cascade_demo"],
)

app.include_router(
    web_call,
    prefix="/v1/web_call",
    tags=["web_call"],
)

app.include_router(
    itinerary_ui,
    prefix="/v1/itinerary",
    tags=["itinerary"],
)

app.include_router(
    booking_ui,
    prefix="/v1/booking",
    tags=["booking"],
)

app.include_router(
    cascade_ui,
    prefix="/v1/cascade",
    tags=["cascade"],
)

app.include_router(
    demo,
    prefix="/v1/demo",
    tags=["demo"],
)

app.include_router(
    legal,
    prefix="/v1/legal",
    tags=["legal"],
)

app.include_router(
    mobile_voice,
    prefix="/v1/mobile_voice",
    tags=["mobile_voice"],
)

app.include_router(
    auth,
    prefix="/v1/auth",
    tags=["auth"],
)

app.include_router(
    email_api,
    prefix="/v1/email",
    tags=["email"],
)

app.include_router(
    ml_api,
    prefix="/v1/ml",
    tags=["ml"],
)

app.include_router(
    trip_builder_api,
    prefix="/v1/trip_builder",
    tags=["trip_builder"],
)

app.include_router(
    build_ui,
    prefix="/v1/build",
    tags=["build"],
)

app.include_router(
    whatsapp_ui,
    prefix="/v1/whatsapp",
    tags=["whatsapp"],
)

app.include_router(
    whatsapp_demo,
    prefix="/v1/whatsapp",
    tags=["whatsapp"],
)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
