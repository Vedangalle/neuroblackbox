# NeuroBlackBox Safety Positioning

## 1. Safety Principle

NeuroBlackBox is an observation organization tool.

It is not a diagnostic product, treatment product, disease prediction product, emergency response product, or replacement for a licensed clinician.

The product is designed to help caregivers preserve and organize observations so they can have better conversations with medical professionals.

## 2. Core Boundary

NeuroBlackBox should never claim:

- this person has Alzheimer’s
- this person has dementia
- this person is declining
- this person is at medical risk
- this pattern predicts a disease
- this observation requires a specific treatment
- this observation confirms a condition

NeuroBlackBox should only claim:

- these observations were logged
- these observations occurred in this time window
- these categories appeared in the notes
- these events may be useful to discuss with a clinician
- this is a source-grounded summary of caregiver observations

## 3. Approved Product Language

Use language like:

- caregiver observation
- source-grounded timeline
- clinician-preparation summary
- clinician discussion
- recorded change
- repeated question
- routine disruption
- speech pause
- word-finding difficulty
- high-severity episode
- family memory record
- local memory layer
- observation window

## 4. Avoided Product Language

Avoid language like:

- diagnosis
- detection
- prediction
- dementia score
- Alzheimer’s risk
- cognitive impairment classification
- medical recommendation
- treatment plan
- clinical decision support
- emergency alert
- disease progression model

## 5. Default Disclaimer

NeuroBlackBox does not diagnose, treat, or predict Alzheimer’s, dementia, or any medical condition.

It organizes caregiver observations so families can discuss concrete changes with a clinician.

## 6. Why the Boundary Matters

The product operates around sensitive family and cognitive-health context.

A caregiver may enter observations involving:

- confusion
- medication
- repeated questions
- missed routines
- memory concerns
- sleep disruption
- emotional distress
- navigation difficulty
- speech or word-finding changes

These observations can be deeply personal. The product must not overstate what it knows.

The safest and strongest position is:

> We help families remember what they observed. We do not tell them what disease someone has.

## 7. Output Rules

Every generated summary should follow five rules:

1. Stay source-grounded.
2. Use dates and observations from the log.
3. Avoid disease labels unless the user wrote them as context.
4. Avoid causal claims.
5. End with clinician-safe framing.

## 8. Safe Output Example

Before the Jun 30 high-severity episode, the log shows a routine disruption on Jun 22, a repeated-question observation on Jun 25, and word-finding pauses on Jun 28.

These observations were recorded before the episode. Their sequence does not
establish prediction or causation. This is not a diagnosis, and the source
observations may be useful to discuss with a clinician.

## 9. Unsafe Output Example

These observations confirm Alzheimer’s disease and mean treatment should begin.

This is unsafe because it makes a diagnostic suggestion and implies treatment direction.

## 10. Product Design Implications

NeuroBlackBox should prefer:

- "high-severity episode" over "medical crisis"
- "caregiver-reported observation" over a clinical label
- "clinician-preparation summary" over "clinical report"
- "possible discussion points" over "recommendations"
- "source observations" over "evidence of disease"

## 11. Data Privacy Position

The product should treat caregiver observations as sensitive by default.

The tracked seed is wholly fictional, synthetic, and immutable. First launch
creates an ignored runtime record, and the app never writes caregiver entries
to the public seed. Real identifiers must never be added to the tracked sample.

The local-first architecture keeps the runtime record and configured memory
service on the user’s machine during this prototype. Local-first does not by
itself provide encryption, access control, identity governance, clinical
privacy compliance, or production authorization.

The `.env` file must never be committed.

The app should avoid logging API keys, private keys, or personal medical details in public repo files.

## 12. Clinician-Preparation North Star

The product should help a caregiver say:

> Here is what we observed, when it happened, and what seemed to repeat. Can you help us understand whether this matters?

That is safe, useful, and emotionally grounded.
