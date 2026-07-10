from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any
import html

import pandas as pd
import streamlit as st

from memory_client import (
    sdk_available,
    search_observations,
    store_observation,
)


# =============================================================================
# Application configuration
# =============================================================================

APP_NAME = "NeuroBlackBox"
DATA_PATH = Path("data/sample_observations.csv")

OBSERVATION_COLUMNS = [
    "date",
    "type",
    "severity",
    "source",
    "observation",
]

OBSERVATION_TYPES = [
    "speech",
    "repetition",
    "routine",
    "episode",
    "medication",
    "navigation",
    "mood",
    "sleep",
    "other",
]

SEVERITY_LEVELS = [
    "low",
    "medium",
    "high",
]

st.set_page_config(
    page_title="NeuroBlackBox | Longitudinal Memory for Cognitive Care",
    page_icon="◉",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# =============================================================================
# Utilities
# =============================================================================

def escape(value: Any) -> str:
    return html.escape(str(value))


def render(markup: str) -> None:
    """
    Render custom HTML using Streamlit's native HTML renderer.

    This avoids the Markdown parser incorrectly displaying HTML as code.
    """
    st.html(markup)


def empty_observation_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=OBSERVATION_COLUMNS)


# =============================================================================
# Data access
# =============================================================================

def normalize_observation_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return empty_observation_frame()

    normalized = df.copy()

    for column in OBSERVATION_COLUMNS:
        if column not in normalized.columns:
            normalized[column] = ""

    normalized = normalized[OBSERVATION_COLUMNS]

    normalized["date"] = pd.to_datetime(
        normalized["date"],
        errors="coerce",
    )

    normalized = normalized.dropna(subset=["date"])

    for column in [
        "type",
        "severity",
        "source",
        "observation",
    ]:
        normalized[column] = (
            normalized[column]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    normalized["type"] = normalized["type"].str.lower()
    normalized["severity"] = normalized["severity"].str.lower()

    return normalized.sort_values(
        "date",
        ascending=True,
    ).reset_index(drop=True)


@st.cache_data(show_spinner=False)
def load_data(modified_time: float | None = None) -> pd.DataFrame:
    del modified_time

    if not DATA_PATH.exists():
        return empty_observation_frame()

    try:
        frame = pd.read_csv(DATA_PATH)
    except Exception:
        return empty_observation_frame()

    return normalize_observation_frame(frame)


def get_data() -> pd.DataFrame:
    modified_time = (
        DATA_PATH.stat().st_mtime
        if DATA_PATH.exists()
        else None
    )

    return load_data(modified_time)


def save_data(df: pd.DataFrame) -> None:
    DATA_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    normalized = normalize_observation_frame(df)

    normalized.to_csv(
        DATA_PATH,
        index=False,
        date_format="%Y-%m-%d",
    )

    load_data.clear()


# =============================================================================
# Descriptive analysis
# =============================================================================

def keyword_count(
    text: str,
    keywords: list[str],
) -> int:
    normalized = text.lower()

    return sum(
        normalized.count(keyword.lower())
        for keyword in keywords
    )


def combined_observation_text(df: pd.DataFrame) -> str:
    if df.empty:
        return ""

    return " ".join(
        df["observation"]
        .fillna("")
        .astype(str)
        .tolist()
    )


def analyze_observations(df: pd.DataFrame) -> dict[str, int]:
    if df.empty:
        return {
            "total": 0,
            "speech": 0,
            "repetition": 0,
            "routine": 0,
            "episode": 0,
            "medication": 0,
            "navigation": 0,
            "high": 0,
            "pause_mentions": 0,
            "repetition_mentions": 0,
        }

    text = combined_observation_text(df)

    return {
        "total": int(len(df)),
        "speech": int((df["type"] == "speech").sum()),
        "repetition": int((df["type"] == "repetition").sum()),
        "routine": int((df["type"] == "routine").sum()),
        "episode": int((df["type"] == "episode").sum()),
        "medication": int((df["type"] == "medication").sum()),
        "navigation": int((df["type"] == "navigation").sum()),
        "high": int((df["severity"] == "high").sum()),
        "pause_mentions": keyword_count(
            text,
            [
                "pause",
                "pauses",
                "paused",
                "word-finding",
                "word finding",
            ],
        ),
        "repetition_mentions": keyword_count(
            text,
            [
                "repeat",
                "repeated",
                "same question",
                "same story",
                "asked again",
                "asked the same",
            ],
        ),
    }


def latest_high_severity_episode(
    df: pd.DataFrame,
) -> pd.Series | None:
    if df.empty:
        return None

    candidates = df[
        (df["type"] == "episode")
        & (df["severity"] == "high")
    ]

    if candidates.empty:
        return None

    return candidates.sort_values("date").iloc[-1]


def before_episode_window(
    df: pd.DataFrame,
    days_before: int = 10,
) -> tuple[pd.Series | None, pd.DataFrame]:
    episode = latest_high_severity_episode(df)

    if episode is None:
        return None, empty_observation_frame()

    episode_date = pd.Timestamp(episode["date"])
    start_date = episode_date - timedelta(days=days_before)

    window = df[
        (df["date"] >= start_date)
        & (df["date"] < episode_date)
    ].copy()

    return episode, window.sort_values("date")


def thirty_day_window(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()

    end_date = df["date"].max()
    start_date = end_date - timedelta(days=30)

    return df[
        (df["date"] >= start_date)
        & (df["date"] <= end_date)
    ].copy()


def format_observation(row: pd.Series) -> str:
    observation_date = pd.Timestamp(row["date"]).strftime(
        "%b %d, %Y"
    )

    return (
        f"{observation_date} | "
        f"{row['type']} | "
        f"{row['severity']} | "
        f"{row['observation']}"
    )


# =============================================================================
# Generated outputs
# =============================================================================

def generate_before_episode_analysis(
    df: pd.DataFrame,
    days_before: int = 10,
) -> str:
    episode, window = before_episode_window(
        df,
        days_before=days_before,
    )

    if episode is None:
        return (
            "BEFORE-EPISODE RECONSTRUCTION\n\n"
            "No high-severity episode is currently available.\n\n"
            "A reconstruction requires an observation categorized as "
            "'episode' with severity set to 'high'."
        )

    episode_date = pd.Timestamp(episode["date"])
    start_date = episode_date - timedelta(days=days_before)

    lines = [
        "BEFORE-EPISODE RECONSTRUCTION",
        "",
        f"Index episode: {episode_date.strftime('%b %d, %Y')}",
        f"Episode record: {episode['observation']}",
        "",
        (
            "Review interval: "
            f"{start_date.strftime('%b %d, %Y')} to "
            f"{episode_date.strftime('%b %d, %Y')}"
        ),
        "",
    ]

    if window.empty:
        lines.extend(
            [
                "No observations were recorded during this interval.",
                "",
                (
                    "Important limitation: absence of recorded observations "
                    "does not establish absence of preceding changes."
                ),
            ]
        )

        return "\n".join(lines)

    metrics = analyze_observations(window)

    lines.extend(
        [
            "Descriptive signals recorded during the interval:",
            f"- Speech observations: {metrics['speech']}",
            f"- Repetition observations: {metrics['repetition']}",
            f"- Routine observations: {metrics['routine']}",
            f"- Medication observations: {metrics['medication']}",
            f"- Navigation observations: {metrics['navigation']}",
            f"- Pause or word-finding mentions: {metrics['pause_mentions']}",
            f"- Repetition-related mentions: {metrics['repetition_mentions']}",
            "",
            "Source observations:",
        ]
    )

    for _, row in window.iterrows():
        lines.append(f"- {format_observation(row)}")

    lines.extend(
        [
            "",
            "Review boundary:",
            (
                "This reconstruction organizes caregiver-entered observations. "
                "It does not establish causation, diagnosis, disease progression, "
                "or predictive risk."
            ),
        ]
    )

    return "\n".join(lines)


def generate_thirty_day_brief(df: pd.DataFrame) -> str:
    recent = thirty_day_window(df)

    if recent.empty:
        return "No observations are available for the current review period."

    metrics = analyze_observations(recent)

    first_date = recent["date"].min().strftime("%b %d, %Y")
    last_date = recent["date"].max().strftime("%b %d, %Y")

    lines = [
        "THIRTY-DAY OBSERVATION BRIEF",
        "",
        f"Review period: {first_date} to {last_date}",
        "",
        "Observation-log composition:",
        f"- Total observations: {metrics['total']}",
        f"- Speech observations: {metrics['speech']}",
        f"- Repetition observations: {metrics['repetition']}",
        f"- Routine observations: {metrics['routine']}",
        f"- Medication observations: {metrics['medication']}",
        f"- Navigation observations: {metrics['navigation']}",
        f"- High-severity observations: {metrics['high']}",
        f"- Pause or word-finding mentions: {metrics['pause_mentions']}",
        f"- Repetition-related mentions: {metrics['repetition_mentions']}",
        "",
        "Interpretation boundary:",
        (
            "These values summarize the observation log. They are not clinical "
            "scores and do not measure cognitive function or disease progression."
        ),
    ]

    return "\n".join(lines)


def generate_clinician_preparation_summary(
    df: pd.DataFrame,
) -> str:
    if df.empty:
        return "No observations are available."

    metrics = analyze_observations(df)

    first_date = df["date"].min().strftime("%b %d, %Y")
    last_date = df["date"].max().strftime("%b %d, %Y")

    high_severity = df[
        df["severity"] == "high"
    ].sort_values("date")

    recent = df.sort_values("date").tail(6)

    lines = [
        "CAREGIVER-CLINICIAN PREPARATION SUMMARY",
        "",
        f"Observation period: {first_date} to {last_date}",
        "",
        "Recorded observation categories:",
        f"- Total records: {metrics['total']}",
        f"- Speech: {metrics['speech']}",
        f"- Repetition: {metrics['repetition']}",
        f"- Routine: {metrics['routine']}",
        f"- Medication: {metrics['medication']}",
        f"- Navigation: {metrics['navigation']}",
        f"- High-severity records: {metrics['high']}",
    ]

    if not high_severity.empty:
        lines.extend(
            [
                "",
                "High-severity source records:",
            ]
        )

        for _, row in high_severity.iterrows():
            lines.append(f"- {format_observation(row)}")

    lines.extend(
        [
            "",
            "Most recent source records:",
        ]
    )

    for _, row in recent.iterrows():
        lines.append(f"- {format_observation(row)}")

    lines.extend(
        [
            "",
            "Potential questions for clinical discussion:",
            (
                "- Which symptoms, routines, medication effects, sleep changes, "
                "or environmental factors should be monitored more systematically?"
            ),
            (
                "- Are the recorded changes sufficiently concerning to justify "
                "formal assessment or additional investigation?"
            ),
            (
                "- Which recommendations from this visit should the family record "
                "and review before the next appointment?"
            ),
            "",
            "Safety boundary:",
            (
                "This document organizes caregiver-reported observations. "
                "It is not a diagnosis, screening result, prediction, "
                "medical record replacement, or treatment recommendation."
            ),
        ]
    )

    return "\n".join(lines)


# =============================================================================
# Retrieval
# =============================================================================

def deterministic_recall(
    df: pd.DataFrame,
    question: str,
) -> pd.DataFrame:
    if df.empty:
        return df.copy()

    query = question.lower().strip()

    if any(
        phrase in query
        for phrase in [
            "before episode",
            "before the episode",
            "before latest episode",
            "before the latest episode",
            "before last bad episode",
        ]
    ):
        _, window = before_episode_window(df)

        return window

    if any(
        phrase in query
        for phrase in [
            "speech",
            "pause",
            "word finding",
            "word-finding",
            "speaking",
        ]
    ):
        return df[
            (df["type"] == "speech")
            | df["observation"].str.contains(
                "pause|word.finding|speech",
                case=False,
                regex=True,
                na=False,
            )
        ]

    if any(
        phrase in query
        for phrase in [
            "repeat",
            "repetition",
            "same question",
            "same story",
        ]
    ):
        return df[
            (df["type"] == "repetition")
            | df["observation"].str.contains(
                "repeat|same question|same story",
                case=False,
                regex=True,
                na=False,
            )
        ]

    if any(
        phrase in query
        for phrase in [
            "medication",
            "medicine",
            "dose",
            "prescription",
        ]
    ):
        return df[
            (df["type"] == "medication")
            | df["observation"].str.contains(
                "medication|medicine|dose|prescription",
                case=False,
                regex=True,
                na=False,
            )
        ]

    if any(
        phrase in query
        for phrase in [
            "navigation",
            "lost",
            "walk",
            "direction",
        ]
    ):
        return df[
            df["type"].isin(
                [
                    "navigation",
                    "episode",
                ]
            )
        ]

    if any(
        phrase in query
        for phrase in [
            "routine",
            "daily activity",
            "appointment",
        ]
    ):
        return df[
            df["type"].isin(
                [
                    "routine",
                    "medication",
                    "navigation",
                ]
            )
        ]

    if any(
        phrase in query
        for phrase in [
            "high severity",
            "episode",
            "confusion",
        ]
    ):
        return df[
            (df["severity"] == "high")
            | (df["type"] == "episode")
        ]

    return df.sort_values("date").tail(6)


def extract_result_content(result: Any) -> str:
    if isinstance(result, dict):
        direct_content = result.get("content")

        if direct_content:
            return str(direct_content)

        chunks = result.get("chunks") or []

        if chunks:
            first_chunk = chunks[0]

            if isinstance(first_chunk, dict):
                return str(
                    first_chunk.get(
                        "content",
                        first_chunk,
                    )
                )

            return str(
                getattr(
                    first_chunk,
                    "content",
                    first_chunk,
                )
            )

        return str(result)

    chunks = getattr(
        result,
        "chunks",
        None,
    )

    if chunks:
        first_chunk = chunks[0]

        return str(
            getattr(
                first_chunk,
                "content",
                first_chunk,
            )
        )

    for attribute in [
        "content",
        "text",
        "document",
    ]:
        value = getattr(
            result,
            attribute,
            None,
        )

        if value:
            return str(value)

    return str(result)


def extract_result_score(result: Any) -> str:
    raw_score = (
        result.get("score")
        if isinstance(result, dict)
        else getattr(result, "score", None)
    )

    if raw_score is None:
        return "not reported"

    try:
        return f"{float(raw_score):.2f}"
    except (TypeError, ValueError):
        return str(raw_score)


def clean_memory_content(content: str) -> str:
    cleaned = content

    for prefix in [
        "NeuroBlackBox caregiver observation. ",
        "Patient: Eleanor. ",
    ]:
        cleaned = cleaned.replace(prefix, "")

    return cleaned.strip()


def display_memory_results(results: list[Any]) -> bool:
    if not results:
        return False

    render(
        """
        <div class="nbb-result-heading">
            Retrieved longitudinal records
        </div>
        """
    )

    for result in results:
        content = clean_memory_content(
            extract_result_content(result)
        )

        score = extract_result_score(result)

        render(
            f"""
            <article class="nbb-memory-result">
                <div class="nbb-memory-result__meta">
                    Supermemory Local · semantic relevance {escape(score)}
                </div>
                <div class="nbb-memory-result__content">
                    {escape(content)}
                </div>
            </article>
            """
        )

    return True


# =============================================================================
# Session state
# =============================================================================

def initialize_session_state() -> None:
    defaults = {
        "query": "",
        "last_save_message": "",
        "last_save_success": None,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def set_query(value: str) -> None:
    st.session_state["query"] = value


initialize_session_state()


# =============================================================================
# Current application state
# =============================================================================

df = get_data()
metrics = analyze_observations(df)

supermemory_available = sdk_available()

before_episode_analysis = generate_before_episode_analysis(df)
thirty_day_brief = generate_thirty_day_brief(df)
clinician_summary = generate_clinician_preparation_summary(df)


# =============================================================================
# Global styling
# =============================================================================

render(
    """
    <style>
        :root {
            color-scheme: light;

            --ink: #10141a;
            --ink-soft: #313842;
            --muted: #68717d;
            --muted-light: #9098a3;

            --paper: #ffffff;
            --paper-soft: #f6f7f9;
            --paper-blue: #f2f6fa;
            --paper-dark: #10151c;

            --line: #dfe3e8;
            --line-dark: #2a323d;

            --blue: #375e7e;
            --blue-dark: #1d3a52;
            --blue-soft: #dce9f2;

            --green: #2c6a4e;
            --green-soft: #e9f4ee;

            --orange: #9c6525;
            --orange-soft: #f7efe4;

            --max-width: 1420px;
            --reading-width: 760px;
        }

        html,
        body,
        .stApp,
        [data-testid="stAppViewContainer"],
        [data-testid="stMain"] {
            background: var(--paper) !important;
            color: var(--ink) !important;
        }

        html,
        body,
        button,
        input,
        textarea,
        select {
            font-family:
                -apple-system,
                BlinkMacSystemFont,
                "Segoe UI",
                Helvetica,
                Arial,
                sans-serif !important;
        }

        [data-testid="stHeader"] {
            background: rgba(255, 255, 255, 0.96) !important;
            border-bottom: 1px solid var(--line) !important;
        }

        .block-container {
            width: 100% !important;
            max-width: var(--max-width) !important;
            padding-top: 1rem !important;
            padding-right: 3rem !important;
            padding-bottom: 7rem !important;
            padding-left: 3rem !important;
        }

        h1,
        h2,
        h3,
        h4,
        h5,
        p {
            color: var(--ink);
        }

        h1,
        h2,
        h3,
        h4,
        h5 {
            letter-spacing: -0.035em;
        }

        h2 {
            font-size: 2.15rem !important;
            font-weight: 660 !important;
        }

        h3 {
            font-size: 1.35rem !important;
            font-weight: 650 !important;
        }

        hr {
            border: 0 !important;
            border-top: 1px solid var(--line) !important;
            margin: 5rem 0 !important;
        }

        .nbb-nav {
            display: grid;
            grid-template-columns: 1fr auto;
            align-items: center;
            min-height: 72px;
            border-bottom: 1px solid var(--line);
        }

        .nbb-nav__brand {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            font-weight: 720;
            font-size: 0.95rem;
            letter-spacing: -0.02em;
        }

        .nbb-nav__symbol {
            position: relative;
            width: 24px;
            height: 24px;
            border: 1.5px solid var(--ink);
            border-radius: 50%;
        }

        .nbb-nav__symbol::before,
        .nbb-nav__symbol::after {
            content: "";
            position: absolute;
            border-radius: 50%;
        }

        .nbb-nav__symbol::before {
            width: 8px;
            height: 8px;
            left: 6.5px;
            top: 6.5px;
            background: var(--blue);
        }

        .nbb-nav__symbol::after {
            width: 3px;
            height: 3px;
            left: 16px;
            top: 3px;
            background: var(--green);
        }

        .nbb-nav__links {
            display: flex;
            gap: 1.6rem;
            color: var(--muted);
            font-size: 0.84rem;
        }

        .nbb-hero {
            display: grid;
            grid-template-columns:
                minmax(0, 1.35fr)
                minmax(380px, 0.65fr);
            gap: 5rem;
            align-items: center;
            min-height: 700px;
            padding: 5.5rem 0;
        }

        .nbb-eyebrow {
            margin-bottom: 1.5rem;
            color: var(--blue);
            font-size: 0.72rem;
            font-weight: 760;
            letter-spacing: 0.13em;
            text-transform: uppercase;
        }

        .nbb-hero__title {
            max-width: 920px;
            margin: 0;
            color: var(--ink);
            font-size: clamp(4.25rem, 7vw, 7.8rem);
            font-weight: 690;
            line-height: 0.94;
            letter-spacing: -0.072em;
        }

        .nbb-hero__title span {
            color: var(--blue);
        }

        .nbb-hero__summary {
            max-width: 790px;
            margin: 2.2rem 0 0 0;
            color: var(--ink-soft);
            font-size: 1.25rem;
            line-height: 1.65;
        }

        .nbb-hero__support {
            max-width: 760px;
            margin: 1.2rem 0 0 0;
            color: var(--muted);
            font-size: 0.97rem;
            line-height: 1.72;
        }

        .nbb-hero__tags {
            display: flex;
            flex-wrap: wrap;
            gap: 0.75rem 1.2rem;
            margin-top: 2rem;
            color: var(--ink-soft);
            font-size: 0.86rem;
        }

        .nbb-hero__tags span::before {
            content: "—";
            margin-right: 0.45rem;
            color: var(--muted-light);
        }

        .nbb-system-panel {
            position: relative;
            min-height: 510px;
            padding: 2rem;
            overflow: hidden;
            border-radius: 24px;
            background: var(--paper-dark);
            color: #ffffff;
        }

        .nbb-system-panel::before {
            content: "";
            position: absolute;
            width: 440px;
            height: 440px;
            left: 50%;
            top: 50%;
            transform: translate(-50%, -50%);
            border: 1px solid rgba(126, 170, 201, 0.24);
            border-radius: 50%;
        }

        .nbb-system-panel::after {
            content: "";
            position: absolute;
            width: 310px;
            height: 310px;
            left: 50%;
            top: 50%;
            transform: translate(-50%, -50%);
            border: 1px solid rgba(126, 170, 201, 0.16);
            border-radius: 50%;
        }

        .nbb-system-panel__header {
            position: relative;
            z-index: 2;
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding-bottom: 1rem;
            border-bottom: 1px solid var(--line-dark);
        }

        .nbb-system-panel__label {
            color: #bac5cf;
            font-size: 0.7rem;
            font-weight: 700;
            letter-spacing: 0.1em;
            text-transform: uppercase;
        }

        .nbb-status {
            display: flex;
            align-items: center;
            gap: 0.45rem;
            color: #dce6df;
            font-size: 0.76rem;
        }

        .nbb-status__dot {
            width: 7px;
            height: 7px;
            border-radius: 50%;
            background: #4fc084;
            box-shadow: 0 0 0 5px rgba(79, 192, 132, 0.09);
        }

        .nbb-memory-core {
            position: absolute;
            z-index: 3;
            left: 50%;
            top: 48%;
            width: 150px;
            height: 150px;
            transform: translate(-50%, -50%);
            border: 1px solid rgba(170, 204, 228, 0.65);
            border-radius: 50%;
            background:
                radial-gradient(
                    circle at 42% 35%,
                    rgba(118, 170, 207, 0.45),
                    rgba(36, 69, 94, 0.55) 45%,
                    rgba(16, 21, 28, 0.95) 76%
                );
            box-shadow:
                0 0 70px rgba(72, 130, 169, 0.32),
                inset 0 0 40px rgba(144, 188, 217, 0.14);
        }

        .nbb-memory-core::before {
            content: "LONGITUDINAL\\A MEMORY";
            white-space: pre;
            position: absolute;
            left: 50%;
            top: 50%;
            transform: translate(-50%, -50%);
            color: #e9f1f6;
            font-size: 0.65rem;
            font-weight: 720;
            line-height: 1.45;
            letter-spacing: 0.09em;
            text-align: center;
        }

        .nbb-orbit-label {
            position: absolute;
            z-index: 4;
            padding: 0.45rem 0.65rem;
            border: 1px solid rgba(177, 197, 211, 0.22);
            border-radius: 4px;
            background: rgba(15, 22, 30, 0.86);
            color: #cbd5dd;
            font-family:
                "SFMono-Regular",
                Consolas,
                monospace;
            font-size: 0.62rem;
            letter-spacing: 0.04em;
        }

        .nbb-orbit-label--speech {
            left: 7%;
            top: 31%;
        }

        .nbb-orbit-label--routine {
            right: 5%;
            top: 29%;
        }

        .nbb-orbit-label--episode {
            right: 7%;
            bottom: 24%;
        }

        .nbb-orbit-label--medication {
            left: 6%;
            bottom: 23%;
        }

        .nbb-orbit-label--visit {
            left: 50%;
            bottom: 8%;
            transform: translateX(-50%);
        }

        .nbb-system-panel__footer {
            position: absolute;
            z-index: 4;
            left: 2rem;
            right: 2rem;
            bottom: 1.6rem;
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 0.8rem;
        }

        .nbb-system-stat {
            padding-top: 0.75rem;
            border-top: 1px solid var(--line-dark);
        }

        .nbb-system-stat__label {
            color: #7f8d99;
            font-size: 0.62rem;
            letter-spacing: 0.04em;
            text-transform: uppercase;
        }

        .nbb-system-stat__value {
            margin-top: 0.25rem;
            color: #edf3f7;
            font-size: 1.2rem;
            font-weight: 650;
        }

        .nbb-scope {
            display: grid;
            grid-template-columns: 180px 1fr;
            gap: 2rem;
            padding: 1.45rem 0;
            border-top: 1px solid var(--line);
            border-bottom: 1px solid var(--line);
        }

        .nbb-scope__label {
            color: var(--ink);
            font-size: 0.72rem;
            font-weight: 760;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }

        .nbb-scope__text {
            max-width: 900px;
            color: var(--muted);
            font-size: 0.94rem;
            line-height: 1.65;
        }

        .nbb-section {
            padding: 1rem 0;
        }

        .nbb-section-header {
            display: grid;
            grid-template-columns: 180px minmax(0, 1fr);
            gap: 2rem;
            margin-bottom: 3rem;
        }

        .nbb-section-header__index {
            padding-top: 0.55rem;
            color: var(--muted);
            font-family:
                "SFMono-Regular",
                Consolas,
                monospace;
            font-size: 0.72rem;
            letter-spacing: 0.05em;
        }

        .nbb-section-header__title {
            max-width: 980px;
            margin: 0;
            color: var(--ink);
            font-size: clamp(2.45rem, 4vw, 4.4rem);
            font-weight: 660;
            line-height: 1.05;
            letter-spacing: -0.055em;
        }

        .nbb-section-header__description {
            max-width: 820px;
            margin: 1.3rem 0 0 0;
            color: var(--muted);
            font-size: 1.03rem;
            line-height: 1.72;
        }

        .nbb-gap-diagram {
            display: grid;
            grid-template-columns:
                minmax(0, 1fr)
                90px
                minmax(0, 1fr)
                90px
                minmax(0, 1fr);
            align-items: stretch;
            border-top: 1px solid var(--line);
            border-bottom: 1px solid var(--line);
        }

        .nbb-gap-stage {
            min-height: 270px;
            padding: 2rem 1.6rem 2.2rem 0;
        }

        .nbb-gap-stage__number {
            margin-bottom: 2rem;
            color: var(--muted-light);
            font-family:
                "SFMono-Regular",
                Consolas,
                monospace;
            font-size: 0.68rem;
        }

        .nbb-gap-stage__title {
            margin-bottom: 0.8rem;
            color: var(--ink);
            font-size: 1.22rem;
            font-weight: 670;
        }

        .nbb-gap-stage__text {
            color: var(--muted);
            font-size: 0.9rem;
            line-height: 1.65;
        }

        .nbb-gap-arrow {
            display: flex;
            align-items: center;
            justify-content: center;
            border-left: 1px solid var(--line);
            border-right: 1px solid var(--line);
            color: var(--blue);
            font-size: 1.5rem;
        }

        .nbb-bridge {
            padding: 2.5rem;
            border-radius: 18px;
            background: var(--paper-blue);
        }

        .nbb-bridge__label {
            margin-bottom: 0.9rem;
            color: var(--blue);
            font-size: 0.7rem;
            font-weight: 760;
            letter-spacing: 0.1em;
            text-transform: uppercase;
        }

        .nbb-bridge__title {
            margin: 0;
            color: var(--blue-dark);
            font-size: 1.55rem;
            font-weight: 670;
        }

        .nbb-bridge__text {
            margin-top: 0.8rem;
            color: #475766;
            font-size: 0.94rem;
            line-height: 1.68;
        }

        .nbb-capabilities {
            border-top: 1px solid var(--line);
        }

        .nbb-capability {
            display: grid;
            grid-template-columns: 120px 0.8fr 1.2fr;
            gap: 2.5rem;
            padding: 2.2rem 0;
            border-bottom: 1px solid var(--line);
        }

        .nbb-capability__index {
            color: var(--muted-light);
            font-family:
                "SFMono-Regular",
                Consolas,
                monospace;
            font-size: 0.7rem;
        }

        .nbb-capability__title {
            color: var(--ink);
            font-size: 1.35rem;
            font-weight: 670;
        }

        .nbb-capability__description {
            max-width: 740px;
            color: var(--muted);
            font-size: 0.94rem;
            line-height: 1.7;
        }

        .nbb-audience-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1px;
            overflow: hidden;
            border: 1px solid var(--line);
            border-radius: 18px;
            background: var(--line);
        }

        .nbb-audience {
            min-height: 480px;
            padding: 2.6rem;
            background: var(--paper);
        }

        .nbb-audience--clinical {
            background: var(--paper-soft);
        }

        .nbb-audience__label {
            margin-bottom: 1rem;
            color: var(--blue);
            font-size: 0.7rem;
            font-weight: 760;
            letter-spacing: 0.1em;
            text-transform: uppercase;
        }

        .nbb-audience__title {
            margin: 0 0 1.4rem 0;
            color: var(--ink);
            font-size: 2rem;
            font-weight: 660;
        }

        .nbb-audience ul {
            margin: 0;
            padding: 0;
            list-style: none;
        }

        .nbb-audience li {
            position: relative;
            padding: 1rem 0 1rem 1.8rem;
            border-top: 1px solid var(--line);
            color: var(--ink-soft);
            font-size: 0.94rem;
            line-height: 1.55;
        }

        .nbb-audience li::before {
            content: "";
            position: absolute;
            left: 0;
            top: 1.35rem;
            width: 7px;
            height: 7px;
            border-radius: 50%;
            background: var(--blue);
        }

        .nbb-metric-strip {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            margin-bottom: 3rem;
            border-top: 1px solid var(--line);
            border-bottom: 1px solid var(--line);
        }

        .nbb-metric {
            padding: 1.5rem 1.6rem 1.6rem 0;
        }

        .nbb-metric + .nbb-metric {
            padding-left: 1.6rem;
            border-left: 1px solid var(--line);
        }

        .nbb-metric__label {
            color: var(--muted);
            font-size: 0.75rem;
        }

        .nbb-metric__value {
            margin-top: 0.45rem;
            color: var(--ink);
            font-size: 2.4rem;
            font-weight: 670;
            letter-spacing: -0.045em;
        }

        .nbb-console-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 1rem;
            padding: 1rem 1.2rem;
            border-radius: 8px 8px 0 0;
            background: var(--paper-dark);
            color: #ffffff;
        }

        .nbb-console-header__title {
            color: #ffffff;
            font-size: 0.79rem;
            font-weight: 680;
            letter-spacing: 0.07em;
            text-transform: uppercase;
        }

        .nbb-console-header__status {
            color: #aeb9c3;
            font-size: 0.72rem;
        }

        .nbb-result-heading {
            margin: 1.4rem 0 0.7rem 0;
            color: var(--ink);
            font-size: 0.82rem;
            font-weight: 680;
        }

        .nbb-memory-result {
            margin-bottom: 0.75rem;
            padding: 1rem;
            border: 1px solid var(--line);
            border-radius: 7px;
            background: var(--paper);
        }

        .nbb-memory-result__meta {
            margin-bottom: 0.45rem;
            color: var(--blue);
            font-size: 0.7rem;
            font-weight: 690;
        }

        .nbb-memory-result__content {
            color: var(--ink-soft);
            font-size: 0.9rem;
            line-height: 1.62;
        }

        .nbb-document {
            height: 100%;
            padding: 1.4rem;
            border: 1px solid var(--line);
            border-radius: 10px;
            background: var(--paper-soft);
        }

        .nbb-document__label {
            margin-bottom: 1rem;
            color: var(--muted);
            font-size: 0.7rem;
            font-weight: 720;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }

        .nbb-document pre {
            margin: 0;
            overflow-x: auto;
            white-space: pre-wrap;
            overflow-wrap: anywhere;
            color: #252c34;
            font-family:
                "SFMono-Regular",
                Consolas,
                monospace;
            font-size: 0.77rem;
            line-height: 1.65;
        }

        .nbb-limitations {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 2rem;
        }

        .nbb-limitation {
            padding-top: 1rem;
            border-top: 1px solid var(--line);
        }

        .nbb-limitation__title {
            margin-bottom: 0.65rem;
            color: var(--ink);
            font-size: 0.92rem;
            font-weight: 680;
        }

        .nbb-limitation__text {
            color: var(--muted);
            font-size: 0.86rem;
            line-height: 1.65;
        }

        .nbb-footer {
            display: grid;
            grid-template-columns: 1fr auto;
            gap: 2rem;
            padding: 2rem 0 0 0;
            border-top: 1px solid var(--line);
            color: var(--muted);
            font-size: 0.8rem;
            line-height: 1.65;
        }

        [data-testid="stForm"] {
            padding: 1.25rem !important;
            border: 1px solid var(--line) !important;
            border-radius: 8px !important;
            background: var(--paper-soft) !important;
        }

        [data-baseweb="input"],
        [data-baseweb="textarea"],
        [data-baseweb="select"] > div {
            background: #ffffff !important;
            border-color: #cfd5dc !important;
            border-radius: 6px !important;
            color: var(--ink) !important;
            box-shadow: none !important;
        }

        [data-baseweb="input"] input,
        [data-baseweb="textarea"] textarea {
            color: var(--ink) !important;
            background: #ffffff !important;
        }

        [data-baseweb="select"] * {
            color: var(--ink) !important;
        }

        .stButton > button,
        .stDownloadButton > button,
        [data-testid="stFormSubmitButton"] > button {
            min-height: 2.7rem !important;
            border: 1px solid #cbd2d9 !important;
            border-radius: 6px !important;
            background: #ffffff !important;
            color: var(--ink) !important;
            font-weight: 620 !important;
            box-shadow: none !important;
        }

        .stButton > button:hover,
        .stDownloadButton > button:hover,
        [data-testid="stFormSubmitButton"] > button:hover {
            border-color: var(--ink) !important;
            background: var(--paper-soft) !important;
        }

        [data-testid="stDataFrame"] {
            border: 1px solid var(--line) !important;
            border-radius: 8px !important;
            overflow: hidden;
        }

        [data-testid="stAlert"] {
            border-radius: 7px !important;
            box-shadow: none !important;
        }

        @media (max-width: 1050px) {
            .nbb-hero {
                grid-template-columns: 1fr;
                gap: 3rem;
            }

            .nbb-system-panel {
                min-height: 480px;
            }

            .nbb-gap-diagram {
                grid-template-columns: 1fr;
            }

            .nbb-gap-arrow {
                min-height: 60px;
                border: 0;
                border-top: 1px solid var(--line);
                border-bottom: 1px solid var(--line);
                transform: rotate(90deg);
            }

            .nbb-capability {
                grid-template-columns: 80px 1fr;
            }

            .nbb-capability__description {
                grid-column: 2;
            }

            .nbb-audience-grid {
                grid-template-columns: 1fr;
            }

            .nbb-metric-strip {
                grid-template-columns: repeat(2, 1fr);
            }

            .nbb-limitations {
                grid-template-columns: 1fr;
            }
        }

        @media (max-width: 700px) {
            .block-container {
                padding-right: 1.2rem !important;
                padding-left: 1.2rem !important;
            }

            .nbb-nav__links {
                display: none;
            }

            .nbb-hero {
                min-height: auto;
                padding: 3.5rem 0;
            }

            .nbb-hero__title {
                font-size: 3.7rem;
            }

            .nbb-section-header {
                grid-template-columns: 1fr;
                gap: 0.5rem;
            }

            .nbb-capability {
                grid-template-columns: 1fr;
                gap: 0.6rem;
            }

            .nbb-capability__description {
                grid-column: auto;
            }

            .nbb-metric-strip {
                grid-template-columns: 1fr;
            }

            .nbb-metric + .nbb-metric {
                padding-left: 0;
                border-left: 0;
                border-top: 1px solid var(--line);
            }

            .nbb-scope {
                grid-template-columns: 1fr;
                gap: 0.6rem;
            }

            .nbb-footer {
                grid-template-columns: 1fr;
            }
        }
    </style>
    """
)


# =============================================================================
# Navigation
# =============================================================================

render(
    """
    <nav class="nbb-nav">
        <div class="nbb-nav__brand">
            <div class="nbb-nav__symbol"></div>
            <span>NeuroBlackBox</span>
        </div>

        <div class="nbb-nav__links">
            <span>Problem</span>
            <span>Memory layer</span>
            <span>Prototype</span>
            <span>Research boundary</span>
        </div>
    </nav>
    """
)


# =============================================================================
# Hero
# =============================================================================

memory_status = (
    "Online"
    if supermemory_available
    else "Fallback"
)

render(
    f"""
    <header class="nbb-hero">
        <div>
            <div class="nbb-eyebrow">
                Longitudinal memory infrastructure for cognitive care
            </div>

            <h1 class="nbb-hero__title">
                Care does not end when the <span>appointment does.</span>
            </h1>

            <p class="nbb-hero__summary">
                NeuroBlackBox preserves symptoms, routines, caregiver observations,
                interventions, improvements, and clinical discussions across time,
                so families and clinicians do not have to reconstruct cognitive
                change from memory alone.
            </p>

            <p class="nbb-hero__support">
                The system is designed for continuity between daily life and
                clinical review, including communities where specialist access,
                reliable documentation, or consistent follow-up may be limited.
            </p>

            <div class="nbb-hero__tags">
                <span>Local-first</span>
                <span>Source-grounded</span>
                <span>Longitudinal</span>
                <span>Clinician preparation</span>
            </div>
        </div>

        <aside class="nbb-system-panel">
            <div class="nbb-system-panel__header">
                <div class="nbb-system-panel__label">
                    Live memory architecture
                </div>

                <div class="nbb-status">
                    <div class="nbb-status__dot"></div>
                    <span>Supermemory {escape(memory_status)}</span>
                </div>
            </div>

            <div class="nbb-memory-core"></div>

            <div class="nbb-orbit-label nbb-orbit-label--speech">
                SPEECH
            </div>

            <div class="nbb-orbit-label nbb-orbit-label--routine">
                ROUTINE
            </div>

            <div class="nbb-orbit-label nbb-orbit-label--episode">
                EPISODE
            </div>

            <div class="nbb-orbit-label nbb-orbit-label--medication">
                MEDICATION
            </div>

            <div class="nbb-orbit-label nbb-orbit-label--visit">
                CLINICAL VISIT
            </div>

            <div class="nbb-system-panel__footer">
                <div class="nbb-system-stat">
                    <div class="nbb-system-stat__label">
                        Records
                    </div>
                    <div class="nbb-system-stat__value">
                        {metrics["total"]}
                    </div>
                </div>

                <div class="nbb-system-stat">
                    <div class="nbb-system-stat__label">
                        High severity
                    </div>
                    <div class="nbb-system-stat__value">
                        {metrics["high"]}
                    </div>
                </div>

                <div class="nbb-system-stat">
                    <div class="nbb-system-stat__label">
                        Storage
                    </div>
                    <div class="nbb-system-stat__value">
                        Local
                    </div>
                </div>
            </div>
        </aside>
    </header>
    """
)

render(
    """
    <div class="nbb-scope">
        <div class="nbb-scope__label">
            Clinical boundary
        </div>

        <div class="nbb-scope__text">
            NeuroBlackBox preserves and organizes caregiver-reported observations.
            It does not diagnose, screen, predict, or treat Alzheimer's disease,
            dementia, or any other medical condition. It does not replace a
            clinician or an official medical record.
        </div>
    </div>
    """
)

st.divider()


# =============================================================================
# Problem
# =============================================================================

render(
    """
    <section class="nbb-section">
        <div class="nbb-section-header">
            <div class="nbb-section-header__index">
                01 / CONTINUITY GAP
            </div>

            <div>
                <h2 class="nbb-section-header__title">
                    Critical context disappears between daily life and clinical care.
                </h2>

                <p class="nbb-section-header__description">
                    Patients and families may not remember every symptom, improvement,
                    recommendation, or contextual change from one appointment to the
                    next. Clinicians then have to reconstruct a longitudinal history
                    from fragmented recollection.
                </p>
            </div>
        </div>

        <div class="nbb-gap-diagram">
            <article class="nbb-gap-stage">
                <div class="nbb-gap-stage__number">01</div>
                <div class="nbb-gap-stage__title">Daily life</div>
                <div class="nbb-gap-stage__text">
                    Speech pauses, repeated questions, medication changes,
                    disrupted routines, navigation issues, and improvements
                    occur outside the clinic.
                </div>
            </article>

            <div class="nbb-gap-arrow">→</div>

            <article class="nbb-gap-stage">
                <div class="nbb-gap-stage__number">02</div>
                <div class="nbb-gap-stage__title">Clinical visit</div>
                <div class="nbb-gap-stage__text">
                    A short appointment compresses weeks or months of lived
                    experience into a retrospective conversation.
                </div>
            </article>

            <div class="nbb-gap-arrow">→</div>

            <article class="nbb-gap-stage">
                <div class="nbb-gap-stage__number">03</div>
                <div class="nbb-gap-stage__title">Follow-up</div>
                <div class="nbb-gap-stage__text">
                    Families may forget recommendations, struggle to evaluate
                    progress, or return without a structured interval history.
                </div>
            </article>
        </div>

        <div style="height: 1.5rem;"></div>

        <div class="nbb-bridge">
            <div class="nbb-bridge__label">
                NeuroBlackBox memory layer
            </div>

            <h3 class="nbb-bridge__title">
                A persistent record across the complete care interval.
            </h3>

            <p class="nbb-bridge__text">
                The system connects caregiver observations, previous visit context,
                intervention history, symptom evolution, and clinician-preparation
                outputs through a searchable local memory layer.
            </p>
        </div>
    </section>
    """
)

st.divider()


# =============================================================================
# Product system
# =============================================================================

render(
    """
    <section class="nbb-section">
        <div class="nbb-section-header">
            <div class="nbb-section-header__index">
                02 / MEMORY SYSTEM
            </div>

            <div>
                <h2 class="nbb-section-header__title">
                    From isolated observations to a longitudinal care record.
                </h2>

                <p class="nbb-section-header__description">
                    NeuroBlackBox is organized around five operations: capture,
                    remember, connect, retrieve, and prepare.
                </p>
            </div>
        </div>

        <div class="nbb-capabilities">
            <article class="nbb-capability">
                <div class="nbb-capability__index">01 / CAPTURE</div>
                <div class="nbb-capability__title">
                    Record what happened.
                </div>
                <div class="nbb-capability__description">
                    Store dated observations covering symptoms, routines,
                    medication, navigation, significant episodes, contextual
                    changes, and improvements.
                </div>
            </article>

            <article class="nbb-capability">
                <div class="nbb-capability__index">02 / REMEMBER</div>
                <div class="nbb-capability__title">
                    Preserve context locally.
                </div>
                <div class="nbb-capability__description">
                    Write each observation to an inspectable local record and
                    a semantic memory layer powered by Supermemory Local.
                </div>
            </article>

            <article class="nbb-capability">
                <div class="nbb-capability__index">03 / CONNECT</div>
                <div class="nbb-capability__title">
                    Relate events across time.
                </div>
                <div class="nbb-capability__description">
                    Connect new observations with previous symptoms, appointments,
                    recommendations, interventions, and outcomes.
                </div>
            </article>

            <article class="nbb-capability">
                <div class="nbb-capability__index">04 / RETRIEVE</div>
                <div class="nbb-capability__title">
                    Ask the complete history.
                </div>
                <div class="nbb-capability__description">
                    Retrieve source-grounded records using questions such as
                    “What changed after the last appointment?” or “What was
                    observed before the latest episode?”
                </div>
            </article>

            <article class="nbb-capability">
                <div class="nbb-capability__index">05 / PREPARE</div>
                <div class="nbb-capability__title">
                    Enter the next visit prepared.
                </div>
                <div class="nbb-capability__description">
                    Generate a structured interval history, before-episode
                    reconstruction, and caregiver-clinician preparation summary.
                </div>
            </article>
        </div>
    </section>
    """
)

st.divider()


# =============================================================================
# Two-sided value
# =============================================================================

render(
    """
    <section class="nbb-section">
        <div class="nbb-section-header">
            <div class="nbb-section-header__index">
                03 / SHARED CONTEXT
            </div>

            <div>
                <h2 class="nbb-section-header__title">
                    One longitudinal record for families, caregivers, and clinicians.
                </h2>

                <p class="nbb-section-header__description">
                    The prototype supports continuity of information without
                    presenting itself as a diagnostic system or a replacement
                    for formal clinical documentation.
                </p>
            </div>
        </div>

        <div class="nbb-audience-grid">
            <article class="nbb-audience">
                <div class="nbb-audience__label">
                    Families and caregivers
                </div>

                <h3 class="nbb-audience__title">
                    Preserve the details that memory loses.
                </h3>

                <ul>
                    <li>
                        Record subtle changes before they collapse into vague recall.
                    </li>
                    <li>
                        Track improvement, deterioration, and recurring patterns.
                    </li>
                    <li>
                        Recall previous recommendations and appointment context.
                    </li>
                    <li>
                        Prepare concrete questions before the next visit.
                    </li>
                    <li>
                        Maintain continuity when several relatives provide care.
                    </li>
                </ul>
            </article>

            <article class="nbb-audience nbb-audience--clinical">
                <div class="nbb-audience__label">
                    Clinician preparation
                </div>

                <h3 class="nbb-audience__title">
                    Review a structured interval history.
                </h3>

                <ul>
                    <li>
                        See how caregiver-reported observations evolved over time.
                    </li>
                    <li>
                        Inspect source records instead of relying only on summaries.
                    </li>
                    <li>
                        Review context around medication, routines, or interventions.
                    </li>
                    <li>
                        Reduce repeated reconstruction of the same patient history.
                    </li>
                    <li>
                        Identify areas that may warrant further clinical questioning.
                    </li>
                </ul>
            </article>
        </div>
    </section>
    """
)

st.divider()


# =============================================================================
# Live prototype
# =============================================================================

render(
    """
    <section class="nbb-section">
        <div class="nbb-section-header">
            <div class="nbb-section-header__index">
                04 / WORKING PROTOTYPE
            </div>

            <div>
                <h2 class="nbb-section-header__title">
                    Search, record, reconstruct, and prepare.
                </h2>

                <p class="nbb-section-header__description">
                    The operational console demonstrates the complete local-first
                    workflow using the existing caregiver observation record.
                </p>
            </div>
        </div>
    </section>
    """
)

render(
    f"""
    <div class="nbb-metric-strip">
        <div class="nbb-metric">
            <div class="nbb-metric__label">Total observations</div>
            <div class="nbb-metric__value">{metrics["total"]}</div>
        </div>

        <div class="nbb-metric">
            <div class="nbb-metric__label">Speech records</div>
            <div class="nbb-metric__value">{metrics["speech"]}</div>
        </div>

        <div class="nbb-metric">
            <div class="nbb-metric__label">Repetition records</div>
            <div class="nbb-metric__value">{metrics["repetition"]}</div>
        </div>

        <div class="nbb-metric">
            <div class="nbb-metric__label">High-severity records</div>
            <div class="nbb-metric__value">{metrics["high"]}</div>
        </div>
    </div>
    """
)

if st.session_state["last_save_message"]:
    if st.session_state["last_save_success"]:
        st.success(st.session_state["last_save_message"])
    else:
        st.warning(st.session_state["last_save_message"])

render(
    f"""
    <div class="nbb-console-header">
        <div class="nbb-console-header__title">
            NeuroBlackBox local console
        </div>

        <div class="nbb-console-header__status">
            Supermemory: {escape(memory_status)}
        </div>
    </div>
    """
)

console_left, console_right = st.columns(
    [0.82, 1.18],
    gap="large",
)

with console_left:
    st.markdown("### Retrieve the longitudinal record")

    query_col_1, query_col_2 = st.columns(2)

    with query_col_1:
        if st.button(
            "Changes in 30 days",
            use_container_width=True,
        ):
            set_query(
                "What changed over the last 30 days?"
            )

        if st.button(
            "Repetition patterns",
            use_container_width=True,
        ):
            set_query(
                "How have repeated questions changed?"
            )

    with query_col_2:
        if st.button(
            "Speech and pauses",
            use_container_width=True,
        ):
            set_query(
                "What speech pauses or word-finding changes were recorded?"
            )

        if st.button(
            "Before latest episode",
            use_container_width=True,
        ):
            set_query(
                "What was observed before the latest high-severity episode?"
            )

    question = st.text_input(
        "Ask the longitudinal record",
        key="query",
        placeholder=(
            "Example: What changed after the previous appointment?"
        ),
    )

    if question.strip():
        with st.spinner(
            "Searching the local memory record..."
        ):
            try:
                semantic_results = search_observations(
                    question,
                    limit=5,
                )
            except Exception:
                semantic_results = []

        used_semantic_results = display_memory_results(
            semantic_results
        )

        if not used_semantic_results:
            st.caption(
                "Semantic retrieval returned no records. "
                "Displaying deterministic local fallback."
            )

            fallback_results = deterministic_recall(
                df,
                question,
            )

            if fallback_results.empty:
                st.info(
                    "No matching source observations were found."
                )
            else:
                for _, row in fallback_results.iterrows():
                    render(
                        f"""
                        <article class="nbb-memory-result">
                            <div class="nbb-memory-result__meta">
                                Local source record ·
                                {escape(row["date"].strftime("%b %d, %Y"))}
                            </div>

                            <div class="nbb-memory-result__content">
                                <strong>
                                    {escape(row["type"])} ·
                                    {escape(row["severity"])}
                                </strong>
                                <br>
                                {escape(row["observation"])}
                            </div>
                        </article>
                        """
                    )

    st.markdown("### Record a new observation")

    with st.form(
        "observation_form",
        clear_on_submit=True,
    ):
        observation_date = st.date_input(
            "Observation date",
            value=date.today(),
        )

        observation_type = st.selectbox(
            "Observation category",
            options=OBSERVATION_TYPES,
        )

        severity = st.selectbox(
            "Recorded severity",
            options=SEVERITY_LEVELS,
        )

        source = st.text_input(
            "Source",
            value="caregiver",
        )

        observation = st.text_area(
            "Direct observation",
            placeholder=(
                "Describe what was directly observed, including context. "
                "Avoid diagnosis or interpretation where possible."
            ),
            height=150,
        )

        submitted = st.form_submit_button(
            "Save observation",
            use_container_width=True,
        )

    if submitted:
        cleaned_observation = observation.strip()
        cleaned_source = source.strip() or "caregiver"

        if not cleaned_observation:
            st.error(
                "Enter an observation before saving."
            )
        else:
            memory_row = {
                "date": observation_date.isoformat(),
                "type": observation_type,
                "severity": severity,
                "source": cleaned_source,
                "observation": cleaned_observation,
            }

            new_row = pd.DataFrame(
                [
                    {
                        "date": pd.to_datetime(observation_date),
                        "type": observation_type,
                        "severity": severity,
                        "source": cleaned_source,
                        "observation": cleaned_observation,
                    }
                ]
            )

            updated_df = pd.concat(
                [
                    df,
                    new_row,
                ],
                ignore_index=True,
            )

            save_data(updated_df)

            try:
                stored_in_memory = store_observation(
                    memory_row
                )
            except Exception:
                stored_in_memory = False

            if stored_in_memory:
                st.session_state["last_save_success"] = True
                st.session_state["last_save_message"] = (
                    "Observation saved to the local record "
                    "and Supermemory Local."
                )
            else:
                st.session_state["last_save_success"] = False
                st.session_state["last_save_message"] = (
                    "Observation saved to the local record. "
                    "The Supermemory Local write was not confirmed."
                )

            st.rerun()

with console_right:
    st.markdown("### Before-episode reconstruction")

    render(
        f"""
        <div class="nbb-document">
            <div class="nbb-document__label">
                Source-grounded reconstruction
            </div>
            <pre>{escape(before_episode_analysis)}</pre>
        </div>
        """
    )

    st.markdown("### Source observation table")

    if df.empty:
        st.info(
            "No observations are currently available."
        )
    else:
        timeline = df.copy()

        timeline["date"] = timeline["date"].dt.strftime(
            "%Y-%m-%d"
        )

        st.dataframe(
            timeline[
                [
                    "date",
                    "type",
                    "severity",
                    "source",
                    "observation",
                ]
            ],
            use_container_width=True,
            hide_index=True,
            height=390,
        )

st.divider()


# =============================================================================
# Generated review documents
# =============================================================================

render(
    """
    <section class="nbb-section">
        <div class="nbb-section-header">
            <div class="nbb-section-header__index">
                05 / REVIEW DOCUMENTS
            </div>

            <div>
                <h2 class="nbb-section-header__title">
                    Structured outputs for the next clinical conversation.
                </h2>

                <p class="nbb-section-header__description">
                    Each document remains descriptive, source-grounded, and
                    explicitly separated from diagnosis or treatment.
                </p>
            </div>
        </div>
    </section>
    """
)

document_left, document_right = st.columns(
    2,
    gap="large",
)

with document_left:
    render(
        f"""
        <div class="nbb-document">
            <div class="nbb-document__label">
                Thirty-day observation brief
            </div>
            <pre>{escape(thirty_day_brief)}</pre>
        </div>
        """
    )

    st.download_button(
        label="Download thirty-day brief",
        data=thirty_day_brief,
        file_name=(
            "neuroblackbox_thirty_day_observation_brief.md"
        ),
        mime="text/markdown",
        use_container_width=True,
    )

with document_right:
    render(
        f"""
        <div class="nbb-document">
            <div class="nbb-document__label">
                Caregiver-clinician preparation summary
            </div>
            <pre>{escape(clinician_summary)}</pre>
        </div>
        """
    )

    st.download_button(
        label="Download clinician-preparation summary",
        data=clinician_summary,
        file_name=(
            "neuroblackbox_clinician_preparation_summary.md"
        ),
        mime="text/markdown",
        use_container_width=True,
    )

st.download_button(
    label="Download before-episode reconstruction",
    data=before_episode_analysis,
    file_name=(
        "neuroblackbox_before_episode_reconstruction.md"
    ),
    mime="text/markdown",
    use_container_width=True,
)

st.divider()


# =============================================================================
# Research boundary
# =============================================================================

render(
    """
    <section class="nbb-section">
        <div class="nbb-section-header">
            <div class="nbb-section-header__index">
                06 / RESEARCH BOUNDARY
            </div>

            <div>
                <h2 class="nbb-section-header__title">
                    A continuity tool, not a diagnostic system.
                </h2>

                <p class="nbb-section-header__description">
                    The prototype is intentionally constrained. Its reliability
                    depends on the quality and completeness of caregiver-entered
                    observations.
                </p>
            </div>
        </div>

        <div class="nbb-limitations">
            <article class="nbb-limitation">
                <div class="nbb-limitation__title">
                    Caregiver-entered evidence
                </div>
                <div class="nbb-limitation__text">
                    The system cannot independently verify whether an observation
                    is complete, representative, or consistently interpreted.
                </div>
            </article>

            <article class="nbb-limitation">
                <div class="nbb-limitation__title">
                    No causal inference
                </div>
                <div class="nbb-limitation__text">
                    An event occurring before an episode does not establish that
                    it predicted or caused the episode.
                </div>
            </article>

            <article class="nbb-limitation">
                <div class="nbb-limitation__title">
                    No clinical validation
                </div>
                <div class="nbb-limitation__text">
                    NeuroBlackBox has not undergone clinical validation,
                    regulatory review, or medical-device assessment.
                </div>
            </article>

            <article class="nbb-limitation">
                <div class="nbb-limitation__title">
                    Retrieval can be incomplete
                </div>
                <div class="nbb-limitation__text">
                    Semantic retrieval may omit relevant records or return
                    observations that are only weakly related to the question.
                </div>
            </article>

            <article class="nbb-limitation">
                <div class="nbb-limitation__title">
                    Not an official medical record
                </div>
                <div class="nbb-limitation__text">
                    Generated summaries support preparation and continuity.
                    They do not replace formal clinical documentation.
                </div>
            </article>

            <article class="nbb-limitation">
                <div class="nbb-limitation__title">
                    Human review remains essential
                </div>
                <div class="nbb-limitation__text">
                    Families and qualified clinicians should review all records
                    and decide whether further evaluation is appropriate.
                </div>
            </article>
        </div>
    </section>
    """
)


# =============================================================================
# Footer
# =============================================================================

render(
    """
    <footer class="nbb-footer">
        <div>
            <strong>NeuroBlackBox</strong><br>
            Longitudinal local memory for caregiver observations and
            clinician preparation.
        </div>

        <div>
            Python · Streamlit · Pandas · Supermemory Local
        </div>
    </footer>
    """
)