# NeuroBlackBox

Local-first cognitive change memory for caregivers.

NeuroBlackBox helps families and caregivers track small day-to-day observations such as speech pauses, repeated questions, routine disruptions, and high-severity episodes. It turns those observations into source-grounded summaries that can be brought to a clinician.

Built for the Supermemory Local localhost:6767 hackathon.

## What it does

NeuroBlackBox lets a caregiver:

- Log observations over time
- Store observations locally in Supermemory Local
- Ask questions like:
  - What changed over the last 30 days?
  - Are pauses increasing?
  - Are repeated questions increasing?
  - What routines are breaking?
  - What did we notice before the last bad episode?
- Generate a doctor-prep summary
- Generate a before-episode analysis
- Download clinician-safe summaries as Markdown

## Why it matters

Families often notice meaningful changes before a medical appointment, but the observations are scattered across memory, texts, notes, and conversations.

By the time they meet a doctor, they may only remember vague statements like:

> Something feels different.

NeuroBlackBox turns that into a structured, source-grounded timeline:

> On Jun 25, repeated the same question five times. On Jun 28, had long pauses and word-finding frustration. On Jun 30, had an evening confusion episode.

## What it is not

NeuroBlackBox does not diagnose, treat, predict, or screen for Alzheimer’s, dementia, or any medical condition.

It is an observation organization and doctor-prep tool.

## Core demo

1. Start Supermemory Local.
2. Run the Streamlit app.
3. Add caregiver observations.
4. Ask: Are pauses increasing?
5. Ask: Are repeated questions increasing?
6. Ask: What did we notice before the last bad episode?
7. Download the doctor-prep summary.

## Tech stack

- Python
- Streamlit
- Pandas
- Supermemory Python SDK
- Supermemory Local running at http://localhost:6767

## Run locally

Install dependencies:

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

Start Supermemory Local in a separate terminal:

npx supermemory local

Create a local .env file:

SUPERMEMORY_API_URL=http://localhost:6767
SUPERMEMORY_API_KEY=local
NEUROBLACKBOX_CONTAINER=neuroblackbox_demo_patient_eleanor

Run the app:

streamlit run src/app.py

Open:

http://localhost:8501

## Safety positioning

NeuroBlackBox is designed around clinician-safe language.

It avoids diagnosis claims, treatment recommendations, prediction claims, and replacing medical professionals.

It focuses on observation logging, source-grounded recall, caregiver organization, and clinician conversation prep.

## Status

Prototype complete:

- Local observation logging
- Supermemory Local storage
- Supermemory Local search
- 30-day change brief
- Before bad episode analysis
- Doctor-prep summary export
