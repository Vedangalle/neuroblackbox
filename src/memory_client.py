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
    "neuroblackbox_demo_patient_eleanor",
)


def sdk_available() -> bool:
    return Supermemory is not None


def get_client() -> Any:
    if Supermemory is None:
        return None

    return Supermemory(
        api_key=API_KEY,
        base_url=BASE_URL,
    )


def observation_to_memory(row: dict) -> str:
    return (
        "NeuroBlackBox caregiver observation. "
        "Patient: Eleanor. "
        f"Date: {row['date']}. "
        f"Type: {row['type']}. "
        f"Severity: {row['severity']}. "
        f"Source: {row['source']}. "
        f"Observation: {row['observation']}"
    )


def store_observation(row: dict) -> bool:
    client = get_client()
    if client is None:
        return False

    try:
        client.add(
            content=observation_to_memory(row),
            container_tags=[CONTAINER_TAG],
            metadata={
                "project": "NeuroBlackBox",
                "patient": "Eleanor",
                "type": str(row.get("type", "")),
                "severity": str(row.get("severity", "")),
                "source": str(row.get("source", "")),
                "date": str(row.get("date", "")),
            },
        )
        return True
    except Exception as exc:
        print(f"Supermemory store failed: {exc}")
        return False


def search_observations(question: str, limit: int = 5) -> list:
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
        print(f"Supermemory search failed: {exc}")
        return []
