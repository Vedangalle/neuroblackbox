from pathlib import Path
from datetime import datetime

import pandas as pd
import streamlit as st


DATA_PATH = Path("data/sample_observations.csv")


st.set_page_config(
    page_title="NeuroBlackBox",
    page_icon="🧠",
    layout="wide",
)


def load_data() -> pd.DataFrame:
    if DATA_PATH.exists():
        df = pd.read_csv(DATA_PATH)
        df["date"] = pd.to_datetime(df["date"])
        return df.sort_values("date")
    return pd.DataFrame(columns=["date", "type", "severity", "source", "observation"])


def keyword_count(text: str, keywords: list[str]) -> int:
    text_lower = text.lower()
    return sum(text_lower.count(keyword) for keyword in keywords)


def analyze_changes(df: pd.DataFrame) -> dict:
    if df.empty:
        return {
            "total_observations": 0,
            "speech_events": 0,
            "repetition_events": 0,
            "routine_events": 0,
            "episode_events": 0,
            "high_severity_events": 0,
            "pause_mentions": 0,
            "repetition_mentions": 0,
        }

    text = " ".join(df["observation"].astype(str).tolist())

    return {
        "total_observations": len(df),
        "speech_events": int((df["type"] == "speech").sum()),
        "repetition_events": int((df["type"] == "repetition").sum()),
        "routine_events": int((df["type"] == "routine").sum()),
        "episode_events": int((df["type"] == "episode").sum()),
        "high_severity_events": int((df["severity"] == "high").sum()),
        "pause_mentions": keyword_count(text, ["pause", "pauses", "paused"]),
        "repetition_mentions": keyword_count(text, ["repeated", "same question", "same story", "asked the same"]),
    }


def generate_doctor_summary(df: pd.DataFrame) -> str:
    metrics = analyze_changes(df)

    if df.empty:
        return "No observations available yet."

    first_date = df["date"].min().strftime("%b %d, %Y")
    last_date = df["date"].max().strftime("%b %d, %Y")

    high_events = df[df["severity"] == "high"]
    recent_events = df.tail(5)

    summary = []
    summary.append(f"Observation window: {first_date} to {last_date}.")
    summary.append("")
    summary.append("Important patterns noticed:")
    summary.append(f"- Total caregiver observations logged: {metrics['total_observations']}")
    summary.append(f"- Speech-related observations: {metrics['speech_events']}")
    summary.append(f"- Repetition-related observations: {metrics['repetition_events']}")
    summary.append(f"- Routine disruption observations: {metrics['routine_events']}")
    summary.append(f"- Higher-severity episodes: {metrics['high_severity_events']}")
    summary.append("")

    if metrics["pause_mentions"] > 0:
        summary.append(f"- Speech pauses or word-finding difficulty appeared {metrics['pause_mentions']} time(s).")

    if metrics["repetition_mentions"] > 0:
        summary.append(f"- Repeated questions or repeated stories appeared {metrics['repetition_mentions']} time(s).")

    if not high_events.empty:
        summary.append("")
        summary.append("Higher-severity observations to mention:")
        for _, row in high_events.iterrows():
            date = row["date"].strftime("%b %d")
            summary.append(f"- {date}: {row['observation']}")

    summary.append("")
    summary.append("Recent observations:")
    for _, row in recent_events.iterrows():
        date = row["date"].strftime("%b %d")
        summary.append(f"- {date} ({row['type']}, {row['severity']}): {row['observation']}")

    summary.append("")
    summary.append("Suggested doctor discussion questions:")
    summary.append("- Are these changes consistent with normal aging, medication effects, stress, sleep issues, or something that needs evaluation?")
    summary.append("- Should we track speech, repetition, navigation, medication adherence, or routine disruptions more formally?")
    summary.append("- Are there screening tests or next steps you recommend based on these observations?")
    summary.append("")
    summary.append("Note: This summary is not a diagnosis. It is an organized caregiver observation record.")

    return "\n".join(summary)


def simple_recall(df: pd.DataFrame, question: str) -> pd.DataFrame:
    question_lower = question.lower()

    if any(word in question_lower for word in ["pause", "speech", "word", "speaking"]):
        return df[df["type"].isin(["speech"])]

    if any(word in question_lower for word in ["repeat", "same question", "same story"]):
        return df[df["type"].isin(["repetition"]) | df["observation"].str.lower().str.contains("repeat|same question|same story", na=False)]

    if any(word in question_lower for word in ["routine", "medication", "walk", "kettle"]):
        return df[df["type"].isin(["routine", "episode"])]

    if any(word in question_lower for word in ["bad episode", "episode", "confused", "high"]):
        return df[(df["type"] == "episode") | (df["severity"] == "high")]

    return df.tail(5)


df = load_data()

st.title("NeuroBlackBox")
st.caption("Local memory for cognitive change. Observation support only, not diagnosis.")

st.warning(
    "NeuroBlackBox does not diagnose, treat, or predict Alzheimer’s, dementia, or any medical condition. "
    "It organizes caregiver observations so families can discuss concrete changes with a clinician."
)

left, right = st.columns([1.1, 1.4])

with left:
    st.subheader("Add observation")

    with st.form("add_observation"):
        observation_date = st.date_input("Date", value=datetime.today())
        observation_type = st.selectbox(
            "Type",
            ["speech", "repetition", "routine", "episode", "mood", "sleep", "other"],
        )
        severity = st.selectbox("Severity", ["low", "medium", "high"])
        source = st.text_input("Source", value="caregiver")
        observation = st.text_area(
            "Observation",
            placeholder="Example: Asked the same question three times within one hour.",
            height=120,
        )
        submitted = st.form_submit_button("Save observation")

        if submitted:
            if observation.strip():
                new_row = pd.DataFrame(
                    [
                        {
                            "date": pd.to_datetime(observation_date),
                            "type": observation_type,
                            "severity": severity,
                            "source": source,
                            "observation": observation.strip(),
                        }
                    ]
                )
                updated = pd.concat([df, new_row], ignore_index=True).sort_values("date")
                updated.to_csv(DATA_PATH, index=False)
                st.success("Observation saved. Refreshing memory timeline.")
                st.rerun()
            else:
                st.error("Please enter an observation.")

    st.subheader("Ask NeuroBlackBox")
    question = st.text_input(
        "Question",
        placeholder="What changed over the last 30 days?",
    )

    if question:
        recalled = simple_recall(df, question)
        st.markdown("### Relevant memory cards")
        for _, row in recalled.iterrows():
            st.info(
                f"**{row['date'].strftime('%b %d, %Y')}** — "
                f"{row['type']} / {row['severity']}\n\n{row['observation']}"
            )

with right:
    st.subheader("Cognitive change dashboard")

    metrics = analyze_changes(df)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Observations", metrics["total_observations"])
    col2.metric("Speech events", metrics["speech_events"])
    col3.metric("Repetition events", metrics["repetition_events"])
    col4.metric("High severity", metrics["high_severity_events"])

    st.markdown("### Timeline")
    timeline = df.copy()
    timeline["date"] = timeline["date"].dt.strftime("%b %d, %Y")
    st.dataframe(
        timeline[["date", "type", "severity", "source", "observation"]],
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("### Doctor-prep summary")
    st.code(generate_doctor_summary(df), language="markdown")