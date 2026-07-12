# Vocal Bridge Course Glossary

This glossary defines the core technical components, architectural patterns, and industry metrics essential for building and evaluating high-performance voice AI applications.

---

## 1. Core Acronyms & Industry Metrics

> The technical building blocks and standards used to measure voice system performance.

* **ASR / STT (Speech-to-Text):** The front-end process of transcribing incoming audio into text strings. Also known as Automatic Speech Recognition.
* **GUI (Graphical User Interface):** Traditional visual interfaces (apps/websites) that often complement voice in multimodal applications.
* **IVR (Interactive Voice Response):** Traditional automated phone systems that interact with callers through voice and keypad (DTMF) inputs.
* **LLM (Large Language Model):** The "brain" of the agent; the reasoning engine that processes prompts, manages tools, and generates responses.
* **MOS (Mean Opinion Score):** A numerical rating (1–5) representing the human-perceived quality and naturalness of synthesized speech.
* **SIP (Session Initiation Protocol):** A core signaling protocol used to route, establish, and manage real-time telephony voice calls.
* **STT (Speech-to-Text):** The automated transcription process of converting raw acoustic audio signals into structured text strings.
* **TTFB (Time to First Byte):** A critical latency metric measuring the time between the end of a user’s utterance and the moment the system produces its first token or audio packet.
* **TTS (Text-to-Speech):** The synthesis engine that converts structured text into audible artificial speech.
* **VAD (Voice Activity Detection):** Technology used to determine if incoming audio contains active human speech or just background noise.
* **WER (Word Error Rate):** A deterministic metric used to measure transcription accuracy by comparing audio to a "ground-truth" transcript.

---

## 2. Architectural Frameworks

> Definitions of how systems are structured and how data flows between components.

* **Cascaded Stack (The "Sandwich"):** A traditional voice pipeline linking separate models in a sequence (STT $\rightarrow$ LLM $\rightarrow$ TTS). While easy to debug, it typically suffers from high latency (1–3s) and loses emotional nuance.
* **Concierge Architecture:** Vocal Bridge’s custom hybrid architecture. It uses a fast foreground agent to handle real-time flow (fillers, turn-taking) while delegating complex tasks to a background LLM agent for deep reasoning and tools.
* **Orchestrator:** The system layer that manages complex interactions, such as handling state, coordinating component timing, and managing interruptions.
* **Real-time Stack (Voice-to-Voice):** A single end-to-end model where audio is processed directly. It achieves ultra-low latency (200–500ms) but can be harder to control with domain-specific engineering.
* **Telephony Bridge:** The infrastructure (SIP, PSTN, or providers like Twilio) required to connect digital voice agents to traditional phone lines.
* **Vocal Bridge (VB):** The platform providing a "voice-to-voice brain" that sits in front of existing agents to manage dialogue, turn-taking, and paralinguistics.
* **WebRTC (Web Real-Time Communication):** The real-time communication protocol used for the bidirectional data channel that carries audio and application state between the agent and the client.

---

## 3. Conversational UX & Dynamics

> The elements that define how a voice interaction feels to a human user.

* **Barging / Interruption:** The capability of a voice agent to gracefully handle a user speaking over it mid-sentence, forcing the agent to stop talking and adapt to the new input.
* **Bridge Line:** A short spoken phrase (e.g., *"Let me check on that..."*) used by the foreground agent to fill the silence while delegating a complex query to the background agent.
* **Endpointing:** The process by which a voice system determines precisely when a user has finished speaking so the agent knows when to respond.
* **Latency:** The delay between a user’s input and the agent’s response. Reducing latency is critical for maintaining a natural conversational flow.
* **Multimodal:** An interface that utilizes multiple modes of interaction, such as a voice agent that simultaneously updates a visual GUI.
* **Paralinguistics / Prosody:** Non-verbal elements of speech—such as tone, pace, pitch, and emotion—that carry intent and context beyond literal text.
* **Turn-taking:** The timing and logic used to determine when an agent should speak, wait, or listen during a conversation.

---

## 4. Development & Methodology

> Best practices for engineering, testing, and deploying non-deterministic AI systems.

* **Client Actions:** A pattern using a bidirectional communication channel (WebRTC) to keep the voice agent and the application UI in perfect sync.
* **Eval-Driven Development:** An engineering discipline where automated evaluation scores are used as the primary signal to iterate on AI systems and bridge the gap between "demo" and "production."
* **Evals (Evaluations):** Systematic, repeatable tests used to score an AI system's outcomes against specific goals or ground truths.
* **Idempotent Pattern:** A coding practice ensuring that setup blocks can be run multiple times safely by reusing existing resource IDs rather than creating duplicate agents.
* **Multimodal Judge:** An LLM used to score qualitative aspects of a voice interaction, such as tone match and conversational naturalness.
* **RAG (Retrieval-Augmented Generation):** A technique for providing LLMs with specific domain knowledge or memory by retrieving information from external documents.
* **Telemetry:** The collection and analysis of real-time data (latency, error rates, costs) to monitor system performance in production.