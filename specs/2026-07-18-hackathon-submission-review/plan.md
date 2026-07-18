# Plan — Phase 42: Hackathon submission review (IMPLEMENTATION_DETAILS.md)

Documentation-only phase. Inputs: the version-1 draft and video transcript
(preserved verbatim in the Phase 42 roadmap entry), `specs/tech-stack.md`,
`specs/changelog.md`, `README.md`.

## 1. Verify the checkable claims

1.1 Run the hermetic suite in the container (`docker compose build backend &&
    docker run --rm hackathon-vocal-bridge-backend python -m pytest tests/ -q`)
    and record the exact passing count for the text's test-suite claim.
1.2 Confirm the Concierge tool list (eight tools) against `concierge.py` /
    tech-stack § Backend; confirm the state sequence wording
    (booked → broken + awaiting_consent → granted → repairing → fixed →
    results callback) against the shipped lifecycle.
1.3 Settle the integration-pattern sentence from README § Course integration
    patterns: orb ≈ Pattern 2 (voice for an existing agent), outbound calls
    use the Pattern 3 capability — replacing the literal
    `<insert pattern here (1, 2, or 3)>` placeholder.

## 2. Review version 1 → `review-notes.md`

2.1 Walk version 1 section by section against the shipped reality; log every
    factual correction, overstatement, typo, and structural call in
    `specs/2026-07-18-hackathon-submission-review/review-notes.md` — including
    the verdict (effective as-is vs. needs the fixes) the roadmap entry asks
    for.
2.2 Cross-check against the video transcript: everything the text claims that
    the video *shows* (spell-back email, Japanese switch, consent call,
    struck-through original flight, $80 refund visible in PayPal) should stay
    prominent — those are the judges' verifiable moments.

## 3. Write `IMPLEMENTATION_DETAILS.md`

3.1 Draft the paste-ready text at the repo root: v1's section structure
    (IDEA / IMPLEMENTATION / HOW WE USED VOCAL BRIDGE / HOW WE USED SABRE /
    ROADMAP), v1's register and approximate length, with every requirements.md
    correction applied — precise-but-confident real-vs-mock framing, eight
    tools, the pattern sentence, the verified test count, clean copy.
3.2 Fold the load-bearing details from v1's trailing numbered notes
    (different-flight guarantee, closest-time pick, price delta + PayPal
    payout, email beats, asyncio-parallel repairs, deployment posture) into
    the main sections; drop the duplication.
3.3 Ensure copy-paste survivability: plain prose under simple section
    headings, no tables/HTML/relative links; the only URL is
    https://talktomytrip.com/ (no `?code=`).

## 4. Close out

4.1 Re-read the final text once against requirements.md's corrections table —
    every row either applied or consciously N/A.
4.2 Run validation.md; stage the new files.
