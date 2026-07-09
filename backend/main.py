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


app = FastAPI(
    title="Vocal Bridge Training API",
    version="1.0",
    description="Vocal Bridge Training API",
)

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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
