# Devpost copy — ML Empowerment Build Challenge 2.0

Paste this into Devpost. Record the 90-second video from the script at the bottom.
Deadline: **August 14, 2026, 11:45pm PDT**.

## Project title

**Cascade: ML Travel Recovery**

(Alternates if taken: *DelayRisk Recovery Agent*, *Don't Book the Next Delay*)

## Tagline (one line)

When your flight cancels, a trained delay-risk model — not a chatbot — ranks which alternative is least likely to strand you again.

## Built with

Python, FastAPI, scikit-learn, pandas, OpenAI Agents SDK, Featherless.ai, Saily, Sabre InstaFlights, Docker, Google Cloud Run

---

## Project description (paste)

### Problem statement

A cancelled or delayed flight is not a search problem. It is a **decision** problem under stress.

Travelers open five tabs, compare times and prices, and still cannot answer the question that matters: *which replacement is least likely to fail again?* Cheap connecting itineraries look attractive until a 42-minute layover and an evening departure produce another miss. People without a corporate travel desk — students, families, hourly workers — absorb that cost as missed exams, childcare, and wages.

Large language models can *talk* about flights. They cannot estimate delay risk from route structure. That is a supervised learning problem.

### Solution overview

**Cascade** is a voice and web travel-recovery agent. When you say your flight was cancelled:

1. The conversational agent extracts destination, date, and constraints.
2. Sabre InstaFlights retrieves real priced alternatives.
3. A **trained logistic regression model** predicts P(arrival delay ≥ 15 minutes) — the Bureau of Transportation Statistics On-Time definition.
4. A preference ranker mixes that risk with price, arrival time, stops, and duration.
5. You see and hear *why*: “24% disruption risk, nonstop, lands at 8:50 AM.”
6. Say “price matters more” or “I must arrive before 9” — the **same** options rerank. No second hallucination.

The concierge is the interface. The model is the intelligence.

### Key features

- **Disruption-risk scores** on every alternative (percent + match score)
- **Explainable factors** in traveler language (connection, evening departure, busy hub)
- **Live preference rerank** from speech, without a new search
- **Voice + screen together** so a stressed traveler does not have to read a spreadsheet
- **Separate train vs serve**: `python -m ml.train` writes an artifact; requests never retrain

### Technologies used

- **ML:** scikit-learn `LogisticRegression` pipeline (impute, scale, one-hot airline), hold-out ROC-AUC **0.76**, accuracy 0.69, recall 0.69. Training data is a BTS-calibrated On-Time set encoding published delay patterns (evening banks, connections, congested hubs, carrier differences). The trained artifact is loaded at inference time.
- **Concierge:** OpenAI Agents SDK with tools (`search_flights`, `set_recovery_preferences`, `book_flight`, `esim_plan`, …). Spoken text is **Featherless** when `FEATHERLESS_API_KEY` is set; Whisper STT and TTS stay on OpenAI.
- **Voice:** WebRTC orb (mouth/ears only — it does not pick the flight)
- **Inventory:** Sabre Flight Search / InstaFlights
- **eSIM:** Saily country catalog + checkout link on the itinerary (no live quote API)
- **App:** FastAPI, vanilla HTML dashboard, Docker, Cloud Run

### Target users

Students and independent travelers who cannot call a travel desk when a connection breaks the night before a midterm, a job interview, or a family event.

### What is real vs honest limits (judges notice this)

- Delay risk is a **real sklearn classifier** with a saved artifact and published metrics.
- Flight shopping can be live Sabre CERT inventory; mock mode is deterministic for rehearsal.
- Training labels are **BTS-calibrated synthetic** (not a 10GB BTS dump in the repo) so CI stays hermetic. Directional effects match published On-Time patterns. We would rather show an honest pipeline than a fake “neural net.”
- Precision is 0.44 at the 0.5 threshold because delay is the minority class — we report it instead of hiding it. Ranking uses the **probability**, not the hard label.
- Saily has no public booking API. We map the trip to a published country page and starting catalog price, then hand checkout to Saily. Voice never reads the URL; we never claim we installed an eSIM.

### Try it

- Live dashboard: https://talktomytrip.com/v1/cascade/ (or local `http://localhost:1019/v1/cascade/`)
- Repo: this GitHub URL
- Model metrics: `GET /v1/ml/metrics`

---

## Screenshots to capture (minimum 4)

1. **Four flight cards** with Recommended badge, disruption %, and why-bullets
2. **After “price matters more”** — United/cheap connection now #1, high risk visible
3. **After “arrive before 9”** — JetBlue 8:50 AM recommended
4. **ROC-AUC line** under Available flights (`Delay-risk model · logistic regression · ROC-AUC 0.76`)
5. Optional: terminal `python -m ml.train` printing accuracy / F1 / ROC-AUC

File names: `01-ml-ranked.png`, `02-price-rerank.png`, `03-arrive-before-9.png`, `04-model-metrics.png`

---

## 90-second video script (record this, nothing else)

**0:00–0:08 (problem)**  
“When your flight cancels, Google shows you times and prices. It cannot tell you which replacement will delay again.”

**0:08–0:20 (the model)**  
Screen: `backend/ml/train.py` + metrics table.  
“This is a trained logistic regression on On-Time delay labels. ROC-AUC 0.76. The chatbot does not invent this number.”

**0:20–0:45 (demo 1)**  
Cascade page, orb live.  
You: “My flight was canceled. JFK to LAX tomorrow morning.”  
Show cards. Point at **24% vs 55%**.  
“The model scored the cheap United connection at 55% delay risk. It recommends the morning nonstop.”

**0:45–1:05 (demo 2 — spoken preference rerank)**  
You: “Actually, price matters more.”  
Cards reorder.  
You: “Never mind — I have to arrive before 9 AM.”  
JetBlue 8:50 becomes #1.

**1:05–1:20 (impact)**  
“Students and families don’t have a corporate desk. This is a recovery ranking they can speak to.”

**1:20–1:30 (close)**  
Title card: *Cascade — ML Travel Recovery. The model ranks. The voice explains.*

Record in one take. Do not mention the other hackathon, PayPal, or iOS. Those dilute the ML story.

---

## What NOT to spend tomorrow on

- Neural nets / XGBoost (you will not beat 0.76 and ship a clean demo by 11:45pm)
- New APIs, iOS, email, PayPal, hotel repair
- Rewriting the README as if this repo was never Cascade Repairer — Devpost is the contest surface; keep the repo honest
- A 8-minute architecture tour

## Eligibility reminder

This challenge is **students only**. Companies and professional orgs are excluded. Submit as a student team (solo is allowed). List roles: ML pipeline, voice/agent, demo/video.
