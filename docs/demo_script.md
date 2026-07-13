# NeuroBlackBox Demo Script

## Preflight

All names and observations used in this prototype are fictional and synthetic.

In the NeuroBlackBox project terminal, run:

```bash
python -m unittest discover -s tests -v
git check-ignore -v data/runtime_observations.csv
```

Confirm that `.env` uses the clean demo namespace:

```dotenv
NEUROBLACKBOX_CONTAINER=neuroblackbox_demo_patient_eleanor_v2
```

Start Supermemory Local, then start Streamlit. `Supermemory: Online` confirms a
bounded authenticated API request, not completion of asynchronous indexing.
Claim semantic retrieval only after the submitted source record appears in a
semantic query. `Local fallback` means the local record and deterministic
retrieval remain available, but the service probe did not verify Supermemory.

State the privacy boundary explicitly: the app, structured runtime record, and
Supermemory Local service run locally, but model-dependent Supermemory
operations may send relevant content to the configured external model provider.
Local-first does not mean that every processing dependency is local.

The tracked seed and every identity are synthetic. The app writes its canonical
CSV state only to the ignored runtime record, then conditionally submits records
to Supermemory Local. Exact-record deduplication and deterministic memory IDs
make the scripted entry repeat-safe. For a completely clean semantic namespace,
use a fresh container suffix; old container data is isolated, not deleted.

## 30-second opening

NeuroBlackBox is a local-first longitudinal memory system for caregiver-reported
cognitive-care observations.

Important context is created between clinical visits, but families may struggle
to reconstruct every dated observation during the next appointment.
NeuroBlackBox preserves the source record, makes it searchable across time, and
creates clinician-preparation outputs with explicit interpretation boundaries.

It does not diagnose, screen, predict, or recommend treatment.

## Demo flow

### 1. Show the boundary and verified state

Point to the clinical-boundary banner, then the memory-console status.

Explain:

> The Online label appears only after a read-only connection and authentication
> probe succeeds. It does not assert that a queued document has finished
> indexing. If the service is unavailable, the app says Local fallback and
> continues using the inspectable local record.

### 2. Add one fictional source observation

Use:

```text
Date: 2026-07-10
Type: speech
Severity: medium
Source: synthetic-demo-caregiver
Observation: After the afternoon walk, paused twice while recalling the name of a familiar park and then completed the story without prompting.
```

Click **Save observation**.

Expected result:

- the ignored runtime CSV is updated
- the tracked synthetic seed remains unchanged
- Online mode submits the record with a deterministic custom ID
- semantic results may appear only after asynchronous indexing finishes
- entering the exact record again does not create a duplicate

### 3. Ask about repeated questions

Ask:

```text
How have repeated questions changed?
```

Show the direct answer, evidence period, original source observations, and
interpretation boundary.

### 4. Ask about speech and pauses

Ask:

```text
What speech pauses or word-finding changes were recorded?
```

Show that the new source observation appears without being converted into a
clinical score or assessment.

### 5. Show the before-episode reconstruction

Ask:

```text
What was recorded before the latest high-severity episode?
```

Expected output includes:

- the latest high-severity episode
- the fixed review interval
- dated source observations preceding the episode
- the exact statement: **These observations were recorded before the episode.**
- an explicit boundary that sequence does not establish prediction or causation

### 6. Export clinician-preparation documents

Click:

1. **Download thirty-day brief**
2. **Download clinician summary**
3. **Download episode reconstruction**

## Closing line

NeuroBlackBox preserves caregiver-reported context between visits so the next
clinical conversation can begin with dated source observations instead of
reconstruction from memory. It remains a continuity and clinician-preparation
tool, not a diagnostic or predictive system.
