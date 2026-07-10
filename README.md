# NeuroBlackBox

**Local-first cognitive change memory for caregivers preparing for doctor conversations.**

![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![Streamlit](https://img.shields.io/badge/Streamlit-App-red)
![Supermemory Local](https://img.shields.io/badge/Supermemory-Local-111827)
![Status](https://img.shields.io/badge/status-hackathon%20prototype-green)
![Safety](https://img.shields.io/badge/medical%20safety-observation%20only-yellow)

NeuroBlackBox helps families and caregivers track small day-to-day observations such as speech pauses, repeated questions, routine disruptions, and high-severity episodes. It turns those scattered notes into source-grounded summaries that can be brought to a clinician.

Built for the **Supermemory Local localhost:6767 hackathon**.

---

## The problem

Families often notice meaningful changes before a medical appointment, but those observations are scattered across memory, texts, notes, and conversations.

By the time they meet a doctor, they may only remember:

> Something feels different.

That statement may be true, but it is hard to act on.

NeuroBlackBox turns that into a structured observation timeline:

> Jun 25: repeated the same question five times.  
> Jun 28: long pauses and word-finding frustration.  
> Jun 30: evening confusion episode.

---

## What NeuroBlackBox does

NeuroBlackBox lets a caregiver:

- log cognitive, speech, routine, and episode observations
- store observations locally through Supermemory Local
- retrieve relevant memory cards through natural-language questions
- generate a 30-day change brief
- generate a before-bad-episode analysis
- generate and download a doctor-prep summary

The product is designed around practical caregiver questions:

- What changed over the last 30 days?
- Are pauses increasing?
- Are repeated questions increasing?
- What routines are breaking?
- What did we notice before the last bad episode?
- What should I bring up to a doctor?

---

## Main demo moment

Ask:

**What did we notice before the last bad episode?**

NeuroBlackBox identifies the latest high-severity episode, reviews observations in the days before it, and produces a source-grounded timeline.

Example output:

- Latest high-severity episode: Jun 30, 2026
- Episode note: Evening confusion episode. Did not recognize why medication box was on table.
- Jun 22: Left tea kettle on after leaving kitchen.
- Jun 25: Repeated question about whether son had called five times in one afternoon.
- Jun 28: Long pauses and visible frustration while searching for simple words.

This is the core idea: **not diagnosis, not prediction, just the right observations in the right order.**

---

## Safety boundary

NeuroBlackBox does **not** diagnose, treat, screen, or predict Alzheimer’s, dementia, or any medical condition.

It is an observation organization and doctor-prep tool.

The app intentionally avoids:

- diagnosis claims
- treatment recommendations
- disease prediction
- clinical risk scoring
- replacing medical professionals

It focuses on:

- caregiver observation logging
- source-grounded recall
- clinician-safe summaries
- better preparation for medical conversations

---

## Why local-first matters

Caregiver observations about cognitive change are sensitive. They may involve confusion, medication routines, repeated questions, behavioral changes, or family concerns.

NeuroBlackBox uses **Supermemory Local** so the memory layer can run on the user’s own machine during the prototype.

This gives the project a stronger privacy posture:

- observations can be stored locally
- memory search can run against local context
- sensitive family notes do not need to become a cloud-first dataset
- the user keeps more control over their information

---

## Features

| Feature | Status |
|---|---|
| Caregiver observation logging | Complete |
| CSV fallback storage | Complete |
| Supermemory Local write integration | Complete |
| Supermemory Local search | Complete |
| Readable memory result cards | Complete |
| 30-day change brief | Complete |
| Before bad episode analysis | Complete |
| Doctor-prep summary | Complete |
| Markdown summary downloads | Complete |
| Medical safety framing | Complete |

---

## Tech stack

- Python
- Streamlit
- Pandas
- Supermemory Python SDK
- Supermemory Local running at http://localhost:6767

---

## Repository structure

neuroblackbox/
- data/sample_observations.csv
- docs/demo_script.md
- docs/product_thesis.md
- docs/safety_positioning.md
- docs/hackathon_submission.md
- src/app.py
- src/memory_client.py
- README.md
- requirements.txt

---

## Run locally

Create and activate a Python environment:

python3 -m venv .venv  
source .venv/bin/activate  
pip install -r requirements.txt

Start Supermemory Local in a separate terminal:

npx supermemory local

Create a local .env file:

SUPERMEMORY_API_URL=http://localhost:6767  
SUPERMEMORY_API_KEY=local  
NEUROBLACKBOX_CONTAINER=neuroblackbox_demo_patient_eleanor

Run NeuroBlackBox:

streamlit run src/app.py

Open:

http://localhost:8501

---

## Demo script

A full walkthrough is available in:

docs/demo_script.md

Recommended demo flow:

1. Show the safety disclaimer.
2. Show Supermemory Local connection.
3. Add a caregiver observation.
4. Ask: Are repeated questions increasing?
5. Ask: Are pauses increasing?
6. Ask: What did we notice before the last bad episode?
7. Download the doctor-prep summary.

---

## Product thesis

The product thesis is available in:

docs/product_thesis.md

Core thesis:

> Caregivers do not need software pretending to be a doctor. They need a memory system that helps them remember what changed, organize it clearly, and bring useful observations to the actual doctor.

---

## Future direction

Potential future versions could support:

- voice note ingestion
- speech transcript analysis
- multi-caregiver timelines
- medication and routine tracking
- appointment-prep packets
- clinician handoff summaries
- longitudinal trend charts
- privacy-preserving family memory vaults

---

## Status

Hackathon prototype complete.

NeuroBlackBox demonstrates a working local-first memory workflow for sensitive caregiver observations using Supermemory Local.
