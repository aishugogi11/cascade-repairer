# Transportation models

Two supervised models, trained offline, loaded at inference:

1. **Quality** (`train.py`) — hop quality in (0, 1). Used as environment scoring.
2. **Action policy** (`policy_train.py`) — utility of a candidate action given the current hop. The optimizer **executes** the highest feasible score.

```
Itinerary
   ↓ parse
Google Maps / demo geometry  →  what routes exist
Simulated rideshare (or a real RideshareProvider)  →  quotes / ETA
   ↓ candidate actions
Trained action forest  →  which action
   ↓ constraints
Action executor  →  updated itinerary
   ↓ re-observe
```

The LLM/voice layer does not pick the action.

## Dataset limitation

Both models train on a **synthetic** transportation dataset with a documented
data-generating process. We do **not** claim real-world ride labels or live
Uber/Lyft prices. `train.py --csv` accepts a real file with the same columns
when you have one.

## Train

From `backend/`:

```bash
python -m ml.transport.train
python -m ml.transport.policy_train
```

Writes `artifacts/transport_quality.joblib`, `metrics.json`,
`action_policy.joblib`, and `policy_metrics.json`. Metrics are from that
hold-out run — never hardcoded.

## Models

| Model | Role |
| --- | --- |
| Rules baseline | `policy.rules_select` (buffer / traffic / walk thresholds) |
| Linear Regression | Interpretable baseline |
| Random Forest | Production (quality + action utility) |

## Inference

`predict.predict_quality` and `policy_predict.predict_action_utility` load
artifacts once per process. Missing artifact → tagged heuristic fallback
(not presented as the forest).
