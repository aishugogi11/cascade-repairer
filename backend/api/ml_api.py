"""ML metrics for the delay-risk and transportation-quality models."""
from fastapi import APIRouter

from ml.inference import model_metrics
from ml.transport.predict import model_metrics as transport_metrics

ml_api = APIRouter()


@ml_api.get("/metrics")
def metrics():
    """Hold-out metrics for the trained delay-risk model. Gated JSON."""
    return model_metrics()


@ml_api.get("/transport")
def transport():
    """Hold-out metrics for the transportation-quality forest."""
    return transport_metrics()


@ml_api.get("/transport/policy")
def transport_policy():
    """Hold-out metrics for the action-selection forest."""
    from ml.transport.policy_predict import policy_metrics
    return policy_metrics()
