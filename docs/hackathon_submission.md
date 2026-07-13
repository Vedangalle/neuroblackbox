# NeuroBlackBox Hackathon Submission

## Project name

NeuroBlackBox

## One-liner

A local-first longitudinal memory system that turns caregiver-reported
observations into source-grounded clinician-preparation summaries.

## Built for

The Supermemory Local hackathon using a local service at `localhost:6767`.

## Problem

Caregiver-reported cognitive-care context is created during ordinary life:
speech pauses, repeated questions, disrupted routines, medication-related
observations, navigation confusion, improvements, and significant episodes.

At the next clinical visit, weeks of dated context may be compressed into a
fragmented recollection. Families need continuity, not software pretending to
make a diagnosis.

## What it does

NeuroBlackBox lets a caregiver record dated source observations and ask:

- What changed during the latest review period?
- How have repeated questions changed?
- What speech pauses or word-finding changes were recorded?
- What was recorded before the latest high-severity episode?
- Which source observations should be discussed at the next appointment?

The app produces conservative answers, evidence periods, original source
records, before-episode reconstruction, and downloadable clinician-preparation
documents.

## Local data and Supermemory integration

The public repository contains an immutable, fictional synthetic seed. On first
launch, the app copies it into an ignored runtime CSV. Every new entry is saved
atomically to that canonical local record before any semantic-memory submission.

The app performs a bounded read-only API probe. Only a successful probe produces
the `Online` state. When Online, startup/session reconciliation submits each
runtime observation to the configured Supermemory container using a
deterministic custom ID. The same exact observation resolves to the same ID,
making repeated submissions idempotent. Partial reconciliation is retried on a
later app run. Online does not prove asynchronous indexing has completed;
semantic retrieval is verified separately.

If the service is unavailable, the interface explicitly reports `Local
fallback`; deterministic retrieval and report generation remain available from
the runtime record.

Each semantic record retains:

- fictional patient identity
- observation date
- category
- caregiver-recorded severity
- source
- original observation text
- deterministic observation ID

## Main demo moment

The strongest question is:

> What was recorded before the latest high-severity episode?

NeuroBlackBox identifies the latest observation categorized as a high-severity
episode, selects a fixed preceding interval, orders its source observations, and
reports descriptive category counts.

The output states:

> These observations were recorded before the episode.

It then makes the interpretation boundary explicit: temporal sequence does not
establish prediction or causation.

## Why it matters

Families should not have to remember every detail at once. A persistent,
inspectable record can make the next clinician conversation more concrete while
keeping the original source observations visible for human review.

## Key features

- Fictional synthetic seed separated from ignored runtime data
- Structured caregiver-observation capture
- Supermemory Local health probe and transparent fallback state
- Deterministic custom IDs and idempotent reconciliation
- Semantic retrieval with visible source records
- Deterministic local retrieval fallback
- Grounded answers with evidence periods and interpretation boundaries
- Thirty-day observation brief
- Before-episode reconstruction
- Clinician-preparation summary
- Markdown downloads
- Built-in release-hardening regression tests

## Safety boundary

NeuroBlackBox does not diagnose, treat, screen, or predict Alzheimer’s,
dementia, or any medical condition. It does not assign disease risk, establish
causation, recommend treatment, replace a clinician, or replace an official
medical record.

It organizes caregiver-reported observations for human review and clinician
preparation.

## Privacy boundary

All names and records shipped in the repository are fictional and synthetic.
The runtime CSV is ignored by Git. Local-first execution reduces unnecessary
data movement for this prototype, but it does not by itself provide encryption,
access control, identity governance, clinical compliance, or production
authorization.

## Technical stack

- Python 3.12+
- Streamlit
- Pandas
- Supermemory Python SDK
- Supermemory Local
- Built-in `unittest` release checks

## Future direction

Potential future work includes multi-caregiver records, explicit clinical-visit
objects, appointment-preparation packets, voice-note ingestion, provenance-aware
reports, encrypted storage, role-based access, and formal usability or clinical
validation research.

These are research directions, not current product claims.

## Closing

NeuroBlackBox is a longitudinal record for caregiver-reported cognitive-care
observations: local-first, source-grounded, inspectable, and intentionally
bounded.
