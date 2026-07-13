from __future__ import annotations

import ast
from datetime import date, timedelta
import html
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import pandas as pd


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = REPOSITORY_ROOT / "src" / "app.py"
MEMORY_CLIENT_PATH = REPOSITORY_ROOT / "src" / "memory_client.py"
OBSERVATION_COLUMNS = [
    "date",
    "type",
    "severity",
    "source",
    "observation",
]


class CacheStub:
    @staticmethod
    def clear() -> None:
        return None


def load_app_symbols(*names: str) -> dict[str, object]:
    """Load selected pure app definitions without executing Streamlit UI code."""
    tree = ast.parse(APP_PATH.read_text(encoding="utf-8"))
    selected = [
        node
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef))
        and node.name in names
    ]
    namespace: dict[str, object] = {
        "Any": object,
        "DATA_PATH": REPOSITORY_ROOT / "data" / "runtime_observations.csv",
        "OBSERVATION_COLUMNS": OBSERVATION_COLUMNS,
        "Path": Path,
        "SEED_DATA_PATH": REPOSITORY_ROOT / "data" / "sample_observations.csv",
        "date": date,
        "html": html,
        "is_before_episode_question": lambda _question: False,
        "load_data": CacheStub,
        "os": os,
        "pd": pd,
        "re": re,
        "shutil": shutil,
        "tempfile": tempfile,
        "timedelta": timedelta,
    }
    exec(
        compile(ast.Module(body=selected, type_ignores=[]), APP_PATH, "exec"),
        namespace,
    )
    return namespace


def observation_frame(rows: list[dict[str, str]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=OBSERVATION_COLUMNS)
    frame["date"] = pd.to_datetime(frame["date"])
    return frame


class DataPersistenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.symbols = load_app_symbols(
            "ObservationDataError",
            "empty_observation_frame",
            "ensure_runtime_data",
            "normalize_observation_frame",
            "save_data",
        )

    def test_normalization_deduplicates_and_orders_records(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "date": "2026-07-02",
                    "type": " Speech ",
                    "severity": " HIGH ",
                    "source": " caregiver ",
                    "observation": " Paused while recalling a name. ",
                },
                {
                    "date": "2026-07-01",
                    "type": "routine",
                    "severity": "low",
                    "source": "caregiver",
                    "observation": "Completed the morning routine.",
                },
                {
                    "date": "2026-07-02",
                    "type": "speech",
                    "severity": "high",
                    "source": "caregiver",
                    "observation": "Paused while recalling a name.",
                },
            ]
        )

        normalized = self.symbols["normalize_observation_frame"](frame)

        self.assertEqual(len(normalized), 2)
        self.assertEqual(normalized.iloc[0]["type"], "routine")
        self.assertEqual(normalized.iloc[1]["type"], "speech")
        self.assertEqual(normalized.iloc[1]["severity"], "high")

    def test_save_is_atomic_and_owner_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data_path = Path(directory) / "runtime.csv"
            self.symbols["DATA_PATH"] = data_path
            frame = observation_frame(
                [
                    {
                        "date": "2026-07-01",
                        "type": "speech",
                        "severity": "medium",
                        "source": "caregiver",
                        "observation": "Paused while recalling a name.",
                    }
                ]
            )

            self.symbols["save_data"](frame)

            saved = pd.read_csv(data_path)
            self.assertEqual(saved.to_dict(orient="records")[0]["type"], "speech")
            self.assertEqual(stat.S_IMODE(data_path.stat().st_mode), 0o600)
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])

    def test_failed_save_preserves_existing_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data_path = Path(directory) / "runtime.csv"
            data_path.write_text("existing complete record\n", encoding="utf-8")
            self.symbols["DATA_PATH"] = data_path
            frame = observation_frame(
                [
                    {
                        "date": "2026-07-01",
                        "type": "speech",
                        "severity": "medium",
                        "source": "caregiver",
                        "observation": "Synthetic observation.",
                    }
                ]
            )

            with mock.patch.object(
                pd.DataFrame,
                "to_csv",
                side_effect=OSError("simulated write failure"),
            ):
                with self.assertRaises(self.symbols["ObservationDataError"]):
                    self.symbols["save_data"](frame)

            self.assertEqual(
                data_path.read_text(encoding="utf-8"),
                "existing complete record\n",
            )
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])

    def test_runtime_initialization_does_not_mutate_seed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            seed_path = Path(directory) / "seed.csv"
            runtime_path = Path(directory) / "runtime.csv"
            seed_content = "date,type,severity,source,observation\n"
            seed_path.write_text(seed_content, encoding="utf-8")
            self.symbols["SEED_DATA_PATH"] = seed_path
            self.symbols["DATA_PATH"] = runtime_path

            self.symbols["ensure_runtime_data"]()

            self.assertEqual(seed_path.read_text(encoding="utf-8"), seed_content)
            self.assertEqual(runtime_path.read_text(encoding="utf-8"), seed_content)
            self.assertEqual(stat.S_IMODE(runtime_path.stat().st_mode), 0o600)


class MemoryAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
        import memory_client

        cls.memory_client = memory_client

    def test_custom_id_is_deterministic(self) -> None:
        row = {
            "date": "2026-07-01",
            "type": "Speech",
            "severity": "Medium",
            "source": "Caregiver",
            "observation": "  Paused while recalling a familiar name.  ",
        }
        equivalent = dict(row, type="speech", severity="medium", source="caregiver")

        self.assertEqual(
            self.memory_client.observation_custom_id(row),
            self.memory_client.observation_custom_id(equivalent),
        )

    def test_add_uses_plural_container_scope(self) -> None:
        client = mock.Mock()
        row = {
            "date": "2026-07-01",
            "type": "speech",
            "severity": "medium",
            "source": "caregiver",
            "observation": "Synthetic observation.",
        }

        self.memory_client._add_observation(client, row)

        kwargs = client.add.call_args.kwargs
        self.assertEqual(kwargs["container_tags"], [self.memory_client.CONTAINER_TAG])
        self.assertNotIn("container_tag", kwargs)

    def test_search_uses_plural_container_scope(self) -> None:
        client = mock.Mock()
        client.search.documents.return_value.results = ["result"]

        with mock.patch.object(self.memory_client, "get_client", return_value=client):
            results = self.memory_client.search_observations("repeated questions")

        self.assertEqual(results, ["result"])
        kwargs = client.search.documents.call_args.kwargs
        self.assertEqual(kwargs["container_tags"], [self.memory_client.CONTAINER_TAG])
        self.assertNotIn("container_tag", kwargs)

    def test_partial_sync_reports_failure_for_retry(self) -> None:
        client = mock.Mock()
        client.add.side_effect = [mock.Mock(), RuntimeError("simulated")]
        rows = [
            {
                "date": "2026-07-01",
                "type": "speech",
                "severity": "medium",
                "source": "caregiver",
                "observation": f"Synthetic observation {index}.",
            }
            for index in range(2)
        ]

        with (
            mock.patch.object(self.memory_client, "get_client", return_value=client),
            mock.patch("builtins.print"),
        ):
            summary = self.memory_client.sync_observations(rows)

        self.assertEqual(summary, {"attempted": 2, "accepted": 1, "failed": 1})


class ReportGroundingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.symbols = load_app_symbols(
            "keyword_count",
            "combined_observation_text",
            "analyze_observations",
            "format_observation",
            "generate_clinician_preparation_summary",
            "format_date_range",
            "evidence_items",
            "category_names",
            "natural_language_list",
            "generate_grounded_answer",
            "memory_sync_required",
        )

    def test_clinician_summary_omits_unrecorded_categories(self) -> None:
        frame = observation_frame(
            [
                {
                    "date": "2026-07-01",
                    "type": "sleep",
                    "severity": "medium",
                    "source": "caregiver",
                    "observation": "Woke twice overnight.",
                }
            ]
        )

        summary = self.symbols["generate_clinician_preparation_summary"](frame)

        self.assertIn("- Sleep: 1", summary)
        self.assertIn("recorded sleep observations", summary)
        for absent in ("Speech", "Repetition", "Routine", "Medication", "Navigation"):
            self.assertNotIn(f"- {absent}:", summary)

    def test_clinician_answer_uses_only_evidenced_categories(self) -> None:
        frame = observation_frame(
            [
                {
                    "date": "2026-07-01",
                    "type": "sleep",
                    "severity": "medium",
                    "source": "caregiver",
                    "observation": "Woke twice overnight.",
                }
            ]
        )

        answer = self.symbols["generate_grounded_answer"](
            frame,
            "What should we discuss with the clinician?",
        )["answer"]

        self.assertIn("recorded sleep category", answer)
        for absent in ("speech", "repetition", "medication", "routine"):
            self.assertNotIn(absent, answer)

    def test_failed_or_changed_sync_is_retried(self) -> None:
        signature = (("2026-07-01", "speech"),)
        prior_signature = (("2026-06-30", "routine"),)
        required = self.symbols["memory_sync_required"]

        self.assertTrue(required(True, None, signature))
        self.assertTrue(required(True, prior_signature, signature))
        self.assertFalse(required(True, signature, signature))
        self.assertFalse(required(False, None, signature))


class RepositoryContractTests(unittest.TestCase):
    def test_seed_data_contract(self) -> None:
        frame = pd.read_csv(REPOSITORY_ROOT / "data" / "sample_observations.csv")

        self.assertEqual(list(frame.columns), OBSERVATION_COLUMNS)
        self.assertFalse(frame.empty)
        self.assertEqual(int(frame.isna().sum().sum()), 0)
        self.assertEqual(int(frame.duplicated().sum()), 0)
        self.assertEqual(int(pd.to_datetime(frame["date"], errors="coerce").isna().sum()), 0)

    def test_local_runtime_state_is_ignored(self) -> None:
        ignore_file = (REPOSITORY_ROOT / ".gitignore").read_text(encoding="utf-8")
        result = subprocess.run(
            ["git", "check-ignore", ".supermemory/", "data/runtime_observations.csv"],
            cwd=REPOSITORY_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertIn("/.supermemory/", ignore_file.splitlines())
        self.assertIn("/data/runtime_observations.csv", ignore_file.splitlines())
        self.assertEqual(result.returncode, 0)

    def test_safe_api_key_template(self) -> None:
        template = (REPOSITORY_ROOT / ".env.example").read_text(encoding="utf-8")

        self.assertIn("SUPERMEMORY_API_KEY=sm_your_local_api_key_here", template)
        self.assertNotIn("SUPERMEMORY_API_KEY=local", template)

    def test_async_submission_language_does_not_claim_completion(self) -> None:
        source = APP_PATH.read_text(encoding="utf-8")

        self.assertIn("Its Supermemory submission was accepted.", source)
        self.assertNotIn("Its Supermemory record was confirmed.", source)

    def test_privacy_docs_include_external_provider_boundary(self) -> None:
        paths = (
            REPOSITORY_ROOT / "README.md",
            REPOSITORY_ROOT / "docs" / "demo_script.md",
            REPOSITORY_ROOT / "docs" / "hackathon_submission.md",
            REPOSITORY_ROOT / "docs" / "product_thesis.md",
            REPOSITORY_ROOT / "docs" / "safety_positioning.md",
        )

        for path in paths:
            content = path.read_text(encoding="utf-8").lower()
            self.assertIn("external model provider", content, path)
            self.assertRegex(
                content,
                r"model-dependent\s+supermemory\s+operations",
                path,
            )

    def test_python_files_have_final_newlines(self) -> None:
        for path in (APP_PATH, MEMORY_CLIENT_PATH, Path(__file__)):
            self.assertTrue(path.read_bytes().endswith(b"\n"), path)

    def test_streamlit_starts_without_uncaught_exception(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            environment = os.environ.copy()
            environment.update(
                {
                    "NEUROBLACKBOX_DATA_PATH": str(Path(directory) / "runtime.csv"),
                    "SUPERMEMORY_API_URL": "http://127.0.0.1:1",
                    "SUPERMEMORY_API_KEY": "sm_test_placeholder",
                }
            )
            code = (
                "import sys; "
                f"sys.path.insert(0, {str(APP_PATH.parent)!r}); "
                "from streamlit.testing.v1 import AppTest; "
                f"app=AppTest.from_file({str(APP_PATH)!r}, default_timeout=15).run(); "
                "assert not app.exception, app.exception"
            )
            result = subprocess.run(
                [sys.executable, "-c", code],
                cwd=REPOSITORY_ROOT,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(
                result.returncode,
                0,
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
            )


if __name__ == "__main__":
    unittest.main()
