from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any
import html
import os
import re
import shutil

import pandas as pd
import streamlit as st

from memory_client import (
    check_connection,
    search_observations,
    store_observation,
    sync_observations,
)


# =============================================================================
# Configuration
# =============================================================================

APP_NAME = "NeuroBlackBox"

APP_DESCRIPTION = (
    "Longitudinal local memory for cognitive-care observations "
    "and clinician preparation."
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SEED_DATA_PATH = REPOSITORY_ROOT / "data" / "sample_observations.csv"
DEFAULT_RUNTIME_DATA_PATH = (
    REPOSITORY_ROOT / "data" / "runtime_observations.csv"
)

configured_data_path = Path(
    os.getenv(
        "NEUROBLACKBOX_DATA_PATH",
        str(DEFAULT_RUNTIME_DATA_PATH),
    )
).expanduser()

DATA_PATH = (
    configured_data_path
    if configured_data_path.is_absolute()
    else REPOSITORY_ROOT / configured_data_path
)

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
    "appointment",
    "intervention",
    "improvement",
    "other",
]

SEVERITY_LEVELS = [
    "low",
    "medium",
    "high",
]

st.set_page_config(
    page_title="NeuroBlackBox | Cognitive Care Memory Infrastructure",
    page_icon="◉",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# =============================================================================
# Generic utilities
# =============================================================================

def escape(value: Any) -> str:
    return html.escape(str(value))


def render(markup: str) -> None:
    """
    Render HTML directly with Streamlit's HTML renderer.

    This prevents custom HTML from being interpreted as Markdown code.
    """
    st.html(markup)


def empty_observation_frame() -> pd.DataFrame:
    return pd.DataFrame(
        columns=OBSERVATION_COLUMNS,
    )


# =============================================================================
# Data loading and persistence
# =============================================================================


class ObservationDataError(RuntimeError):
    """Raised when the local observation record cannot be initialized/read."""


def ensure_runtime_data() -> None:
    runtime_path = DATA_PATH.resolve()
    seed_path = SEED_DATA_PATH.resolve()

    if runtime_path == seed_path:
        raise ObservationDataError(
            "NEUROBLACKBOX_DATA_PATH must not point to the tracked "
            "synthetic seed. Choose a separate local runtime file."
        )

    if DATA_PATH.exists():
        return

    if not SEED_DATA_PATH.exists():
        raise ObservationDataError(
            f"Synthetic seed data was not found at {SEED_DATA_PATH}."
        )

    try:
        DATA_PATH.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        shutil.copy2(
            SEED_DATA_PATH,
            DATA_PATH,
        )
    except OSError as exc:
        raise ObservationDataError(
            f"Could not initialize the local runtime record at {DATA_PATH}."
        ) from exc


def normalize_observation_frame(
    df: pd.DataFrame,
) -> pd.DataFrame:
    if df.empty:
        return empty_observation_frame()

    normalized = df.copy()

    for column in OBSERVATION_COLUMNS:
        if column not in normalized.columns:
            normalized[column] = ""

    normalized = normalized[
        OBSERVATION_COLUMNS
    ]

    normalized["date"] = pd.to_datetime(
        normalized["date"],
        errors="coerce",
    )

    normalized = normalized.dropna(
        subset=["date"],
    )

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

    normalized["type"] = (
        normalized["type"]
        .str.lower()
    )

    normalized["severity"] = (
        normalized["severity"]
        .str.lower()
    )

    normalized = normalized.drop_duplicates(
        subset=OBSERVATION_COLUMNS,
        keep="first",
    )

    return normalized.sort_values(
        by="date",
        ascending=True,
    ).reset_index(
        drop=True,
    )


@st.cache_data(
    show_spinner=False,
)
def load_data(
    modified_time: float | None = None,
) -> pd.DataFrame:
    del modified_time

    try:
        frame = pd.read_csv(
            DATA_PATH,
        )
    except (
        OSError,
        UnicodeError,
        pd.errors.ParserError,
    ) as exc:
        raise ObservationDataError(
            f"Could not read the local runtime record at {DATA_PATH}."
        ) from exc

    return normalize_observation_frame(
        frame,
    )


def get_data() -> pd.DataFrame:
    ensure_runtime_data()

    modified_time = (
        DATA_PATH.stat().st_mtime
        if DATA_PATH.exists()
        else None
    )

    return load_data(
        modified_time,
    )


def save_data(
    df: pd.DataFrame,
) -> None:
    DATA_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    normalized = normalize_observation_frame(
        df,
    )

    normalized.to_csv(
        DATA_PATH,
        index=False,
        date_format="%Y-%m-%d",
    )

    load_data.clear()


def memory_rows(
    df: pd.DataFrame,
) -> list[dict[str, str]]:
    prepared = normalize_observation_frame(df).copy()

    if prepared.empty:
        return []

    prepared["date"] = prepared["date"].dt.strftime(
        "%Y-%m-%d",
    )

    return prepared[OBSERVATION_COLUMNS].to_dict(
        orient="records",
    )


def memory_data_signature(
    rows: list[dict[str, str]],
) -> tuple[tuple[str, ...], ...]:
    return tuple(
        tuple(str(row.get(column, "")) for column in OBSERVATION_COLUMNS)
        for row in rows
    )


# =============================================================================
# Descriptive analysis
# =============================================================================

def keyword_count(
    text: str,
    keywords: list[str],
) -> int:
    alternatives = sorted(
        {
            re.escape(keyword.lower())
            for keyword in keywords
            if keyword
        },
        key=len,
        reverse=True,
    )

    if not alternatives:
        return 0

    pattern = re.compile(
        "|".join(alternatives),
        flags=re.IGNORECASE,
    )

    return sum(1 for _ in pattern.finditer(text))


def combined_observation_text(
    df: pd.DataFrame,
) -> str:
    if df.empty:
        return ""

    return " ".join(
        df["observation"]
        .fillna("")
        .astype(str)
        .tolist()
    )


def analyze_observations(
    df: pd.DataFrame,
) -> dict[str, int]:
    if df.empty:
        return {
            "total": 0,
            "speech": 0,
            "repetition": 0,
            "routine": 0,
            "episode": 0,
            "medication": 0,
            "navigation": 0,
            "appointment": 0,
            "intervention": 0,
            "improvement": 0,
            "high": 0,
            "pause_mentions": 0,
            "repetition_mentions": 0,
        }

    text = combined_observation_text(
        df,
    )

    return {
        "total": int(
            len(df)
        ),
        "speech": int(
            (df["type"] == "speech").sum()
        ),
        "repetition": int(
            (df["type"] == "repetition").sum()
        ),
        "routine": int(
            (df["type"] == "routine").sum()
        ),
        "episode": int(
            (df["type"] == "episode").sum()
        ),
        "medication": int(
            (df["type"] == "medication").sum()
        ),
        "navigation": int(
            (df["type"] == "navigation").sum()
        ),
        "appointment": int(
            (df["type"] == "appointment").sum()
        ),
        "intervention": int(
            (df["type"] == "intervention").sum()
        ),
        "improvement": int(
            (df["type"] == "improvement").sum()
        ),
        "high": int(
            (df["severity"] == "high").sum()
        ),
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

    return candidates.sort_values(
        "date",
    ).iloc[-1]


def before_episode_window(
    df: pd.DataFrame,
    days_before: int = 10,
) -> tuple[pd.Series | None, pd.DataFrame]:
    episode = latest_high_severity_episode(
        df,
    )

    if episode is None:
        return (
            None,
            empty_observation_frame(),
        )

    episode_date = pd.Timestamp(
        episode["date"],
    )

    start_date = episode_date - timedelta(
        days=days_before,
    )

    window = df[
        (df["date"] >= start_date)
        & (df["date"] < episode_date)
    ].copy()

    return (
        episode,
        window.sort_values("date"),
    )


def thirty_day_window(
    df: pd.DataFrame,
) -> pd.DataFrame:
    if df.empty:
        return df.copy()

    end_date = df["date"].max()

    start_date = end_date - timedelta(
        days=30,
    )

    return df[
        (df["date"] >= start_date)
        & (df["date"] <= end_date)
    ].copy()


def format_observation(
    row: pd.Series,
) -> str:
    observation_date = pd.Timestamp(
        row["date"],
    ).strftime(
        "%b %d, %Y",
    )

    return (
        f"{observation_date} | "
        f"{row['type']} | "
        f"{row['severity']} | "
        f"{row['observation']}"
    )


# =============================================================================
# Generated analysis outputs
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

    episode_date = pd.Timestamp(
        episode["date"],
    )

    start_date = episode_date - timedelta(
        days=days_before,
    )

    lines = [
        "BEFORE-EPISODE RECONSTRUCTION",
        "",
        (
            "Index episode: "
            f"{episode_date.strftime('%b %d, %Y')}"
        ),
        (
            "Episode record: "
            f"{episode['observation']}"
        ),
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
                (
                    "No observations were recorded "
                    "during this interval."
                ),
                "",
                (
                    "Important limitation: absence of recorded "
                    "observations does not establish absence of "
                    "preceding changes."
                ),
            ]
        )

        return "\n".join(
            lines,
        )

    metrics = analyze_observations(
        window,
    )

    lines.extend(
        [
            "Descriptive signals recorded during the interval:",
            f"- Speech observations: {metrics['speech']}",
            f"- Repetition observations: {metrics['repetition']}",
            f"- Routine observations: {metrics['routine']}",
            f"- Medication observations: {metrics['medication']}",
            f"- Navigation observations: {metrics['navigation']}",
            (
                "- Recorded pause or word-finding mentions: "
                f"{metrics['pause_mentions']}"
            ),
            (
                "- Recorded repetition-related mentions: "
                f"{metrics['repetition_mentions']}"
            ),
            "",
            "Source observations:",
        ]
    )

    for _, row in window.iterrows():
        lines.append(
            f"- {format_observation(row)}"
        )

    lines.extend(
        [
            "",
            "These observations were recorded before the episode.",
            "",
            "Review boundary:",
            (
                "This reconstruction organizes caregiver-entered "
                "observations. It does not establish causation, "
                "diagnosis, disease progression, or predictive risk."
            ),
        ]
    )

    return "\n".join(
        lines,
    )


def generate_thirty_day_brief(
    df: pd.DataFrame,
) -> str:
    recent = thirty_day_window(
        df,
    )

    if recent.empty:
        return (
            "No observations are available "
            "for the current review period."
        )

    metrics = analyze_observations(
        recent,
    )

    first_date = recent["date"].min().strftime(
        "%b %d, %Y",
    )

    last_date = recent["date"].max().strftime(
        "%b %d, %Y",
    )

    lines = [
        "THIRTY-DAY OBSERVATION BRIEF",
        "",
        (
            f"Review period: "
            f"{first_date} to {last_date}"
        ),
        "",
        "Observation-log composition:",
        f"- Total observations: {metrics['total']}",
        f"- Speech observations: {metrics['speech']}",
        f"- Repetition observations: {metrics['repetition']}",
        f"- Routine observations: {metrics['routine']}",
        f"- Medication observations: {metrics['medication']}",
        f"- Navigation observations: {metrics['navigation']}",
        f"- High-severity observations: {metrics['high']}",
        (
            "- Recorded pause or word-finding mentions: "
            f"{metrics['pause_mentions']}"
        ),
        (
            "- Recorded repetition-related mentions: "
            f"{metrics['repetition_mentions']}"
        ),
        "",
        "Interpretation boundary:",
        (
            "These values summarize the observation log. "
            "They are not clinical scores and do not measure "
            "cognitive function or disease progression."
        ),
    ]

    return "\n".join(
        lines,
    )


def generate_clinician_preparation_summary(
    df: pd.DataFrame,
) -> str:
    if df.empty:
        return "No observations are available."

    metrics = analyze_observations(
        df,
    )

    first_date = df["date"].min().strftime(
        "%b %d, %Y",
    )

    last_date = df["date"].max().strftime(
        "%b %d, %Y",
    )

    high_severity = df[
        df["severity"] == "high"
    ].sort_values(
        "date",
    )

    recent = df.sort_values(
        "date",
    ).tail(
        6,
    )

    lines = [
        "CAREGIVER-CLINICIAN PREPARATION SUMMARY",
        "",
        (
            f"Observation period: "
            f"{first_date} to {last_date}"
        ),
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
            lines.append(
                f"- {format_observation(row)}"
            )

    lines.extend(
        [
            "",
            "Most recent source records:",
        ]
    )

    for _, row in recent.iterrows():
        lines.append(
            f"- {format_observation(row)}"
        )

    lines.extend(
        [
            "",
            "Potential questions for clinical discussion:",
            (
                "- Which observations, routines, medication effects, "
                "sleep changes, or environmental factors should "
                "be monitored more systematically?"
            ),
            (
                "- Are the recorded changes sufficiently concerning "
                "to justify formal assessment or additional investigation?"
            ),
            (
                "- Which recommendations from this visit should the "
                "family record and review before the next appointment?"
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

    return "\n".join(
        lines,
    )


# =============================================================================
# Retrieval fallback
# =============================================================================


BEFORE_EPISODE_QUERY_PATTERN = re.compile(
    r"\bbefore\s+(?:the\s+)?(?:last|latest)"
    r"(?:\s+(?:bad|high[-\s]severity))?\s+episode\b",
    flags=re.IGNORECASE,
)


def is_before_episode_question(
    question: str,
) -> bool:
    normalized = " ".join(question.lower().split())
    return (
        "before episode" in normalized
        or "before the episode" in normalized
        or bool(
            BEFORE_EPISODE_QUERY_PATTERN.search(
                normalized,
            )
        )
    )


def deterministic_recall(
    df: pd.DataFrame,
    question: str,
) -> pd.DataFrame:
    if df.empty:
        return df.copy()

    query = question.lower().strip()

    if is_before_episode_question(query):
        _, window = before_episode_window(
            df,
        )

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
            "appointment",
            "last visit",
            "previous visit",
        ]
    ):
        return df[
            df["type"].isin(
                [
                    "appointment",
                    "intervention",
                    "improvement",
                    "medication",
                ]
            )
        ]

    if any(
        phrase in query
        for phrase in [
            "routine",
            "daily activity",
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

    return df.sort_values(
        "date",
    ).tail(
        6,
    )

# =============================================================================
# Grounded question answering
# =============================================================================

SEVERITY_RANK = {
    "low": 1,
    "medium": 2,
    "high": 3,
}


def format_date_range(
    records: pd.DataFrame,
) -> str:
    if records.empty:
        return "No matching dates"

    first_date = records["date"].min().strftime(
        "%b %d, %Y",
    )

    last_date = records["date"].max().strftime(
        "%b %d, %Y",
    )

    if first_date == last_date:
        return first_date

    return f"{first_date} – {last_date}"


def severity_summary(
    records: pd.DataFrame,
) -> str:
    if records.empty:
        return "No severity data"

    counts = (
        records["severity"]
        .value_counts()
        .to_dict()
    )

    parts = []

    for severity in [
        "high",
        "medium",
        "low",
    ]:
        count = int(
            counts.get(
                severity,
                0,
            )
        )

        if count:
            parts.append(
                f"{count} {severity}"
            )

    return ", ".join(parts) or "No severity data"


def category_summary(
    records: pd.DataFrame,
) -> str:
    if records.empty:
        return "No matching categories"

    counts = (
        records["type"]
        .value_counts()
        .head(4)
    )

    return ", ".join(
        f"{category}: {int(count)}"
        for category, count in counts.items()
    )


def records_for_repetition(
    df: pd.DataFrame,
) -> pd.DataFrame:
    records = df[
        (df["type"] == "repetition")
        | df["observation"].str.contains(
            (
                "repeated question|repeated the same question|"
                "asked the same question|same question|"
                "repeated story|same story|asked again"
            ),
            case=False,
            regex=True,
            na=False,
        )
    ].copy()

    return (
        records
        .drop_duplicates(
            subset=[
                "date",
                "observation",
            ],
        )
        .sort_values("date")
        .reset_index(drop=True)
    )


def records_for_speech(
    df: pd.DataFrame,
) -> pd.DataFrame:
    records = df[
        (df["type"] == "speech")
        | df["observation"].str.contains(
            (
                "speech pause|longer pause|paused|"
                "word.finding|searching for words|"
                "remember a familiar name"
            ),
            case=False,
            regex=True,
            na=False,
        )
    ].copy()

    return (
        records
        .drop_duplicates(
            subset=[
                "date",
                "observation",
            ],
        )
        .sort_values("date")
        .reset_index(drop=True)
    )


def records_for_improvements(
    df: pd.DataFrame,
) -> pd.DataFrame:
    return df[
        (df["type"] == "improvement")
        | df["observation"].str.contains(
            (
                "improved|improvement|better|"
                "fewer|less frequent|returned to normal"
            ),
            case=False,
            regex=True,
            na=False,
        )
    ].sort_values(
        "date",
    )


def evidence_items(
    records: pd.DataFrame,
    limit: int = 4,
) -> list[str]:
    if records.empty:
        return []

    selected = records.sort_values(
        "date",
    ).tail(
        limit,
    )

    items = []

    for _, row in selected.iterrows():
        item_date = row["date"].strftime(
            "%b %d",
        )

        items.append(
            (
                f"{item_date} — "
                f"{row['type']} / {row['severity']}: "
                f"{row['observation']}"
            )
        )

    return items


def compare_early_and_late_frequency(
    records: pd.DataFrame,
) -> str:
    """
    Describe distribution across time without claiming clinical progression.
    """
    if len(records) < 2:
        return (
            "There are not enough matching records to assess "
            "how the pattern changed over time."
        )

    ordered = records.sort_values(
        "date",
    )

    midpoint = (
        ordered["date"].min()
        + (
            ordered["date"].max()
            - ordered["date"].min()
        ) / 2
    )

    early_count = int(
        (ordered["date"] <= midpoint).sum()
    )

    late_count = int(
        (ordered["date"] > midpoint).sum()
    )

    if late_count > early_count:
        return (
            "More matching observations were recorded in the later "
            "half of the observation period."
        )

    if late_count < early_count:
        return (
            "More matching observations were recorded in the earlier "
            "half of the observation period."
        )

    return (
        "Matching observations were distributed relatively evenly "
        "across the observation period."
    )


def generate_grounded_answer(
    df: pd.DataFrame,
    question: str,
) -> dict[str, Any]:
    """
    Generate a conservative answer grounded in the local source record.

    This function summarizes caregiver-entered observations only.
    It does not perform diagnosis, prediction, or causal inference.
    """
    normalized_question = question.lower().strip()

    if df.empty:
        return {
            "title": "No observation record available",
            "answer": (
                "NeuroBlackBox cannot answer this question because "
                "the local observation record is empty."
            ),
            "evidence": [],
            "record_count": 0,
            "date_range": "No data",
            "boundary": (
                "This response summarizes recorded observations only."
            ),
        }

    # -------------------------------------------------------------------------
    # Before latest high-severity episode
    # -------------------------------------------------------------------------

    if is_before_episode_question(
        normalized_question,
    ):
        episode, records = before_episode_window(
            df,
            days_before=10,
        )

        if episode is None:
            return {
                "title": "No qualifying episode found",
                "answer": (
                    "No observation is currently categorized as both "
                    "an episode and high severity, so a before-episode "
                    "reconstruction cannot be generated."
                ),
                "evidence": [],
                "record_count": 0,
                "date_range": "No qualifying episode",
                "boundary": (
                    "Absence of a qualifying record does not mean "
                    "that no significant event occurred."
                ),
            }

        episode_date = pd.Timestamp(
            episode["date"],
        ).strftime(
            "%b %d, %Y",
        )

        metrics = analyze_observations(
            records,
        )

        answer = (
            f"In the 10 days before the high-severity episode on "
            f"{episode_date}, {len(records)} source observations were "
            f"recorded. They included "
            f"{metrics['speech']} speech observation(s), "
            f"{metrics['repetition']} repetition observation(s), and "
            f"{metrics['routine']} routine observation(s). "
            "These observations were recorded before the episode. "
            "They do not establish prediction or causation."
        )

        return {
            "title": "Observations preceding the latest episode",
            "answer": answer,
            "evidence": evidence_items(
                records,
                limit=5,
            ),
            "record_count": len(records),
            "date_range": format_date_range(
                records,
            ),
            "boundary": (
                "Temporal proximity does not establish that an observation "
                "predicted or caused the episode."
            ),
        }

    # -------------------------------------------------------------------------
    # Repetition
    # -------------------------------------------------------------------------

    if any(
        phrase in normalized_question
        for phrase in [
            "repeat",
            "repetition",
            "repeated question",
            "repeated questions",
            "same question",
            "same story",
        ]
    ):
        records = records_for_repetition(
            df,
        )

        if records.empty:
            return {
                "title": "No repetition-related records found",
                "answer": (
                    "No repetition-related observations were found "
                    "in the current local record."
                ),
                "evidence": [],
                "record_count": 0,
                "date_range": "No matching records",
                "boundary": (
                    "This result reflects only observations entered "
                    "into NeuroBlackBox."
                ),
            }

        frequency_statement = (
            compare_early_and_late_frequency(
                records,
            )
        )

        high_count = int(
            (records["severity"] == "high").sum()
        )

        answer = (
            f"{len(records)} repetition-related observation(s) were "
            f"recorded between {format_date_range(records)}. "
            f"{frequency_statement} "
        )

        if high_count:
            answer += (
                f"The record includes {high_count} high-severity "
                "repetition observation(s). "
            )

        answer += (
            "The pattern is recurrent in the caregiver record, but the "
            "available observations do not by themselves establish clinical "
            "progression."
        )

        return {
            "title": "Repeated questions appear as a recurring pattern",
            "answer": answer,
            "evidence": evidence_items(
                records,
                limit=5,
            ),
            "record_count": len(records),
            "date_range": format_date_range(
                records,
            ),
            "boundary": (
                "Frequency in the log may also reflect how often caregivers "
                "entered observations."
            ),
        }

    # -------------------------------------------------------------------------
    # Speech pauses and word finding
    # -------------------------------------------------------------------------

    if any(
        phrase in normalized_question
        for phrase in [
            "speech",
            "pause",
            "pauses",
            "word finding",
            "word-finding",
            "speaking",
        ]
    ):
        records = records_for_speech(
            df,
        )

        if records.empty:
            return {
                "title": "No speech-related records found",
                "answer": (
                    "No speech-pause or word-finding observations were "
                    "found in the current local record."
                ),
                "evidence": [],
                "record_count": 0,
                "date_range": "No matching records",
                "boundary": (
                    "This result reflects only observations entered "
                    "into NeuroBlackBox."
                ),
            }

        frequency_statement = (
            compare_early_and_late_frequency(
                records,
            )
        )

        answer = (
            f"{len(records)} speech-related observation(s) were recorded "
            f"between {format_date_range(records)}. "
            f"{frequency_statement} "
            f"The recorded severity mix is {severity_summary(records)}. "
            "Several records mention longer pauses or difficulty recalling "
            "familiar words or names."
        )

        return {
            "title": "Speech pauses and word-finding changes were recorded",
            "answer": answer,
            "evidence": evidence_items(
                records,
                limit=5,
            ),
            "record_count": len(records),
            "date_range": format_date_range(
                records,
            ),
            "boundary": (
                "This describes caregiver-entered observations and is not "
                "a cognitive assessment."
            ),
        }

    # -------------------------------------------------------------------------
    # Improvements
    # -------------------------------------------------------------------------

    if any(
        phrase in normalized_question
        for phrase in [
            "improvement",
            "improvements",
            "improved",
            "better",
            "getting better",
        ]
    ):
        records = records_for_improvements(
            df,
        )

        if records.empty:
            return {
                "title": "No explicit improvement records found",
                "answer": (
                    "The current record does not contain observations "
                    "explicitly categorized or worded as improvements. "
                    "This does not establish that no improvement occurred."
                ),
                "evidence": [],
                "record_count": 0,
                "date_range": "No matching records",
                "boundary": (
                    "Only explicitly recorded observations can be summarized."
                ),
            }

        return {
            "title": "Recorded improvements",
            "answer": (
                f"{len(records)} improvement-related observation(s) were "
                f"recorded between {format_date_range(records)}."
            ),
            "evidence": evidence_items(
                records,
                limit=5,
            ),
            "record_count": len(records),
            "date_range": format_date_range(
                records,
            ),
            "boundary": (
                "These are caregiver-entered descriptions, not verified "
                "clinical outcomes."
            ),
        }

    # -------------------------------------------------------------------------
    # Clinician discussion
    # -------------------------------------------------------------------------

    if any(
        phrase in normalized_question
        for phrase in [
            "discuss with",
            "ask the doctor",
            "ask doctor",
            "tell the doctor",
            "clinician",
            "next appointment",
        ]
    ):
        high_records = df[
            df["severity"] == "high"
        ].sort_values(
            "date",
        )

        recent_records = df.sort_values(
            "date",
        ).tail(
            5,
        )

        evidence = evidence_items(
            high_records,
            limit=3,
        )

        evidence.extend(
            item
            for item in evidence_items(
                recent_records,
                limit=3,
            )
            if item not in evidence
        )

        answer = (
            "The next clinical discussion should prioritize the "
            f"{len(high_records)} high-severity record(s), recent speech "
            "and repetition changes, medication or routine disruptions, "
            "and whether any recommendations from the previous visit were "
            "followed and appeared helpful. Bring the dated source records "
            "so the clinician can review the original observations."
        )

        return {
            "title": "Priority topics for the next clinical discussion",
            "answer": answer,
            "evidence": evidence[:6],
            "record_count": len(
                high_records
            ),
            "date_range": format_date_range(
                df,
            ),
            "boundary": (
                "NeuroBlackBox organizes discussion topics but does not "
                "recommend diagnosis or treatment."
            ),
        }

    # -------------------------------------------------------------------------
    # Previous appointment / general change
    # -------------------------------------------------------------------------

    if any(
        phrase in normalized_question
        for phrase in [
            "last visit",
            "previous visit",
            "last appointment",
            "previous appointment",
            "what changed",
            "changes",
        ]
    ):
        appointment_records = df[
            df["type"] == "appointment"
        ].sort_values(
            "date",
        )

        if not appointment_records.empty:
            latest_appointment_date = (
                appointment_records["date"].max()
            )

            records = df[
                df["date"] > latest_appointment_date
            ].sort_values(
                "date",
            )
        else:
            records = thirty_day_window(
                df,
            )

        metrics = analyze_observations(
            records,
        )

        if records.empty:
            return {
                "title": "No later observations found",
                "answer": (
                    "No observations were recorded after the latest "
                    "appointment record."
                ),
                "evidence": [],
                "record_count": 0,
                "date_range": "No matching records",
                "boundary": (
                    "This result reflects the current local record only."
                ),
            }

        answer = (
            f"{len(records)} observation(s) were recorded during the "
            f"review period. The record includes "
            f"{metrics['speech']} speech, "
            f"{metrics['repetition']} repetition, "
            f"{metrics['routine']} routine, "
            f"{metrics['episode']} episode, and "
            f"{metrics['high']} high-severity observation(s). "
            f"The most represented categories were "
            f"{category_summary(records)}."
        )

        return {
            "title": "Changes recorded during the review period",
            "answer": answer,
            "evidence": evidence_items(
                records,
                limit=5,
            ),
            "record_count": len(records),
            "date_range": format_date_range(
                records,
            ),
            "boundary": (
                "Counts describe the observation log and are not measures "
                "of disease severity or progression."
            ),
        }

    # -------------------------------------------------------------------------
    # General fallback
    # -------------------------------------------------------------------------

    records = deterministic_recall(
        df,
        question,
    )

    metrics = analyze_observations(
        records,
    )

    if records.empty:
        return {
            "title": "No matching observations found",
            "answer": (
                "The local record does not contain observations that "
                "clearly answer this question."
            ),
            "evidence": [],
            "record_count": 0,
            "date_range": "No matching records",
            "boundary": (
                "Try asking about speech, repetition, routines, medication, "
                "episodes, improvements, or the previous appointment."
            ),
        }

    return {
        "title": "Summary of matching observations",
        "answer": (
            f"{len(records)} potentially relevant observation(s) were found "
            f"between {format_date_range(records)}. "
            f"The matching records include {category_summary(records)}, "
            f"with severity levels of {severity_summary(records)}."
        ),
        "evidence": evidence_items(
            records,
            limit=5,
        ),
        "record_count": len(records),
        "date_range": format_date_range(
            records,
        ),
        "boundary": (
            "This is a descriptive summary of caregiver-entered records."
        ),
    }


def display_grounded_answer(
    answer: dict[str, Any],
) -> None:
    evidence = answer.get(
        "evidence",
        [],
    )

    evidence_html = ""

    if evidence:
        evidence_html = (
            '<div class="answer-evidence">'
            '<div class="answer-evidence__heading">'
            'Evidence used'
            '</div>'
            + "".join(
                (
                    '<div class="answer-evidence__item">'
                    f'{escape(item)}'
                    '</div>'
                )
                for item in evidence
            )
            + "</div>"
        )

    render(
        f"""
        <article class="answer-card">
            <div class="answer-card__header">
                <div>
                    <div class="answer-card__eyebrow">
                        NeuroBlackBox answer
                    </div>

                    <div class="answer-card__title">
                        {escape(answer["title"])}
                    </div>
                </div>

                <div class="answer-card__count">
                    {escape(answer["record_count"])} records
                </div>
            </div>

            <div class="answer-card__body">
                <div class="answer-card__answer">
                    {escape(answer["answer"])}
                </div>

                <div class="answer-meta">
                    <div>
                        <span>Evidence period</span>
                        <strong>{escape(answer["date_range"])}</strong>
                    </div>
                </div>

                {evidence_html}

                <div class="answer-boundary">
                    <strong>Interpretation boundary</strong>
                    <br>
                    {escape(answer["boundary"])}
                </div>
            </div>
        </article>
        """
    )

# =============================================================================
# Supermemory result handling
# =============================================================================

def extract_result_content(
    result: Any,
) -> str:
    if isinstance(
        result,
        dict,
    ):
        direct_content = result.get(
            "content",
        )

        if direct_content:
            return str(
                direct_content,
            )

        chunks = result.get(
            "chunks",
        ) or []

        if chunks:
            first_chunk = chunks[0]

            if isinstance(
                first_chunk,
                dict,
            ):
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

        return str(
            result,
        )

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
            return str(
                value,
            )

    return str(
        result,
    )


def extract_result_score(
    result: Any,
) -> str:
    raw_score = (
        result.get("score")
        if isinstance(result, dict)
        else getattr(
            result,
            "score",
            None,
        )
    )

    if raw_score is None:
        return "not reported"

    try:
        return f"{float(raw_score):.2f}"
    except (
        TypeError,
        ValueError,
    ):
        return str(
            raw_score,
        )


def clean_memory_content(
    content: str,
) -> str:
    cleaned = content

    for prefix in [
        "NeuroBlackBox caregiver observation. ",
        "Patient: Eleanor. ",
    ]:
        cleaned = cleaned.replace(
            prefix,
            "",
        )

    return cleaned.strip()


def display_memory_results(
    results: list[Any],
) -> bool:
    if not results:
        return False

    render(
        """
        <div class="retrieval-heading">
            Retrieved longitudinal records
        </div>
        """
    )

    for result in results:
        content = clean_memory_content(
            extract_result_content(
                result,
            )
        )

        score = extract_result_score(
            result,
        )

        render(
            f"""
            <article class="memory-result">
                <div class="memory-result__header">
                    <span>Source observation</span>
                    <span>Relevance {escape(score)}</span>
                </div>

                <div class="memory-result__content">
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
        "memory_sync_attempted_signature": None,
        "memory_sync_message": "",
        "memory_sync_success": None,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def set_query(
    value: str,
) -> None:
    st.session_state["query"] = value


initialize_session_state()


# =============================================================================
# Current state
# =============================================================================

try:
    df = get_data()
except ObservationDataError as exc:
    st.error(str(exc))
    st.stop()

metrics = analyze_observations(
    df,
)


@st.cache_data(
    show_spinner=False,
    ttl=10,
)
def get_memory_connection_status() -> Any:
    return check_connection()


memory_connection = get_memory_connection_status()
supermemory_online = bool(memory_connection.online)
memory_status = memory_connection.label
memory_status_class = (
    "online"
    if supermemory_online
    else "fallback"
)

rows_for_memory = memory_rows(df)
current_memory_signature = memory_data_signature(
    rows_for_memory,
)

if (
    supermemory_online
    and st.session_state["memory_sync_attempted_signature"]
    != current_memory_signature
):
    st.session_state["memory_sync_attempted_signature"] = (
        current_memory_signature
    )

    sync_result = sync_observations(
        rows_for_memory,
    )

    if sync_result["failed"]:
        st.session_state["memory_sync_success"] = False
        st.session_state["memory_sync_message"] = (
            "The local record is available, but Supermemory accepted "
            f"{sync_result['accepted']} of "
            f"{sync_result['attempted']} observations during reconciliation."
        )
    else:
        st.session_state["memory_sync_success"] = True
        st.session_state["memory_sync_message"] = ""

before_episode_analysis = generate_before_episode_analysis(
    df,
)

thirty_day_brief = generate_thirty_day_brief(
    df,
)

clinician_summary = generate_clinician_preparation_summary(
    df,
)


# =============================================================================
# Styling
# =============================================================================

render(
    """
    <style>
        :root {
            color-scheme: light;

            --ink: #0b1016;
            --ink-soft: #2d3743;
            --muted: #667281;
            --faint: #9099a4;

            --white: #ffffff;
            --canvas: #f7f8fa;
            --canvas-blue: #f1f5f8;
            --canvas-green: #eff6f2;
            --dark: #0d131a;
            --dark-soft: #151e28;

            --border: #dde2e7;
            --border-dark: #293541;

            --blue: #315f82;
            --blue-dark: #1b3b53;
            --blue-light: #dbe9f2;

            --green: #2e7253;
            --green-light: #dceee4;

            --amber: #9b682a;

            --max-width: 1480px;
        }

        html {
            scroll-behavior: smooth;
        }

        html,
        body,
        .stApp,
        [data-testid="stAppViewContainer"],
        [data-testid="stMain"] {
            background: var(--white) !important;
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
            height: 0 !important;
            min-height: 0 !important;
            background: transparent !important;
        }

        [data-testid="stToolbar"],
        [data-testid="stDecoration"],
        [data-testid="stStatusWidget"],
        #MainMenu,
        footer {
            display: none !important;
        }

        .block-container {
            width: 100% !important;
            max-width: var(--max-width) !important;
            padding-top: 0 !important;
            padding-right: 3rem !important;
            padding-bottom: 5rem !important;
            padding-left: 3rem !important;
        }

        h1,
        h2,
        h3,
        h4,
        h5 {
            color: var(--ink) !important;
            letter-spacing: -0.045em;
        }

        h2 {
            font-size: 2.1rem !important;
        }

        h3 {
            font-size: 1.3rem !important;
        }

        hr {
            border: 0 !important;
            border-top: 1px solid var(--border) !important;
            margin: 5.5rem 0 !important;
        }

        a {
            text-decoration: none;
        }

        .site-nav {
            position: sticky;
            z-index: 100;
            top: 0;
            display: grid;
            grid-template-columns: auto 1fr auto;
            align-items: center;
            min-height: 76px;
            border-bottom: 1px solid rgba(221, 226, 231, 0.9);
            background: rgba(255, 255, 255, 0.93);
            backdrop-filter: blur(18px);
        }

        .site-brand {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            color: var(--ink);
            font-size: 0.96rem;
            font-weight: 720;
        }

        .site-mark {
            position: relative;
            width: 25px;
            height: 25px;
            border: 1.5px solid var(--ink);
            border-radius: 50%;
        }

        .site-mark::before {
            content: "";
            position: absolute;
            width: 8px;
            height: 8px;
            left: 7px;
            top: 7px;
            border-radius: 50%;
            background: var(--blue);
        }

        .site-mark::after {
            content: "";
            position: absolute;
            width: 4px;
            height: 4px;
            right: 2px;
            top: 2px;
            border-radius: 50%;
            background: var(--green);
        }

        .site-links {
            display: flex;
            justify-content: center;
            gap: 1.7rem;
        }

        .site-links a {
            color: var(--muted);
            font-size: 0.82rem;
            transition:
                color 160ms ease,
                transform 160ms ease;
        }

        .site-links a:hover {
            color: var(--ink);
            transform: translateY(-1px);
        }

        .nav-action {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-height: 38px;
            padding: 0 1rem;
            border-radius: 6px;
            background: var(--ink);
            color: var(--white);
            font-size: 0.79rem;
            font-weight: 650;
            transition:
                transform 160ms ease,
                background 160ms ease;
        }

        .nav-action:hover {
            background: var(--blue-dark);
            transform: translateY(-1px);
        }

        .hero {
            display: grid;
            grid-template-columns:
                minmax(0, 1.35fr)
                minmax(390px, 0.65fr);
            gap: 5rem;
            align-items: center;
            min-height: 760px;
            padding: 5.4rem 0 4.5rem 0;
        }

        .eyebrow {
            margin-bottom: 1.4rem;
            color: var(--blue);
            font-size: 0.72rem;
            font-weight: 760;
            letter-spacing: 0.135em;
            text-transform: uppercase;
        }

        .hero-title {
            max-width: 940px;
            margin: 0;
            color: var(--ink);
            font-size: clamp(4rem, 6.5vw, 7.15rem);
            font-weight: 690;
            line-height: 0.94;
            letter-spacing: -0.072em;
        }

        .hero-title span {
            color: var(--blue);
        }

        .hero-lead {
            max-width: 830px;
            margin: 2rem 0 0 0;
            color: var(--ink-soft);
            font-size: 1.22rem;
            line-height: 1.68;
        }

        .hero-support {
            max-width: 760px;
            margin-top: 1rem;
            color: var(--muted);
            font-size: 0.95rem;
            line-height: 1.72;
        }

        .hero-actions {
            display: flex;
            flex-wrap: wrap;
            gap: 0.8rem;
            margin-top: 2rem;
        }

        .button-primary,
        .button-secondary {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-height: 48px;
            padding: 0 1.25rem;
            border-radius: 7px;
            font-size: 0.86rem;
            font-weight: 650;
            transition:
                transform 160ms ease,
                box-shadow 160ms ease,
                border-color 160ms ease;
        }

        .button-primary {
            background: var(--ink);
            color: var(--white);
            box-shadow: 0 12px 30px rgba(11, 16, 22, 0.13);
        }

        .button-secondary {
            border: 1px solid var(--border);
            background: var(--white);
            color: var(--ink);
        }

        .button-primary:hover,
        .button-secondary:hover {
            transform: translateY(-2px);
        }

        .button-secondary:hover {
            border-color: var(--ink);
        }

        .proof-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.8rem 1.3rem;
            margin-top: 1.7rem;
            color: var(--muted);
            font-size: 0.82rem;
        }

        .proof-row span {
            display: flex;
            align-items: center;
            gap: 0.45rem;
        }

        .proof-row span::before {
            content: "";
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: var(--green);
        }

        .memory-visual {
            position: relative;
            min-height: 540px;
            overflow: hidden;
            border: 1px solid #202b36;
            border-radius: 25px;
            background:
                radial-gradient(
                    circle at 50% 46%,
                    rgba(61, 111, 148, 0.22),
                    transparent 30%
                ),
                var(--dark);
            box-shadow:
                0 38px 80px rgba(12, 20, 29, 0.18);
        }

        .memory-visual__header {
            position: relative;
            z-index: 5;
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin: 0 1.8rem;
            padding: 1.5rem 0 1rem 0;
            border-bottom: 1px solid var(--border-dark);
        }

        .memory-visual__label {
            color: #c3ccd5;
            font-size: 0.67rem;
            font-weight: 720;
            letter-spacing: 0.1em;
            text-transform: uppercase;
        }

        .memory-status {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            color: #d1dad4;
            font-size: 0.72rem;
        }

        .memory-status__dot {
            width: 7px;
            height: 7px;
            border-radius: 50%;
            background: #4bc081;
            box-shadow: 0 0 0 5px rgba(75, 192, 129, 0.08);
        }

        .memory-status--fallback .memory-status__dot {
            background: var(--amber);
            box-shadow: none;
        }

        .memory-ring {
            position: absolute;
            left: 50%;
            top: 49%;
            transform: translate(-50%, -50%);
            border: 1px solid rgba(120, 164, 194, 0.22);
            border-radius: 50%;
        }

        .memory-ring--one {
            width: 420px;
            height: 420px;
        }

        .memory-ring--two {
            width: 310px;
            height: 310px;
        }

        .memory-ring--three {
            width: 205px;
            height: 205px;
        }

        .memory-core {
            position: absolute;
            z-index: 3;
            left: 50%;
            top: 49%;
            display: flex;
            align-items: center;
            justify-content: center;
            width: 145px;
            height: 145px;
            transform: translate(-50%, -50%);
            border: 1px solid rgba(153, 191, 217, 0.75);
            border-radius: 50%;
            background:
                radial-gradient(
                    circle at 40% 30%,
                    rgba(101, 161, 201, 0.48),
                    rgba(37, 71, 97, 0.68) 43%,
                    rgba(14, 21, 29, 0.96) 78%
                );
            box-shadow:
                0 0 75px rgba(57, 112, 150, 0.32),
                inset 0 0 35px rgba(146, 190, 219, 0.15);
            color: #edf3f7;
            font-size: 0.67rem;
            font-weight: 720;
            line-height: 1.4;
            letter-spacing: 0.08em;
            text-align: center;
        }

        .memory-node {
            position: absolute;
            z-index: 4;
            padding: 0.48rem 0.62rem;
            border: 1px solid rgba(151, 179, 198, 0.22);
            border-radius: 4px;
            background: rgba(13, 20, 28, 0.86);
            color: #c7d1d9;
            font-family:
                "SFMono-Regular",
                Consolas,
                monospace;
            font-size: 0.6rem;
            letter-spacing: 0.04em;
        }

        .memory-node--speech {
            left: 6%;
            top: 31%;
        }

        .memory-node--routine {
            right: 5%;
            top: 29%;
        }

        .memory-node--medication {
            left: 5%;
            bottom: 24%;
        }

        .memory-node--episode {
            right: 6%;
            bottom: 24%;
        }

        .memory-node--visit {
            left: 50%;
            bottom: 12%;
            transform: translateX(-50%);
        }

        .memory-visual__stats {
            position: absolute;
            z-index: 5;
            right: 1.8rem;
            bottom: 1.5rem;
            left: 1.8rem;
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 0.8rem;
        }

        .memory-stat {
            padding-top: 0.8rem;
            border-top: 1px solid var(--border-dark);
        }

        .memory-stat__label {
            color: #7f8c98;
            font-size: 0.61rem;
            text-transform: uppercase;
        }

        .memory-stat__value {
            margin-top: 0.25rem;
            color: #edf3f7;
            font-size: 1.25rem;
            font-weight: 650;
        }

        .scope-bar {
            display: grid;
            grid-template-columns: 180px 1fr;
            gap: 2rem;
            padding: 1.4rem 0;
            border-top: 1px solid var(--border);
            border-bottom: 1px solid var(--border);
        }

        .scope-bar__label {
            color: var(--ink);
            font-size: 0.7rem;
            font-weight: 760;
            letter-spacing: 0.09em;
            text-transform: uppercase;
        }

        .scope-bar__copy {
            max-width: 930px;
            color: var(--muted);
            font-size: 0.91rem;
            line-height: 1.65;
        }

        .section-header {
            display: grid;
            grid-template-columns: 180px minmax(0, 1fr);
            gap: 2rem;
            margin-bottom: 3.2rem;
        }

        .section-index {
            padding-top: 0.55rem;
            color: var(--muted);
            font-family:
                "SFMono-Regular",
                Consolas,
                monospace;
            font-size: 0.7rem;
            letter-spacing: 0.04em;
        }

        .section-title {
            max-width: 1000px;
            margin: 0;
            color: var(--ink);
            font-size: clamp(2.5rem, 4vw, 4.2rem);
            font-weight: 660;
            line-height: 1.06;
            letter-spacing: -0.055em;
        }

        .section-description {
            max-width: 820px;
            margin: 1.2rem 0 0 0;
            color: var(--muted);
            font-size: 1rem;
            line-height: 1.72;
        }

        .problem-flow {
            display: grid;
            grid-template-columns:
                minmax(0, 1fr)
                74px
                minmax(0, 1fr)
                74px
                minmax(0, 1fr);
            border-top: 1px solid var(--border);
            border-bottom: 1px solid var(--border);
        }

        .problem-stage {
            min-height: 270px;
            padding: 2rem 1.5rem 2.2rem 0;
        }

        .problem-stage__number {
            margin-bottom: 2rem;
            color: var(--faint);
            font-family:
                "SFMono-Regular",
                Consolas,
                monospace;
            font-size: 0.66rem;
        }

        .problem-stage__title {
            margin-bottom: 0.7rem;
            color: var(--ink);
            font-size: 1.2rem;
            font-weight: 670;
        }

        .problem-stage__copy {
            color: var(--muted);
            font-size: 0.9rem;
            line-height: 1.65;
        }

        .problem-arrow {
            display: flex;
            align-items: center;
            justify-content: center;
            border-right: 1px solid var(--border);
            border-left: 1px solid var(--border);
            color: var(--blue);
            font-size: 1.45rem;
        }

        .solution-callout {
            margin-top: 1.5rem;
            padding: 2.5rem;
            border-radius: 18px;
            background: var(--canvas-blue);
        }

        .solution-callout__label {
            margin-bottom: 0.8rem;
            color: var(--blue);
            font-size: 0.69rem;
            font-weight: 760;
            letter-spacing: 0.1em;
            text-transform: uppercase;
        }

        .solution-callout__title {
            margin: 0;
            color: var(--blue-dark);
            font-size: 1.6rem;
            font-weight: 670;
        }

        .solution-callout__copy {
            max-width: 920px;
            margin-top: 0.8rem;
            color: #475968;
            font-size: 0.94rem;
            line-height: 1.68;
        }

        .capabilities {
            border-top: 1px solid var(--border);
        }

        .capability {
            display: grid;
            grid-template-columns: 120px 0.8fr 1.2fr;
            gap: 2.5rem;
            padding: 2.25rem 0;
            border-bottom: 1px solid var(--border);
            transition:
                padding-left 160ms ease,
                background 160ms ease;
        }

        .capability:hover {
            padding-left: 0.8rem;
            background: var(--canvas);
        }

        .capability__index {
            color: var(--faint);
            font-family:
                "SFMono-Regular",
                Consolas,
                monospace;
            font-size: 0.68rem;
        }

        .capability__title {
            color: var(--ink);
            font-size: 1.3rem;
            font-weight: 670;
        }

        .capability__copy {
            max-width: 740px;
            color: var(--muted);
            font-size: 0.92rem;
            line-height: 1.7;
        }

        .architecture-band {
            margin-right: calc(50% - 50vw);
            margin-left: calc(50% - 50vw);
            padding: 6rem max(3rem, calc((100vw - var(--max-width)) / 2 + 3rem));
            background: var(--dark);
            color: var(--white);
        }

        .architecture-band .section-title {
            color: var(--white);
        }

        .architecture-band .section-description,
        .architecture-band .section-index {
            color: #9ca9b5;
        }

        .architecture-grid {
            display: grid;
            grid-template-columns: 1.15fr 0.85fr;
            gap: 4rem;
            align-items: center;
        }

        .pipeline {
            overflow: hidden;
            border: 1px solid var(--border-dark);
            border-radius: 17px;
            background: var(--dark-soft);
        }

        .pipeline-step {
            display: grid;
            grid-template-columns: 95px 1fr;
            gap: 1.2rem;
            padding: 1.35rem 1.5rem;
            border-bottom: 1px solid var(--border-dark);
        }

        .pipeline-step:last-child {
            border-bottom: 0;
        }

        .pipeline-step__number {
            color: #738291;
            font-family:
                "SFMono-Regular",
                Consolas,
                monospace;
            font-size: 0.66rem;
        }

        .pipeline-step__title {
            margin-bottom: 0.3rem;
            color: #eff4f7;
            font-size: 0.94rem;
            font-weight: 650;
        }

        .pipeline-step__copy {
            color: #9ba8b4;
            font-size: 0.82rem;
            line-height: 1.6;
        }

        .architecture-proof {
            padding: 2rem;
            border: 1px solid var(--border-dark);
            border-radius: 17px;
            background: rgba(255, 255, 255, 0.025);
        }

        .architecture-proof__label {
            margin-bottom: 1rem;
            color: #7fa7c2;
            font-size: 0.7rem;
            font-weight: 730;
            letter-spacing: 0.1em;
            text-transform: uppercase;
        }

        .architecture-proof__title {
            margin: 0 0 1.1rem 0;
            color: #f0f4f7;
            font-size: 1.75rem;
            font-weight: 650;
        }

        .architecture-proof ul {
            margin: 0;
            padding: 0;
            list-style: none;
        }

        .architecture-proof li {
            position: relative;
            padding: 0.85rem 0 0.85rem 1.4rem;
            border-top: 1px solid var(--border-dark);
            color: #aab5bf;
            font-size: 0.88rem;
            line-height: 1.55;
        }

        .architecture-proof li::before {
            content: "";
            position: absolute;
            left: 0;
            top: 1.2rem;
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: #5ca77f;
        }

        .use-case-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 1rem;
        }

        .use-case {
            min-height: 330px;
            padding: 2rem;
            border: 1px solid var(--border);
            border-radius: 15px;
            background: var(--white);
            transition:
                transform 160ms ease,
                box-shadow 160ms ease;
        }

        .use-case:hover {
            transform: translateY(-4px);
            box-shadow: 0 20px 45px rgba(15, 24, 34, 0.08);
        }

        .use-case__index {
            margin-bottom: 3rem;
            color: var(--faint);
            font-family:
                "SFMono-Regular",
                Consolas,
                monospace;
            font-size: 0.68rem;
        }

        .use-case__title {
            margin-bottom: 0.8rem;
            color: var(--ink);
            font-size: 1.35rem;
            font-weight: 670;
        }

        .use-case__copy {
            color: var(--muted);
            font-size: 0.92rem;
            line-height: 1.7;
        }

        .audience-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1px;
            overflow: hidden;
            border: 1px solid var(--border);
            border-radius: 17px;
            background: var(--border);
        }

        .audience {
            min-height: 485px;
            padding: 2.6rem;
            background: var(--white);
        }

        .audience--clinical {
            background: var(--canvas);
        }

        .audience__label {
            margin-bottom: 1rem;
            color: var(--blue);
            font-size: 0.69rem;
            font-weight: 760;
            letter-spacing: 0.1em;
            text-transform: uppercase;
        }

        .audience__title {
            margin: 0 0 1.5rem 0;
            color: var(--ink);
            font-size: 2rem;
            font-weight: 660;
        }

        .audience ul {
            margin: 0;
            padding: 0;
            list-style: none;
        }

        .audience li {
            position: relative;
            padding: 1rem 0 1rem 1.8rem;
            border-top: 1px solid var(--border);
            color: var(--ink-soft);
            font-size: 0.92rem;
            line-height: 1.55;
        }

        .audience li::before {
            content: "";
            position: absolute;
            left: 0;
            top: 1.35rem;
            width: 7px;
            height: 7px;
            border-radius: 50%;
            background: var(--blue);
        }

        .metric-strip {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            margin-bottom: 2.5rem;
            border-top: 1px solid var(--border);
            border-bottom: 1px solid var(--border);
        }

        .metric {
            padding: 1.5rem 1.6rem 1.7rem 0;
        }

        .metric + .metric {
            padding-left: 1.6rem;
            border-left: 1px solid var(--border);
        }

        .metric__label {
            color: var(--muted);
            font-size: 0.74rem;
        }

        .metric__value {
            margin-top: 0.45rem;
            color: var(--ink);
            font-size: 2.4rem;
            font-weight: 670;
            letter-spacing: -0.05em;
        }

        .console-shell {
            overflow: hidden;
            border: 1px solid var(--border);
            border-radius: 13px;
            box-shadow: 0 28px 60px rgba(15, 23, 32, 0.08);
        }

        .console-bar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 1rem 1.2rem;
            background: var(--dark);
            color: var(--white);
        }

        .console-bar__title {
            color: var(--white);
            font-size: 0.76rem;
            font-weight: 680;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }

        .console-bar__status {
            color: #aab5be;
            font-size: 0.7rem;
        }

        .retrieval-heading {
            margin: 1.3rem 0 0.7rem 0;
            color: var(--ink);
            font-size: 0.8rem;
            font-weight: 680;
        }

        .memory-result {
            margin-bottom: 0.7rem;
            overflow: hidden;
            border: 1px solid var(--border);
            border-radius: 7px;
            background: var(--white);
        }

        .memory-result__header {
            display: flex;
            justify-content: space-between;
            padding: 0.65rem 0.8rem;
            border-bottom: 1px solid var(--border);
            background: var(--canvas);
            color: var(--blue);
            font-size: 0.68rem;
            font-weight: 660;
        }

        .memory-result__content {
            padding: 0.9rem;
            color: var(--ink-soft);
            font-size: 0.88rem;
            line-height: 1.65;
        }

        .report-grid {
            display: grid;
            grid-template-columns: 0.82fr 1.18fr;
            gap: 1rem;
        }

        .report {
            height: 100%;
            overflow: hidden;
            border: 1px solid var(--border);
            border-radius: 14px;
            background: var(--white);
        }

        .report__header {
            padding: 1.3rem 1.4rem;
            border-bottom: 1px solid var(--border);
            background: var(--canvas);
        }

        .report__eyebrow {
            margin-bottom: 0.45rem;
            color: var(--blue);
            font-size: 0.67rem;
            font-weight: 730;
            letter-spacing: 0.09em;
            text-transform: uppercase;
        }

        .report__title {
            color: var(--ink);
            font-size: 1.25rem;
            font-weight: 670;
        }

        .report__body {
            padding: 1.4rem;
        }

        .report-period {
            display: grid;
            grid-template-columns: 1fr auto;
            gap: 1rem;
            padding-bottom: 1rem;
            border-bottom: 1px solid var(--border);
        }

        .report-period__label {
            color: var(--muted);
            font-size: 0.76rem;
        }

        .report-period__value {
            color: var(--ink);
            font-size: 0.82rem;
            font-weight: 630;
        }

        .report-stat-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 0.7rem;
            margin-top: 1rem;
        }

        .report-stat {
            padding: 0.85rem;
            border-radius: 7px;
            background: var(--canvas);
        }

        .report-stat__label {
            color: var(--muted);
            font-size: 0.68rem;
        }

        .report-stat__value {
            margin-top: 0.2rem;
            color: var(--ink);
            font-size: 1.3rem;
            font-weight: 660;
        }

        .report-list {
            margin-top: 1.1rem;
        }

        .report-list__heading {
            margin-bottom: 0.6rem;
            color: var(--ink);
            font-size: 0.8rem;
            font-weight: 660;
        }

        .report-list__item {
            padding: 0.7rem 0;
            border-top: 1px solid var(--border);
            color: var(--ink-soft);
            font-size: 0.79rem;
            line-height: 1.55;
        }

        .limitations-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 2rem;
        }

        .limitation {
            padding-top: 1rem;
            border-top: 1px solid var(--border);
        }

        .limitation__title {
            margin-bottom: 0.55rem;
            color: var(--ink);
            font-size: 0.9rem;
            font-weight: 670;
        }

        .limitation__copy {
            color: var(--muted);
            font-size: 0.84rem;
            line-height: 1.65;
        }

        .closing-band {
            margin-top: 6rem;
            margin-right: calc(50% - 50vw);
            margin-left: calc(50% - 50vw);
            padding: 6rem max(3rem, calc((100vw - var(--max-width)) / 2 + 3rem));
            background: var(--dark);
            color: var(--white);
        }

        .closing-band__grid {
            display: grid;
            grid-template-columns: 1.25fr 0.75fr;
            gap: 4rem;
            align-items: end;
        }

        .closing-band__eyebrow {
            margin-bottom: 1.2rem;
            color: #7ea6c1;
            font-size: 0.7rem;
            font-weight: 730;
            letter-spacing: 0.1em;
            text-transform: uppercase;
        }

        .closing-band__title {
            max-width: 920px;
            margin: 0;
            color: var(--white);
            font-size: clamp(3rem, 5vw, 5.6rem);
            font-weight: 660;
            line-height: 1;
            letter-spacing: -0.06em;
        }

        .closing-band__copy {
            margin-top: 1.3rem;
            max-width: 750px;
            color: #a9b4be;
            font-size: 0.96rem;
            line-height: 1.7;
        }

        .closing-band__actions {
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
        }

        .closing-action {
            display: flex;
            align-items: center;
            justify-content: space-between;
            min-height: 54px;
            padding: 0 1rem;
            border: 1px solid var(--border-dark);
            border-radius: 7px;
            color: #eaf0f4;
            font-size: 0.84rem;
            transition:
                background 160ms ease,
                transform 160ms ease;
        }

        .closing-action:hover {
            background: var(--dark-soft);
            transform: translateX(3px);
        }

        .site-footer {
            display: grid;
            grid-template-columns: 1fr auto;
            gap: 2rem;
            padding: 2rem 0;
            color: var(--muted);
            font-size: 0.78rem;
            line-height: 1.65;
        }

        [data-testid="stForm"] {
            padding: 1.2rem !important;
            border: 1px solid var(--border) !important;
            border-radius: 8px !important;
            background: var(--canvas) !important;
        }

        [data-testid="stExpander"] {
            border: 1px solid var(--border) !important;
            border-radius: 8px !important;
            background: var(--white) !important;
        }

        [data-testid="stExpander"] summary {
            color: var(--ink) !important;
            font-weight: 630 !important;
        }

        [data-baseweb="input"],
        [data-baseweb="textarea"],
        [data-baseweb="select"] > div {
            background: var(--white) !important;
            border-color: #cdd4da !important;
            border-radius: 6px !important;
            color: var(--ink) !important;
            box-shadow: none !important;
        }

        [data-baseweb="input"] input,
        [data-baseweb="textarea"] textarea {
            color: var(--ink) !important;
            background: var(--white) !important;
        }

        [data-baseweb="select"] * {
            color: var(--ink) !important;
        }

        .stButton > button,
        .stDownloadButton > button,
        [data-testid="stFormSubmitButton"] > button {
            min-height: 2.7rem !important;
            border: 1px solid #cbd2d8 !important;
            border-radius: 6px !important;
            background: var(--white) !important;
            color: var(--ink) !important;
            font-weight: 620 !important;
            box-shadow: none !important;
            transition:
                border-color 160ms ease,
                transform 160ms ease !important;
        }

        .stButton > button:hover,
        .stDownloadButton > button:hover,
        [data-testid="stFormSubmitButton"] > button:hover {
            border-color: var(--ink) !important;
            transform: translateY(-1px);
        }

        [data-testid="stDataFrame"] {
            border: 1px solid var(--border) !important;
            border-radius: 8px !important;
            overflow: hidden;
        }

        [data-testid="stAlert"] {
            border-radius: 7px !important;
            box-shadow: none !important;
        }

        @media (max-width: 1100px) {
            .hero,
            .architecture-grid,
            .closing-band__grid {
                grid-template-columns: 1fr;
            }

            .use-case-grid,
            .limitations-grid {
                grid-template-columns: 1fr;
            }

            .report-grid {
                grid-template-columns: 1fr;
            }

            .audience-grid {
                grid-template-columns: 1fr;
            }

            .capability {
                grid-template-columns: 90px 1fr;
            }

            .capability__copy {
                grid-column: 2;
            }

            .site-links {
                display: none;
            }
        }

        @media (max-width: 760px) {
            .block-container {
                padding-right: 1.2rem !important;
                padding-left: 1.2rem !important;
            }

            .site-nav {
                grid-template-columns: 1fr auto;
            }

            .hero {
                min-height: auto;
                padding: 4rem 0;
            }

            .hero-title {
                font-size: 3.65rem;
            }

            .section-header,
            .scope-bar {
                grid-template-columns: 1fr;
                gap: 0.6rem;
            }

            .problem-flow {
                grid-template-columns: 1fr;
            }

            .problem-arrow {
                min-height: 55px;
                border-right: 0;
                border-left: 0;
                border-top: 1px solid var(--border);
                border-bottom: 1px solid var(--border);
                transform: rotate(90deg);
            }

            .capability {
                grid-template-columns: 1fr;
                gap: 0.55rem;
            }

            .capability__copy {
                grid-column: auto;
            }

            .metric-strip {
                grid-template-columns: 1fr;
            }

            .metric + .metric {
                padding-left: 0;
                border-top: 1px solid var(--border);
                border-left: 0;
            }

            .site-footer {
                grid-template-columns: 1fr;
            }
        }
        /* ================================================================
        Final presentation corrections
        ================================================================ */

.answer-card {
    display: block !important;
    margin: 0.5rem 0 1.6rem 0 !important;
    overflow: hidden !important;
    border: 1px solid var(--border) !important;
    border-radius: 12px !important;
    background: var(--white) !important;
    box-shadow: 0 18px 42px rgba(15, 24, 34, 0.08) !important;
}

.answer-card__header {
    display: flex !important;
    align-items: flex-start !important;
    justify-content: space-between !important;
    gap: 1rem !important;
    padding: 1.15rem 1.2rem !important;
    border-bottom: 1px solid var(--border) !important;
    background: var(--canvas-blue) !important;
}

.answer-card__eyebrow {
    margin-bottom: 0.35rem !important;
    color: var(--blue) !important;
    font-size: 0.65rem !important;
    font-weight: 760 !important;
    letter-spacing: 0.1em !important;
    text-transform: uppercase !important;
}

.answer-card__title {
    color: var(--ink) !important;
    font-size: 1.08rem !important;
    font-weight: 680 !important;
    line-height: 1.35 !important;
}

.answer-card__count {
    flex: 0 0 auto !important;
    padding: 0.35rem 0.58rem !important;
    border: 1px solid var(--border) !important;
    border-radius: 999px !important;
    background: var(--white) !important;
    color: var(--muted) !important;
    font-size: 0.68rem !important;
    font-weight: 630 !important;
}

.answer-card__body {
    padding: 1.2rem !important;
}

.answer-card__answer {
    color: var(--ink-soft) !important;
    font-size: 0.94rem !important;
    line-height: 1.72 !important;
}

.answer-meta {
    display: grid !important;
    grid-template-columns: 1fr !important;
    margin-top: 1rem !important;
    padding: 0.8rem 0 !important;
    border-top: 1px solid var(--border) !important;
    border-bottom: 1px solid var(--border) !important;
}

.answer-meta div {
    display: flex !important;
    justify-content: space-between !important;
    gap: 1rem !important;
    font-size: 0.72rem !important;
}

.answer-meta span {
    color: var(--muted) !important;
}

.answer-meta strong {
    color: var(--ink) !important;
    font-weight: 650 !important;
}

.answer-evidence {
    margin-top: 1rem !important;
}

.answer-evidence__heading {
    margin-bottom: 0.4rem !important;
    color: var(--ink) !important;
    font-size: 0.76rem !important;
    font-weight: 680 !important;
}

.answer-evidence__item {
    padding: 0.68rem 0 !important;
    border-top: 1px solid var(--border) !important;
    color: var(--ink-soft) !important;
    font-size: 0.76rem !important;
    line-height: 1.55 !important;
}

.answer-boundary {
    margin-top: 1rem !important;
    padding: 0.85rem !important;
    border-radius: 7px !important;
    background: var(--canvas) !important;
    color: var(--muted) !important;
    font-size: 0.72rem !important;
    line-height: 1.55 !important;
}

/* Give the continuity stages room around their dividing lines */

.problem-stage {
    min-height: 285px !important;
    padding: 2.35rem 2rem 2.5rem 2rem !important;
}

.problem-stage:first-child {
    padding-left: 0 !important;
}

.problem-arrow {
    min-width: 80px !important;
}

.problem-stage__number {
    margin-bottom: 2.35rem !important;
}

.problem-stage__title {
    margin-bottom: 0.9rem !important;
}

.problem-stage__copy {
    max-width: 390px !important;
    line-height: 1.72 !important;
}

/* Improve spacing inside the longitudinal-memory callout */

.solution-callout {
    margin-top: 1.8rem !important;
    padding: 2.8rem 2.6rem !important;
}

.solution-callout__label {
    margin-bottom: 1rem !important;
}

.solution-callout__title {
    margin-bottom: 0.9rem !important;
}

.solution-callout__copy {
    max-width: 980px !important;
    line-height: 1.75 !important;
}

/* Prevent the clinical-visit node from overlapping the statistics */

.memory-visual {
    min-height: 590px !important;
}

.memory-node--visit {
    bottom: 27% !important;
}

.memory-visual__stats {
    bottom: 1.45rem !important;
    padding-top: 0.35rem !important;
}

.memory-stat {
    min-height: 76px !important;
    padding-top: 0.9rem !important;
}

.memory-stat__label {
    margin-bottom: 0.3rem !important;
}
.architecture-band .section-title,
.architecture-proof__title {
    color: #f4f7f9 !important;
}

.architecture-band .section-description,
.architecture-band .section-index,
.architecture-proof li {
    color: #aeb9c4 !important;
}
    </style>
    """
)


# =============================================================================
# Navigation
# =============================================================================

render(
    """
    <nav class="site-nav">
        <a class="site-brand" href="#top">
            <span class="site-mark"></span>
            <span>NeuroBlackBox</span>
        </a>

        <div class="site-links">
            <a href="#problem">Problem</a>
            <a href="#system">System</a>
            <a href="#architecture">Architecture</a>
            <a href="#prototype">Prototype</a>
            <a href="#safety">Safety</a>
        </div>

        <a class="nav-action" href="#prototype">
            Open prototype
        </a>
    </nav>
    """
)


# =============================================================================
# Hero
# =============================================================================

render(
    f"""
    <div id="top"></div>

    <header class="hero">
        <div>
            <div class="eyebrow">
                Cognitive care loses context between appointments
            </div>

            <h1 class="hero-title">
                Care does not end when the
                <span>appointment does.</span>
            </h1>

            <p class="hero-lead">
                NeuroBlackBox creates a continuous memory of recorded changes,
                routines, interventions, improvements, caregiver observations,
                and clinical conversations.
            </p>

            <p class="hero-support">
                Families no longer have to reconstruct weeks of cognitive
                change from memory. Clinicians receive a structured,
                source-grounded interval history instead of tracing every
                observation from the beginning.
            </p>

            <div class="hero-actions">
                <a class="button-primary" href="#prototype">
                    View the live prototype
                </a>

                <a class="button-secondary" href="#architecture">
                    Explore the memory architecture
                </a>
            </div>

            <div class="proof-row">
                <span>Local-first memory</span>
                <span>Source-grounded retrieval</span>
                <span>Longitudinal history</span>
                <span>Clinician-preparation summaries</span>
            </div>
        </div>

        <aside class="memory-visual">
            <div class="memory-visual__header">
                <div class="memory-visual__label">
                    Live longitudinal memory
                </div>

                <div class="memory-status memory-status--{escape(memory_status_class)}">
                    <span class="memory-status__dot"></span>
                    <span>Supermemory {escape(memory_status)}</span>
                </div>
            </div>

            <div class="memory-ring memory-ring--one"></div>
            <div class="memory-ring memory-ring--two"></div>
            <div class="memory-ring memory-ring--three"></div>

            <div class="memory-core">
                LONGITUDINAL<br>
                MEMORY
            </div>

            <div class="memory-node memory-node--speech">
                SPEECH
            </div>

            <div class="memory-node memory-node--routine">
                ROUTINE
            </div>

            <div class="memory-node memory-node--medication">
                MEDICATION
            </div>

            <div class="memory-node memory-node--episode">
                EPISODE
            </div>

            <div class="memory-node memory-node--visit">
                CLINICAL VISIT
            </div>

            <div class="memory-visual__stats">
                <div class="memory-stat">
                    <div class="memory-stat__label">
                        Records
                    </div>
                    <div class="memory-stat__value">
                        {metrics["total"]}
                    </div>
                </div>

                <div class="memory-stat">
                    <div class="memory-stat__label">
                        High severity
                    </div>
                    <div class="memory-stat__value">
                        {metrics["high"]}
                    </div>
                </div>

                <div class="memory-stat">
                    <div class="memory-stat__label">
                        Storage
                    </div>
                    <div class="memory-stat__value">
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
    <div class="scope-bar">
        <div class="scope-bar__label">
            Clinical boundary
        </div>

        <div class="scope-bar__copy">
            NeuroBlackBox preserves caregiver-reported observations and
            supports preparation for clinical review. It does not diagnose,
            screen, predict, or treat Alzheimer's disease, dementia, or any
            other medical condition. It does not replace a clinician or an
            official medical record.
        </div>
    </div>
    """
)

st.divider()


# =============================================================================
# Problem section
# =============================================================================

render(
    """
    <section id="problem">
        <div class="section-header">
            <div class="section-index">
                01 / CONTINUITY GAP
            </div>

            <div>
                <h2 class="section-title">
                    Critical information disappears between daily life
                    and clinical care.
                </h2>

                <p class="section-description">
                    Patients and families may not remember every observation,
                    improvement, recommendation, medication effect, or
                    contextual change from one appointment to the next.
                    Clinicians must then reconstruct a longitudinal history
                    from fragmented recollection.
                </p>
            </div>
        </div>

        <div class="problem-flow">
            <article class="problem-stage">
                <div class="problem-stage__number">
                    01
                </div>

                <div class="problem-stage__title">
                    Daily life
                </div>

                <div class="problem-stage__copy">
                    Speech pauses, repeated questions, medication changes,
                    disrupted routines, navigation issues, and improvements
                    occur outside the clinic.
                </div>
            </article>

            <div class="problem-arrow">
                →
            </div>

            <article class="problem-stage">
                <div class="problem-stage__number">
                    02
                </div>

                <div class="problem-stage__title">
                    Clinical visit
                </div>

                <div class="problem-stage__copy">
                    A short appointment compresses weeks or months of lived
                    experience into one retrospective conversation.
                </div>
            </article>

            <div class="problem-arrow">
                →
            </div>

            <article class="problem-stage">
                <div class="problem-stage__number">
                    03
                </div>

                <div class="problem-stage__title">
                    Follow-up
                </div>

                <div class="problem-stage__copy">
                    Families may forget recommendations, struggle to assess
                    progress, or return without a structured interval history.
                </div>
            </article>
        </div>

        <div class="solution-callout">
            <div class="solution-callout__label">
                NeuroBlackBox memory layer
            </div>

            <h3 class="solution-callout__title">
                A persistent record across the complete care interval.
            </h3>

            <p class="solution-callout__copy">
                The system connects caregiver observations, prior visit
                context, intervention history, recorded change over time, and
                clinician-preparation outputs through a searchable local
                memory layer.
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
    <section id="system">
        <div class="section-header">
            <div class="section-index">
                02 / PRODUCT SYSTEM
            </div>

            <div>
                <h2 class="section-title">
                    From isolated observations to a longitudinal care record.
                </h2>

                <p class="section-description">
                    NeuroBlackBox is organized around five continuous
                    operations: capture, remember, connect, retrieve,
                    and prepare.
                </p>
            </div>
        </div>

        <div class="capabilities">
            <article class="capability">
                <div class="capability__index">
                    01 / CAPTURE
                </div>

                <div class="capability__title">
                    Record what happened.
                </div>

                <div class="capability__copy">
                    Store dated observations covering recorded changes, routines,
                    medication, navigation, significant episodes,
                    contextual changes, interventions, and improvements.
                </div>
            </article>

            <article class="capability">
                <div class="capability__index">
                    02 / REMEMBER
                </div>

                <div class="capability__title">
                    Preserve context locally.
                </div>

                <div class="capability__copy">
                    Write every observation to an inspectable local record
                    and a semantic memory layer powered by Supermemory Local.
                </div>
            </article>

            <article class="capability">
                <div class="capability__index">
                    03 / CONNECT
                </div>

                <div class="capability__title">
                    Relate events across time.
                </div>

                <div class="capability__copy">
                    Connect new observations with previous observations,
                    appointments, recommendations, interventions,
                    medication changes, and outcomes.
                </div>
            </article>

            <article class="capability">
                <div class="capability__index">
                    04 / RETRIEVE
                </div>

                <div class="capability__title">
                    Ask the complete history.
                </div>

                <div class="capability__copy">
                    Retrieve source-grounded records with questions such as
                    “What changed after the last appointment?” or “What was
                    observed before the latest episode?”
                </div>
            </article>

            <article class="capability">
                <div class="capability__index">
                    05 / PREPARE
                </div>

                <div class="capability__title">
                    Enter the next visit prepared.
                </div>

                <div class="capability__copy">
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
# Architecture band
# =============================================================================

render(
    """
    <section id="architecture" class="architecture-band">
        <div class="section-header">
            <div class="section-index">
                03 / SUPERMEMORY ARCHITECTURE
            </div>

            <div>
                <h2 class="section-title">
                    Built on a persistent local memory layer.
                </h2>

                <p class="section-description">
                    Supermemory Local provides the semantic persistence and
                    retrieval layer that connects observations across sessions
                    without treating the system as a diagnostic engine.
                </p>
            </div>
        </div>

        <div class="architecture-grid">
            <div class="pipeline">
                <article class="pipeline-step">
                    <div class="pipeline-step__number">
                        01 / INPUT
                    </div>

                    <div>
                        <div class="pipeline-step__title">
                            Caregiver observation
                        </div>

                        <div class="pipeline-step__copy">
                            Dated source records describe observed changes, routines,
                            episodes, interventions, appointments, and outcomes.
                        </div>
                    </div>
                </article>

                <article class="pipeline-step">
                    <div class="pipeline-step__number">
                        02 / RECORD
                    </div>

                    <div>
                        <div class="pipeline-step__title">
                            Structured local persistence
                        </div>

                        <div class="pipeline-step__copy">
                            An inspectable CSV record provides transparent
                            persistence and deterministic fallback.
                        </div>
                    </div>
                </article>

                <article class="pipeline-step">
                    <div class="pipeline-step__number">
                        03 / MEMORY
                    </div>

                    <div>
                        <div class="pipeline-step__title">
                            Supermemory semantic storage
                        </div>

                        <div class="pipeline-step__copy">
                            Observations remain retrievable across sessions
                            through a local semantic memory container.
                        </div>
                    </div>
                </article>

                <article class="pipeline-step">
                    <div class="pipeline-step__number">
                        04 / RETRIEVE
                    </div>

                    <div>
                        <div class="pipeline-step__title">
                            Question-conditioned recall
                        </div>

                        <div class="pipeline-step__copy">
                            Natural-language questions retrieve related
                            source observations from the longitudinal record.
                        </div>
                    </div>
                </article>

                <article class="pipeline-step">
                    <div class="pipeline-step__number">
                        05 / OUTPUT
                    </div>

                    <div>
                        <div class="pipeline-step__title">
                            Clinician-preparation documents
                        </div>

                        <div class="pipeline-step__copy">
                            Source-grounded summaries organize the interval
                            history without assigning diagnosis or risk.
                        </div>
                    </div>
                </article>
            </div>

            <aside class="architecture-proof">
                <div class="architecture-proof__label">
                    Why Supermemory matters
                </div>

                <h3 class="architecture-proof__title">
                    Memory that persists beyond a single interaction.
                </h3>

                <ul>
                    <li>
                        Remembers observations across separate sessions.
                    </li>
                    <li>
                        Retrieves semantically related events and context.
                    </li>
                    <li>
                        Preserves source records for human inspection.
                    </li>
                    <li>
                        Supports questions across a longitudinal history.
                    </li>
                    <li>
                        Runs locally for privacy-sensitive workflows.
                    </li>
                </ul>
            </aside>
        </div>
    </section>
    """
)

st.divider()


# =============================================================================
# Use cases
# =============================================================================

render(
    """
    <section>
        <div class="section-header">
            <div class="section-index">
                04 / CARE CONTINUITY
            </div>

            <div>
                <h2 class="section-title">
                    Useful at every point between appointments.
                </h2>

                <p class="section-description">
                    The system supports the real information workflow across
                    daily observation, follow-up preparation, and clinical review.
                </p>
            </div>
        </div>

        <div class="use-case-grid">
            <article class="use-case">
                <div class="use-case__index">
                    01 / BETWEEN APPOINTMENTS
                </div>

                <div class="use-case__title">
                    Capture changes while they are still specific.
                </div>

                <div class="use-case__copy">
                    A caregiver records changes as they occur instead of trying
                    to reconstruct several weeks of observations immediately before
                    an appointment.
                </div>
            </article>

            <article class="use-case">
                <div class="use-case__index">
                    02 / BEFORE FOLLOW-UP
                </div>

                <div class="use-case__title">
                    Review what changed since the previous visit.
                </div>

                <div class="use-case__copy">
                    The family retrieves observations related to speech,
                    repetition, medication, routines, episodes, and improvement,
                    then prepares concrete discussion questions.
                </div>
            </article>

            <article class="use-case">
                <div class="use-case__index">
                    03 / CLINICAL REVIEW
                </div>

                <div class="use-case__title">
                    Begin with context instead of reconstruction.
                </div>

                <div class="use-case__copy">
                    A clinician can review a structured interval history and
                    source observations without repeating the entire observation
                    traceback from the beginning.
                </div>
            </article>
        </div>
    </section>
    """
)

st.divider()


# =============================================================================
# Shared value
# =============================================================================

render(
    """
    <section>
        <div class="section-header">
            <div class="section-index">
                05 / SHARED CONTEXT
            </div>

            <div>
                <h2 class="section-title">
                    One longitudinal record for families, caregivers,
                    and clinicians.
                </h2>

                <p class="section-description">
                    The prototype supports continuity of information without
                    positioning itself as a diagnostic system or a replacement
                    for formal clinical documentation.
                </p>
            </div>
        </div>

        <div class="audience-grid">
            <article class="audience">
                <div class="audience__label">
                    Families and caregivers
                </div>

                <h3 class="audience__title">
                    Preserve the details that memory loses.
                </h3>

                <ul>
                    <li>
                        Record subtle changes before they become vague recall.
                    </li>
                    <li>
                        Track improvements, recurring observations, and contextual changes.
                    </li>
                    <li>
                        Recall previous recommendations and visit context.
                    </li>
                    <li>
                        Prepare concrete questions before the next appointment.
                    </li>
                    <li>
                        Maintain continuity when several relatives provide care.
                    </li>
                </ul>
            </article>

            <article class="audience audience--clinical">
                <div class="audience__label">
                    Clinician preparation
                </div>

                <h3 class="audience__title">
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
                        Review context around medication and interventions.
                    </li>
                    <li>
                        Reduce repeated reconstruction of patient history.
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
    <section id="prototype">
        <div class="section-header">
            <div class="section-index">
                06 / WORKING PROTOTYPE
            </div>

            <div>
                <h2 class="section-title">
                    Search, record, reconstruct, and prepare.
                </h2>

                <p class="section-description">
                    The operational console demonstrates the complete
                    Supermemory-powered local workflow using the current
                    caregiver observation record.
                </p>
            </div>
        </div>
    </section>
    """
)

render(
    f"""
    <div class="metric-strip">
        <div class="metric">
            <div class="metric__label">
                Total observations
            </div>
            <div class="metric__value">
                {metrics["total"]}
            </div>
        </div>

        <div class="metric">
            <div class="metric__label">
                Speech records
            </div>
            <div class="metric__value">
                {metrics["speech"]}
            </div>
        </div>

        <div class="metric">
            <div class="metric__label">
                Repetition records
            </div>
            <div class="metric__value">
                {metrics["repetition"]}
            </div>
        </div>

        <div class="metric">
            <div class="metric__label">
                High-severity records
            </div>
            <div class="metric__value">
                {metrics["high"]}
            </div>
        </div>
    </div>

    <div class="console-shell">
        <div class="console-bar">
            <div class="console-bar__title">
                NeuroBlackBox Memory Console
            </div>

            <div class="console-bar__status">
                Supermemory: {escape(memory_status)}
            </div>
        </div>
    </div>
    """
)

if st.session_state["memory_sync_message"]:
    st.warning(
        st.session_state["memory_sync_message"]
    )

if st.session_state["last_save_message"]:
    if st.session_state["last_save_success"]:
        st.success(
            st.session_state["last_save_message"]
        )
    else:
        st.warning(
            st.session_state["last_save_message"]
        )

console_left, console_right = st.columns(
    [
        0.82,
        1.18,
    ],
    gap="large",
)

with console_left:
    st.markdown(
        "### Search the longitudinal record"
    )

    preset_one, preset_two = st.columns(
        2,
    )

    with preset_one:
        st.button(
            "Changes since last visit",
            width="stretch",
            on_click=set_query,
            args=(
                "What changed after the previous appointment?",
            ),
        )

        st.button(
            "Repetition patterns",
            width="stretch",
            on_click=set_query,
            args=(
                "How have repeated questions changed?",
            ),
        )

    with preset_two:
        st.button(
            "Speech and pauses",
            width="stretch",
            on_click=set_query,
            args=(
                "What speech pauses or word-finding changes were recorded?",
            ),
        )

        st.button(
            "Before latest episode",
            width="stretch",
            on_click=set_query,
            args=(
                "What was observed before the latest high-severity episode?",
            ),
        )

    question = st.text_input(
        "Ask the memory record",
        key="query",
        placeholder=(
            "Example: What changed after the previous appointment?"
        ),
    )

    if question.strip():
        grounded_answer = generate_grounded_answer(
            df,
            question,
        )

        display_grounded_answer(
            grounded_answer,
        )

        semantic_results = []

        if supermemory_online:
            with st.spinner(
                "Retrieving supporting source observations..."
            ):
                semantic_results = search_observations(
                    question,
                    limit=5,
                )

        semantic_used = display_memory_results(
            semantic_results,
        )

        if not semantic_used:
            if supermemory_online:
                st.caption(
                    "Semantic retrieval returned no matching records. "
                    "Displaying deterministic local fallback."
                )
            else:
                st.caption(
                    "Supermemory Local is unavailable. "
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
                        <article class="memory-result">
                            <div class="memory-result__header">
                                <span>
                                    Local source observation
                                </span>

                                <span>
                                    {escape(row["date"].strftime("%b %d, %Y"))}
                                </span>
                            </div>

                            <div class="memory-result__content">
                                <strong>
                                    {escape(row["type"])}
                                    ·
                                    {escape(row["severity"])}
                                </strong>

                                <br><br>

                                {escape(row["observation"])}
                            </div>
                        </article>
                        """
                    )

    with st.expander(
        "Add a new source observation",
        expanded=False,
    ):
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
                width="stretch",
            )

        if submitted:
            cleaned_observation = (
                observation.strip()
            )

            cleaned_source = (
                source.strip()
                or "caregiver"
            )

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
                            "date": pd.to_datetime(
                                observation_date,
                            ),
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

                normalized_updated_df = normalize_observation_frame(
                    updated_df,
                )
                observation_already_present = (
                    len(normalized_updated_df) == len(df)
                )

                save_data(
                    normalized_updated_df,
                )

                stored_in_memory = False

                if supermemory_online:
                    stored_in_memory = store_observation(
                        memory_row,
                    )

                if stored_in_memory:
                    st.session_state["last_save_success"] = True

                    if observation_already_present:
                        st.session_state["last_save_message"] = (
                            "This exact observation was already in the local "
                            "record. Its Supermemory record was confirmed."
                        )
                    else:
                        st.session_state["last_save_message"] = (
                            "Observation saved to the local record "
                            "and submitted to Supermemory Local."
                        )
                else:
                    st.session_state["last_save_success"] = (
                        observation_already_present
                    )

                    if observation_already_present:
                        st.session_state["last_save_message"] = (
                            "This exact observation was already in the local "
                            "record, so no duplicate was created."
                        )
                    elif supermemory_online:
                        st.session_state["last_save_message"] = (
                            "Observation saved to the local record. "
                            "The Supermemory Local write was not confirmed."
                        )
                    else:
                        st.session_state["last_save_message"] = (
                            "Observation saved to the local record. "
                            "Supermemory is in Local fallback and will be "
                            "reconciled after a verified connection."
                        )

                st.rerun()

with console_right:
    st.markdown(
        "### Before-episode reconstruction"
    )

    render(
        f"""
        <article class="report">
            <div class="report__header">
                <div class="report__eyebrow">
                    Source-grounded reconstruction
                </div>

                <div class="report__title">
                    Context preceding the latest high-severity episode
                </div>
            </div>

            <div class="report__body">
                <div class="report-list">
                    {
                        "".join(
                            f'<div class="report-list__item">{escape(line)}</div>'
                            for line in before_episode_analysis.splitlines()
                            if line.strip()
                        )
                    }
                </div>
            </div>
        </article>
        """
    )

    st.markdown(
        "### Source observation table"
    )

    if df.empty:
        st.info(
            "No observations are currently available."
        )
    else:
        timeline = df.copy()

        timeline["date"] = (
            timeline["date"]
            .dt.strftime("%Y-%m-%d")
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
            width="stretch",
            hide_index=True,
            height=390,
        )

st.divider()


# =============================================================================
# Review documents
# =============================================================================

recent_window = thirty_day_window(
    df,
)

recent_metrics = analyze_observations(
    recent_window,
)

high_records = df[
    df["severity"] == "high"
].sort_values(
    "date",
)

recent_records = df.sort_values(
    "date",
).tail(
    4,
)

review_start = (
    recent_window["date"].min().strftime("%b %d, %Y")
    if not recent_window.empty
    else "No data"
)

review_end = (
    recent_window["date"].max().strftime("%b %d, %Y")
    if not recent_window.empty
    else "No data"
)

render(
    """
    <section>
        <div class="section-header">
            <div class="section-index">
                07 / REVIEW DOCUMENTS
            </div>

            <div>
                <h2 class="section-title">
                    Structured outputs for the next clinical conversation.
                </h2>

                <p class="section-description">
                    The on-page presentation is designed for rapid human review.
                    Downloadable Markdown files preserve the complete source-grounded
                    analysis.
                </p>
            </div>
        </div>
    </section>
    """
)

high_record_html = "".join(
    (
        '<div class="report-list__item">'
        f'<strong>{escape(row["date"].strftime("%b %d"))}</strong>'
        f' — {escape(row["observation"])}'
        "</div>"
    )
    for _, row in high_records.tail(4).iterrows()
)

if not high_record_html:
    high_record_html = (
        '<div class="report-list__item">'
        "No high-severity observations are currently available."
        "</div>"
    )

recent_record_html = "".join(
    (
        '<div class="report-list__item">'
        f'<strong>{escape(row["date"].strftime("%b %d"))}</strong>'
        f' · {escape(row["type"])}'
        f' · {escape(row["severity"])}'
        f'<br>{escape(row["observation"])}'
        "</div>"
    )
    for _, row in recent_records.iterrows()
)

render(
    f"""
    <div class="report-grid">
        <article class="report">
            <div class="report__header">
                <div class="report__eyebrow">
                    Thirty-day observation brief
                </div>

                <div class="report__title">
                    Recorded changes during the latest review period
                </div>
            </div>

            <div class="report__body">
                <div class="report-period">
                    <div class="report-period__label">
                        Observation period
                    </div>

                    <div class="report-period__value">
                        {escape(review_start)} – {escape(review_end)}
                    </div>
                </div>

                <div class="report-stat-grid">
                    <div class="report-stat">
                        <div class="report-stat__label">
                            Total records
                        </div>
                        <div class="report-stat__value">
                            {recent_metrics["total"]}
                        </div>
                    </div>

                    <div class="report-stat">
                        <div class="report-stat__label">
                            Speech
                        </div>
                        <div class="report-stat__value">
                            {recent_metrics["speech"]}
                        </div>
                    </div>

                    <div class="report-stat">
                        <div class="report-stat__label">
                            Repetition
                        </div>
                        <div class="report-stat__value">
                            {recent_metrics["repetition"]}
                        </div>
                    </div>

                    <div class="report-stat">
                        <div class="report-stat__label">
                            High severity
                        </div>
                        <div class="report-stat__value">
                            {recent_metrics["high"]}
                        </div>
                    </div>
                </div>

                <div class="report-list">
                    <div class="report-list__heading">
                        Interpretation boundary
                    </div>

                    <div class="report-list__item">
                        These figures describe the observation log.
                        They are not cognitive scores and do not measure
                        disease progression.
                    </div>
                </div>
            </div>
        </article>

        <article class="report">
            <div class="report__header">
                <div class="report__eyebrow">
                    Caregiver-clinician preparation
                </div>

                <div class="report__title">
                    High-priority context and recent source observations
                </div>
            </div>

            <div class="report__body">
                <div class="report-list">
                    <div class="report-list__heading">
                        High-severity source records
                    </div>

                    {high_record_html}
                </div>

                <div class="report-list">
                    <div class="report-list__heading">
                        Most recent source records
                    </div>

                    {recent_record_html}
                </div>

                <div class="report-list">
                    <div class="report-list__heading">
                        Suggested clinical discussion
                    </div>

                    <div class="report-list__item">
                        Which observations, routines, medication effects, sleep
                        changes, or environmental factors should be monitored
                        more systematically?
                    </div>

                    <div class="report-list__item">
                        Which recommendations from this visit should the family
                        record and review before the next appointment?
                    </div>
                </div>
            </div>
        </article>
    </div>
    """
)

download_one, download_two, download_three = st.columns(
    3,
)

with download_one:
    st.download_button(
        label="Download thirty-day brief",
        data=thirty_day_brief,
        file_name="neuroblackbox_thirty_day_brief.md",
        mime="text/markdown",
        width="stretch",
    )

with download_two:
    st.download_button(
        label="Download clinician summary",
        data=clinician_summary,
        file_name="neuroblackbox_clinician_summary.md",
        mime="text/markdown",
        width="stretch",
    )

with download_three:
    st.download_button(
        label="Download episode reconstruction",
        data=before_episode_analysis,
        file_name="neuroblackbox_episode_reconstruction.md",
        mime="text/markdown",
        width="stretch",
    )

st.divider()


# =============================================================================
# Safety
# =============================================================================

render(
    """
    <section id="safety">
        <div class="section-header">
            <div class="section-index">
                08 / RESEARCH BOUNDARY
            </div>

            <div>
                <h2 class="section-title">
                    A continuity tool, not a diagnostic system.
                </h2>

                <p class="section-description">
                    The prototype is intentionally constrained. Reliability
                    depends on the quality, completeness, timing, and wording
                    of caregiver-entered observations.
                </p>
            </div>
        </div>

        <div class="limitations-grid">
            <article class="limitation">
                <div class="limitation__title">
                    Caregiver-entered evidence
                </div>

                <div class="limitation__copy">
                    The system cannot independently verify whether an
                    observation is complete, representative, or interpreted
                    consistently.
                </div>
            </article>

            <article class="limitation">
                <div class="limitation__title">
                    No causal inference
                </div>

                <div class="limitation__copy">
                    An observation occurring before an episode does not
                    establish that it predicted or caused the episode.
                </div>
            </article>

            <article class="limitation">
                <div class="limitation__title">
                    No clinical validation
                </div>

                <div class="limitation__copy">
                    NeuroBlackBox has not undergone clinical validation,
                    regulatory review, or medical-device assessment.
                </div>
            </article>

            <article class="limitation">
                <div class="limitation__title">
                    Retrieval can be incomplete
                </div>

                <div class="limitation__copy">
                    Semantic retrieval may omit relevant records or return
                    observations that are only weakly related to a question.
                </div>
            </article>

            <article class="limitation">
                <div class="limitation__title">
                    Not an official medical record
                </div>

                <div class="limitation__copy">
                    Generated summaries support continuity and preparation.
                    They do not replace formal clinical documentation.
                </div>
            </article>

            <article class="limitation">
                <div class="limitation__title">
                    Human review remains essential
                </div>

                <div class="limitation__copy">
                    Families and qualified clinicians should review all
                    records and decide whether further evaluation is appropriate.
                </div>
            </article>
        </div>
    </section>
    """
)


# =============================================================================
# Closing pitch
# =============================================================================

render(
    """
    <section class="closing-band">
        <div class="closing-band__grid">
            <div>
                <div class="closing-band__eyebrow">
                    The NeuroBlackBox thesis
                </div>

                <h2 class="closing-band__title">
                    Every appointment should begin with context,
                    not reconstruction.
                </h2>

                <p class="closing-band__copy">
                    NeuroBlackBox turns fragmented daily observations into
                    a persistent, searchable, source-grounded memory that
                    follows the care journey across appointments.
                </p>
            </div>

            <div class="closing-band__actions">
                <a class="closing-action" href="#prototype">
                    <span>Open the live prototype</span>
                    <span>→</span>
                </a>

                <a class="closing-action" href="#architecture">
                    <span>Review the memory architecture</span>
                    <span>→</span>
                </a>

                <a class="closing-action" href="#top">
                    <span>Return to the beginning</span>
                    <span>↑</span>
                </a>
            </div>
        </div>
    </section>
    """
)


# =============================================================================
# Footer
# =============================================================================

render(
    """
    <footer class="site-footer">
        <div>
            <strong>NeuroBlackBox</strong><br>
            Longitudinal local memory for cognitive-care observations
            and clinician preparation.
        </div>

        <div>
            Python · Streamlit · Pandas · Supermemory Local
        </div>
    </footer>
    """
)
