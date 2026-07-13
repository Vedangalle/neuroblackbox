from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import hashlib
import json
import os
from typing import Any

from dotenv import load_dotenv

try:
    from supermemory import Supermemory
except ImportError:
    Supermemory = None


load_dotenv()

BASE_URL = os.getenv("SUPERMEMORY_API_URL", "http://localhost:6767")
API_KEY = os.getenv("SUPERMEMORY_API_KEY", "local")
CONTAINER_TAG = os.getenv(
    "NEUROBLACKBOX_CONTAINER",
    "neuroblackbox_demo_patient_eleanor_v2",
)
PATIENT_NAME = os.getenv("NEUROBLACKBOX_DEMO_PATIENT", "Eleanor")

OBSERVATION_FIELDS = (
    "date",
    "type",
    "severity",
    "source",
    "observation",
)


@dataclass(frozen=True)
class MemoryConnectionStatus:
    online: bool
    label: str
    detail: str


def sdk_available() -> bool:
    """Return whether the Python SDK can be imported, not service health."""
    return Supermemory is not None


def get_client(
    *,
    timeout_seconds: float | None = None,
    max_retries: int = 2,
) -> Any:
    if Supermemory is None:
        return None

    client_options: dict[str, Any] = {
        "api_key": API_KEY,
        "base_url": BASE_URL,
        "max_retries": max_retries,
    }

    if timeout_seconds is not None:
        client_options["timeout"] = timeout_seconds

    return Supermemory(**client_options)


def check_connection(
    timeout_seconds: float = 2.0,
) -> MemoryConnectionStatus:
    """Probe the configured local service without writing any memory."""
    client = get_client(
        timeout_seconds=timeout_seconds,
        max_retries=0,
    )

    if client is None:
        return MemoryConnectionStatus(
            online=False,
            label="Local fallback",
            detail="Supermemory SDK unavailable",
        )

    try:
        client.search.documents(
            q="NeuroBlackBox connectivity check",
            container_tags=[CONTAINER_TAG],
            limit=1,
            timeout=timeout_seconds,
        )
    except Exception as exc:
        error_name = type(exc).__name__
        print(f"Supermemory health check failed ({error_name}).")
        return MemoryConnectionStatus(
            online=False,
            label="Local fallback",
            detail=f"Supermemory unavailable ({error_name})",
        )

    return MemoryConnectionStatus(
        online=True,
        label="Online",
        detail="Supermemory Local connection verified",
    )


def canonical_observation(
    row: Mapping[str, Any],
) -> dict[str, str]:
    canonical: dict[str, str] = {}

    for field in OBSERVATION_FIELDS:
        value = row.get(field, "")

        if field == "date" and hasattr(value, "strftime"):
            cleaned = value.strftime("%Y-%m-%d")
        else:
            cleaned = " ".join(str(value).strip().split())

        if field == "date" and len(cleaned) >= 10:
            cleaned = cleaned[:10]

        if field in {"type", "severity", "source"}:
            cleaned = cleaned.lower()

        canonical[field] = cleaned

    return canonical


def observation_custom_id(
    row: Mapping[str, Any],
) -> str:
    """Create a stable, API-safe ID for an immutable source observation."""
    payload = {
        "container": CONTAINER_TAG,
        "patient": PATIENT_NAME,
        "observation": canonical_observation(row),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()[:32]
    return f"neuroblackbox-{digest}"


def observation_to_memory(
    row: Mapping[str, Any],
) -> str:
    observation = canonical_observation(row)
    return (
        "NeuroBlackBox caregiver-reported source observation. "
        f"Patient: {PATIENT_NAME}. "
        f"Date: {observation['date']}. "
        f"Type: {observation['type']}. "
        f"Severity: {observation['severity']}. "
        f"Source: {observation['source']}. "
        f"Observation: {observation['observation']}"
    )


def _add_observation(
    client: Any,
    row: Mapping[str, Any],
) -> None:
    observation = canonical_observation(row)
    custom_id = observation_custom_id(observation)

    client.add(
        content=observation_to_memory(observation),
        container_tags=[CONTAINER_TAG],
        custom_id=custom_id,
        metadata={
            "project": "NeuroBlackBox",
            "patient": PATIENT_NAME,
            "record_kind": "caregiver-reported observation",
            "observation_id": custom_id,
            "type": observation["type"],
            "severity": observation["severity"],
            "source": observation["source"],
            "date": observation["date"],
        },
    )


def store_observation(
    row: Mapping[str, Any],
) -> bool:
    client = get_client()
    if client is None:
        return False

    try:
        _add_observation(client, row)
        return True
    except Exception as exc:
        print(f"Supermemory store failed ({type(exc).__name__}).")
        return False


def sync_observations(
    rows: Iterable[Mapping[str, Any]],
) -> dict[str, int]:
    """Submit each record with a stable ID so reruns reconcile safely."""
    observations = list(rows)
    summary = {
        "attempted": len(observations),
        "accepted": 0,
        "failed": 0,
    }

    client = get_client()
    if client is None:
        summary["failed"] = len(observations)
        return summary

    for row in observations:
        try:
            _add_observation(client, row)
            summary["accepted"] += 1
        except Exception as exc:
            summary["failed"] += 1
            print(
                "Supermemory reconciliation failed for one observation "
                f"({type(exc).__name__})."
            )

    return summary


def search_observations(
    question: str,
    limit: int = 5,
) -> list[Any]:
    client = get_client()
    if client is None:
        return []

    try:
        response = client.search.documents(
            q=question,
            container_tags=[CONTAINER_TAG],
            limit=limit,
        )
        return getattr(response, "results", []) or []
    except Exception as exc:
        print(f"Supermemory search failed ({type(exc).__name__}).")
        return []
