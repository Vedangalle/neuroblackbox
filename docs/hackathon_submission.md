# NeuroBlackBox Hackathon Submission

## Project Name

NeuroBlackBox

## One-Liner

A local-first cognitive change memory that helps caregivers turn scattered observations into source-grounded doctor-prep summaries.

## Built For

Supermemory Local `<localhost:6767>` hackathon.

## Problem

Caregivers often notice meaningful cognitive or routine changes before a doctor visit, but those observations are scattered across memory, family conversations, texts, and notes.

By the time the appointment arrives, the caregiver may only remember:

> Something feels different.

That is emotionally real, but hard to act on.

NeuroBlackBox turns scattered observations into a structured memory timeline.

## What It Does

NeuroBlackBox lets caregivers log observations such as:

- speech pauses
- word-finding difficulty
- repeated questions
- routine disruptions
- missed medication routines
- high-severity confusion episodes

The app then helps answer:

- What changed over the last 30 days?
- Are pauses increasing?
- Are repeated questions increasing?
- What routines are breaking?
- What did we notice before the last bad episode?
- What should we bring up to a doctor?

## Supermemory Local Integration

NeuroBlackBox uses Supermemory Local as the local memory layer.

Each caregiver observation is stored with structured metadata:

- patient
- date
- observation type
- severity
- source
- observation text

When the caregiver asks a question, the app searches Supermemory Local and returns relevant memory cards.

This makes the app more than a static dashboard. It becomes a local memory system for sensitive caregiver context.

## Main Demo Moment

The strongest demo question is:

> What did we notice before the last bad episode?

NeuroBlackBox identifies the latest high-severity episode, reviews the observations before it, and generates a clinician-safe pre-episode timeline.

Example output:

- Jun 22: routine disruption
- Jun 25: repeated question
- Jun 28: speech pauses and word-finding frustration
- Jun 30: high-severity evening confusion episode

The app does not claim diagnosis or prediction. It shows the source-grounded observation pattern.

## Why It Matters

Families do not need software pretending to be a doctor.

They need a system that helps them remember what happened, organize it clearly, and bring useful observations to the actual doctor.

NeuroBlackBox is designed for that gap.

## Key Features

- Local caregiver observation logging
- Supermemory Local memory storage
- Supermemory Local search
- Readable memory result cards
- 30-day change brief
- Before bad episode analysis
- Doctor-prep summary
- Markdown downloads
- Explicit medical safety framing

## Safety Boundary

NeuroBlackBox does not diagnose, treat, screen, or predict Alzheimer’s, dementia, or any medical condition.

It organizes caregiver observations so families can discuss concrete changes with a clinician.

## Technical Stack

- Python
- Streamlit
- Pandas
- Supermemory Python SDK
- Supermemory Local

## Future Direction

Future versions could support:

- voice note ingestion
- multi-caregiver timelines
- appointment-prep packets
- clinician handoff summaries
- routine and medication tracking
- privacy-preserving family memory vaults
- longitudinal trend charts

## Closing

NeuroBlackBox is a black box for human cognitive change observations.

Not a diagnostic black box.

A memory black box.

A way for families to preserve the small signals that are easy to forget but important to discuss.
