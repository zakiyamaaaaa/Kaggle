from __future__ import annotations

from copy import deepcopy

import pytest

from scripts.build_event_counterfactuals import (
    ACTIONS,
    ENCODED_FEATURE_NAMES,
    EventMatchError,
    build_event_context,
    dataset_diagnostics,
    event_context_key,
    event_identity,
    validate_event_context,
)


def _event(*, seed: int = 7, seat: int = 1, step: int = 42, event_index: int = 0):
    scalars = [0.0] * len(ENCODED_FEATURE_NAMES)
    # Exercise two explicit clip bounds in the diagnostics.
    scalars[ENCODED_FEATURE_NAMES.index("own_cash")] = 2.5
    scalars[ENCODED_FEATURE_NAMES.index("quantity")] = 3.0
    return build_event_context(
        seed,
        seat,
        step,
        "MILK",
        150,
        [[[0.0, 1.0]]],
        scalars,
        event_index=event_index,
    )


def test_stable_event_match_ignores_index_but_rejects_identity_and_encoding_drift():
    expected = _event(event_index=3)
    same_context = deepcopy(expected)
    same_context["event_index"] = 999
    validate_event_context(expected, same_context)
    assert event_identity(expected) == event_identity(same_context)
    assert event_context_key(expected) == event_context_key(same_context)

    for field, value in (
        ("seed", 8),
        ("seat", 0),
        ("step", 43),
        ("item", "WOOL"),
        ("quantity", 149),
    ):
        drifted = deepcopy(expected)
        drifted[field] = value
        with pytest.raises(EventMatchError, match="event context drift"):
            validate_event_context(expected, drifted)

    drifted = deepcopy(expected)
    drifted["image"][0][0][0] = 0.5
    with pytest.raises(EventMatchError, match="encoded features"):
        validate_event_context(expected, drifted)

    drifted = deepcopy(expected)
    drifted["scalars"][0] = 0.25
    with pytest.raises(EventMatchError, match="encoded features"):
        validate_event_context(expected, drifted)


def test_dataset_diagnostics_reports_duplicates_ties_and_saturation():
    first = _event(event_index=0)
    second = deepcopy(first)
    second.update(seed=8, step=43, event_index=1)
    first["margins"] = {"full": 10.0, "skip": 10.0, "half": 8.0}
    second["margins"] = {name: float(index) for index, name in enumerate(ACTIONS)}

    diagnostics = dataset_diagnostics([first, second])

    assert diagnostics["captured_event_count"] == 2
    assert diagnostics["unique_context_count"] == 1
    assert diagnostics["exact_duplicate_contexts"] == 1
    assert diagnostics["exact_duplicate_context_groups"] == 1
    assert diagnostics["unique_event_identity_count"] == 2
    assert diagnostics["duplicate_event_identities"] == 0
    assert diagnostics["tie_rates"]["any"] == pytest.approx(0.5)
    assert diagnostics["tie_rates"]["all_actions"] == 0.0
    saturation = diagnostics["saturation_diagnostics"]
    assert saturation["saturated_scalar_values"] == 4
    assert saturation["by_feature"]["own_cash"]["saturated"] == 2
    assert saturation["by_feature"]["quantity"]["saturated"] == 2
