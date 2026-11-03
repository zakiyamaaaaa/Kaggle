from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from kaggriculture_agent.dataset import DatasetError, audit_trajectory_tables

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "outputs" / "datasets" / "development_32seed_v1"


def _tables() -> dict[str, pa.Table]:
    return {
        name: pq.read_table(DATA / f"{name}.parquet")
        for name in ("transitions", "episodes", "pairs")
    }


def test_existing_common_dataset_passes_integrity_audit() -> None:
    audit = audit_trajectory_tables(_tables())

    assert audit["rows"]["transitions"] == 64 * 2 * 719
    assert audit["unique_games"] == 64
    assert audit["unique_pairs"] == 32
    assert audit["unique_seeds"] == 32
    assert not any(audit["duplicate_keys"].values())


def test_duplicate_transition_key_is_rejected() -> None:
    tables = _tables()
    tables["transitions"] = pa.concat_tables(
        [tables["transitions"], tables["transitions"].slice(0, 1)]
    )

    with pytest.raises(DatasetError, match="duplicate keys"):
        audit_trajectory_tables(tables)
