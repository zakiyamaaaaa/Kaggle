#!/usr/bin/env python3
"""Build per-event skip/half/full counterfactual labels on common seeds."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from kaggriculture_agent import registry
from kaggriculture_agent.cnn_ppo import SCALARS
from kaggriculture_agent.event_cnn_ppo import (
    ACTIONS,
    EVENT_SCHEMA_V1,
    EVENT_SCHEMA_V2,
    encode_event,
    event_feature_names,
    normalize_event_schema,
)
from kaggriculture_agent.local_arena import GameSpec, play_game


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "experiments/omw-event-cnn-ppo-v1/main.py"
CONTROL = ROOT / "references/kaggle-scan-2026-09-21/extracted/one-more-wheat/main.py"
ELIGIBLE_ITEMS = (
    "WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL", "FERTILIZER"
)

# These fields form the stable event context used to target an intervention.
# ``event_index`` is intentionally not part of either key: it is a useful
# display/selection position in the baseline trace, but it is not stable after
# an earlier event is skipped or partially sold.
EVENT_IDENTITY_FIELDS = ("seed", "seat", "step", "item", "quantity")
EVENT_CONTEXT_FIELDS = EVENT_IDENTITY_FIELDS + ("image", "scalars")
ENCODED_FEATURE_NAMES = tuple(SCALARS) + tuple(event_feature_names(EVENT_SCHEMA_V1))

# ``encode_observation`` and ``encode_event`` clip only these scalar features.
# Keep the bounds here explicit so saturation is measurable instead of being
# inferred from a particular dataset's observed min/max.
SATURATION_BOUNDS: dict[str, tuple[float | None, float | None]] = {
    "own_cash": (None, 2.5),
    "rival_cash": (None, 2.5),
    "cash_margin": (-2.5, 2.5),
    "wheat_price": (None, 3.0),
    "milk_price": (None, 3.0),
    "wool_price": (None, 3.0),
    "melon_price": (None, 3.0),
    "quantity": (None, 3.0),
    "net_rival_batch": (None, 3.0),
    "demand_recovery": (None, 3.0),
    "exposure": (None, 5.0),
    "sale_horizon": (None, 2.0),
    "current_price": (None, 3.0),
    "market_inventory": (None, 3.0),
    "rival_stock": (None, 3.0),
}
SATURATION_BOUNDS_BY_SCHEMA: dict[int, dict[str, tuple[float | None, float | None]]] = {
    EVENT_SCHEMA_V1: SATURATION_BOUNDS,
    EVENT_SCHEMA_V2: {
        **{name: bounds for name, bounds in SATURATION_BOUNDS.items() if name != "market_inventory"},
        "market_inventory_log": (None, None),
        "exposure_per_unit": (None, None),
        "net_stock_ratio": (None, None),
    },
}


class EventMatchError(ValueError):
    """Raised when a counterfactual target is not the same event context."""


def _nested_encoded_equal(expected: Any, actual: Any, path: str = "") -> str | None:
    """Return a short mismatch description for encoded nested values."""

    if isinstance(expected, Sequence) and not isinstance(expected, (str, bytes)):
        if not isinstance(actual, Sequence) or isinstance(actual, (str, bytes)):
            return f"{path or 'value'} type differs"
        if len(expected) != len(actual):
            return f"{path or 'value'} length differs ({len(expected)} != {len(actual)})"
        for index, (left, right) in enumerate(zip(expected, actual)):
            mismatch = _nested_encoded_equal(left, right, f"{path}[{index}]")
            if mismatch:
                return mismatch
        return None
    try:
        left = float(expected)
        right = float(actual)
    except (TypeError, ValueError):
        return None if expected == actual else f"{path or 'value'} differs"
    if not (math.isfinite(left) and math.isfinite(right)):
        return None if left == right else f"{path or 'value'} is non-finite"
    if not math.isclose(left, right, rel_tol=0.0, abs_tol=1e-12):
        return f"{path or 'value'} differs ({left!r} != {right!r})"
    return None


def build_event_context(
    seed: int,
    seat: int,
    step: int,
    item: str,
    quantity: int,
    image: Any,
    scalars: Any,
    *,
    event_index: int | None = None,
) -> dict[str, Any]:
    """Build the complete stable context captured for one sell opportunity."""

    context = {
        "seed": int(seed),
        "seat": int(seat),
        "step": int(step),
        "item": str(item),
        "quantity": int(quantity),
        "image": image,
        "scalars": scalars,
    }
    if event_index is not None:
        context["event_index"] = int(event_index)
    return context


def event_identity(event: Mapping[str, Any]) -> tuple[Any, ...]:
    """Return identity fields that remain meaningful across reruns."""

    try:
        return tuple(event[field] for field in EVENT_IDENTITY_FIELDS)
    except KeyError as exc:
        raise EventMatchError(f"event is missing identity field {exc.args[0]!r}") from exc


def event_context_key(event: Mapping[str, Any]) -> str:
    """Return a canonical key for encoded model context diagnostics."""

    try:
        payload = {field: event[field] for field in ("image", "scalars")}
    except KeyError as exc:
        raise EventMatchError(f"event is missing encoded field {exc.args[0]!r}") from exc
    try:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise EventMatchError("event encoded features are not JSON-safe") from exc


def validate_event_context(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> None:
    """Validate every stable identity and encoded feature field.

    A target that has the same callback index but a changed item/quantity or
    observation encoding is not the same counterfactual event.  Callers should
    treat this exception as a failed/drifted intervention, never silently
    continue with an index-based fallback.
    """

    for field in EVENT_IDENTITY_FIELDS:
        if field not in expected or field not in actual:
            raise EventMatchError(f"event context missing {field!r}")
        if expected[field] != actual[field]:
            raise EventMatchError(
                f"event context drift in {field}: expected {expected[field]!r}, "
                f"observed {actual[field]!r}"
            )
    for field in ("image", "scalars"):
        if field not in expected or field not in actual:
            raise EventMatchError(f"event context missing {field!r}")
        mismatch = _nested_encoded_equal(expected[field], actual[field], field)
        if mismatch:
            raise EventMatchError(f"event context drift in encoded features: {mismatch}")


# A name that reads naturally in tests and callers that do not need the longer
# implementation name.  Keep the validating behavior in one place.
validate_event_match = validate_event_context


def _target_header_check(target: Mapping[str, Any], seed: int, seat: int) -> None:
    for field in EVENT_IDENTITY_FIELDS:
        if field not in target:
            raise EventMatchError(f"target event is missing {field!r}")
    for field, observed in (("seed", seed), ("seat", seat)):
        if int(target[field]) != observed:
            raise EventMatchError(
                f"target event {field} does not belong to this game: "
                f"expected {observed!r}, observed {target[field]!r}"
            )


def _tie_names(margins: Mapping[str, float]) -> tuple[str, ...]:
    best = max(float(margins[name]) for name in ACTIONS)
    return tuple(name for name in ACTIONS if float(margins[name]) == best)


def _saturation_diagnostics(
    events: Sequence[Mapping[str, Any]], feature_schema: int = EVENT_SCHEMA_V1
) -> dict[str, Any]:
    schema = normalize_event_schema(feature_schema)
    encoded_feature_names = tuple(SCALARS) + tuple(event_feature_names(schema))
    bounds_by_feature = SATURATION_BOUNDS_BY_SCHEMA[schema]
    feature_values: dict[str, list[float]] = {name: [] for name in encoded_feature_names}
    for event in events:
        scalars = event.get("scalars")
        if not isinstance(scalars, Sequence) or isinstance(scalars, (str, bytes)):
            raise EventMatchError("event scalars must be a sequence")
        if len(scalars) != len(encoded_feature_names):
            raise EventMatchError(
                "event scalars length differs from schema: "
                f"{len(scalars)} != {len(encoded_feature_names)}"
            )
        for name, value in zip(encoded_feature_names, scalars):
            feature_values[name].append(float(value))

    by_feature: dict[str, dict[str, Any]] = {}
    saturated_total = 0
    for name, values in feature_values.items():
        lower, upper = bounds_by_feature.get(name, (None, None))
        saturated = sum(
            int(
                (lower is not None and math.isclose(value, lower, rel_tol=0.0, abs_tol=1e-12))
                or (upper is not None and math.isclose(value, upper, rel_tol=0.0, abs_tol=1e-12))
            )
            for value in values
        )
        saturated_total += saturated
        by_feature[name] = {
            "observations": len(values),
            "saturated": saturated,
            "rate": saturated / len(values) if values else 0.0,
            "bounds": [lower, upper],
        }
    total = sum(len(values) for values in feature_values.values())
    return {
        "total_scalar_values": total,
        "saturated_scalar_values": saturated_total,
        "overall_rate": saturated_total / total if total else 0.0,
        "by_feature": by_feature,
    }


def dataset_diagnostics(
    rows: Sequence[Mapping[str, Any]],
    *,
    captured_events: Sequence[Mapping[str, Any]] | None = None,
    feature_schema: int = EVENT_SCHEMA_V1,
) -> dict[str, Any]:
    """Summarize duplicate contexts, ties, and clipping in a label dataset."""

    schema = normalize_event_schema(feature_schema)
    events = list(captured_events if captured_events is not None else rows)
    context_counts = Counter(event_context_key(event) for event in events)
    identity_counts = Counter(event_identity(event) for event in events)
    duplicate_context_groups = sum(count > 1 for count in context_counts.values())
    duplicate_context_rows = sum(count - 1 for count in context_counts.values() if count > 1)
    duplicate_identity_groups = sum(count > 1 for count in identity_counts.values())
    duplicate_identity_rows = sum(count - 1 for count in identity_counts.values() if count > 1)

    tie_counts = Counter()
    for row in rows:
        if "margins" not in row:
            continue
        ties = _tie_names(row["margins"])
        tie_counts["any"] += len(ties) > 1
        tie_counts["all_actions"] += len(ties) == len(ACTIONS)
        for name in ties:
            tie_counts[name] += 1
    labeled = sum("margins" in row for row in rows)
    tie_rates = {
        "any": tie_counts["any"] / labeled if labeled else 0.0,
        "all_actions": tie_counts["all_actions"] / labeled if labeled else 0.0,
        "by_winning_action": {
            name: tie_counts[name] / labeled if labeled else 0.0 for name in ACTIONS
        },
    }
    return {
        "captured_event_count": len(events),
        "labeled_example_count": labeled,
        "unique_context_count": len(context_counts),
        "exact_duplicate_contexts": duplicate_context_rows,
        "exact_duplicate_context_groups": duplicate_context_groups,
        "exact_duplicate_context_rate": duplicate_context_rows / len(events) if events else 0.0,
        "unique_event_identity_count": len(identity_counts),
        "duplicate_event_identities": duplicate_identity_rows,
        "duplicate_event_identity_groups": duplicate_identity_groups,
        "tie_rates": tie_rates,
        "feature_schema": schema,
        "encoded_feature_names": list(tuple(SCALARS) + tuple(event_feature_names(schema))),
        "saturation_diagnostics": _saturation_diagnostics(events, schema),
    }


def load(path, label):
    spec = importlib.util.spec_from_file_location(label, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[label] = module
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=974100)
    parser.add_argument("--seeds", type=int, default=4)
    parser.add_argument("--events-per-game", type=int, default=6)
    parser.add_argument(
        "--items",
        default=",".join(ELIGIBLE_ITEMS),
        help="comma-separated eligible items to capture and label",
    )
    parser.add_argument(
        "--feature-schema",
        "--schema",
        default="v1",
        help="event encoder schema (1/v1 or 2/v2) used for captured and labeled rows",
    )
    args = parser.parse_args()
    feature_schema = normalize_event_schema(args.feature_schema)
    items = tuple(part.strip().upper() for part in args.items.split(",") if part.strip())
    if not items or any(item not in ELIGIBLE_ITEMS for item in items):
        parser.error(f"--items must use {', '.join(ELIGIBLE_ITEMS)}")
    if len(set(items)) != len(items):
        parser.error("duplicate --items")
    if args.seeds < 1:
        parser.error("--seeds must be positive")
    if args.events_per_game < 1:
        parser.error("--events-per-game must be positive")
    candidate = load(WRAPPER, "_event_cf_candidate")
    opponent = load(CONTROL, "_event_cf_opponent")
    registry.AGENTS.update({"_event_cf_candidate": candidate.agent, "_event_cf_opponent": opponent.agent})

    def play(
        seed: int,
        seat: int,
        target: Mapping[str, Any] | None = None,
        choice: int = 2,
        capture: bool = False,
    ):
        if target is not None:
            _target_header_check(target, seed, seat)
        events = []
        index = 0
        matched = False
        mismatch = None

        def decide(observation, item, quantity, net_batch, recovery, exposure, first_sale, rival_stock):
            nonlocal index, matched, mismatch
            if item not in items:
                return 2
            image, scalars = encode_event(
                observation,
                item,
                quantity,
                net_batch,
                recovery,
                exposure,
                first_sale,
                rival_stock,
                schema=feature_schema,
            )
            event = build_event_context(
                seed,
                seat,
                int(observation["step"]),
                item,
                quantity,
                image,
                scalars,
                event_index=index,
            )
            if capture:
                events.append(event)
            force = False
            if target is not None and not matched and event["step"] == target["step"]:
                try:
                    validate_event_context(target, event)
                except EventMatchError as exc:
                    # More than one opportunity can theoretically share a
                    # simulator step.  Keep looking within that step; if no
                    # exact context appears, the caller receives the drift
                    # error below rather than an index-based intervention.
                    mismatch = str(exc)
                else:
                    matched = True
                    force = True
            action = choice if force else 2
            index += 1
            return action

        candidate._OR3_DECIDER = decide
        players = (
            ("_event_cf_candidate", "_event_cf_opponent")
            if seat == 0 else ("_event_cf_opponent", "_event_cf_candidate")
        )
        target_id = event_identity(target) if target is not None else "full"
        result = play_game(GameSpec(f"cf-{seed}-{seat}-{target_id}-{choice}", seed, *players, "cf", "omw"))
        if result.status != "completed":
            raise RuntimeError(result.error)
        if target is not None and not matched:
            detail = f"; nearest mismatch: {mismatch}" if mismatch else ""
            raise EventMatchError(
                "target event context was not observed during intervention" + detail
            )
        own, rival = (
            (result.reward_0, result.reward_1)
            if seat == 0 else (result.reward_1, result.reward_0)
        )
        return own - rival, events

    rows = []
    captured_events = []
    for seed in range(args.seed, args.seed + args.seeds):
        for seat in (0, 1):
            full_margin, events = play(seed, seat, capture=True)
            if not events:
                continue
            captured_events.extend(events)
            if args.events_per_game == 1:
                # Pick a late event so the smoke path also exercises matching
                # after a long unchanged prefix of the trajectory.
                selected = [len(events) - 1]
            elif len(events) <= args.events_per_game:
                selected = list(range(len(events)))
            else:
                selected = sorted(
                    {round(i * (len(events) - 1) / (args.events_per_game - 1))
                     for i in range(args.events_per_game)}
                )
            for event_index in selected:
                margins = {"full": full_margin}
                for choice in (0, 1):
                    margin, _ = play(seed, seat, target=events[event_index], choice=choice)
                    margins[ACTIONS[choice]] = margin
                best_margin = max(margins.values())
                best = min(index for index, name in enumerate(ACTIONS) if margins[name] == best_margin)
                rows.append(
                    {**events[event_index], "margins": margins, "label": best,
                     "label_name": ACTIONS[best]}
                )
            print(json.dumps({"seed": seed, "seat": seat, "events": len(events),
                              "selected": len(selected), "full_margin": full_margin}), flush=True)
    diagnostics = dataset_diagnostics(
        rows, captured_events=captured_events, feature_schema=feature_schema
    )
    report = {
        "schema": 2,
        "feature_schema": feature_schema,
        "encoded_feature_names": list(tuple(SCALARS) + tuple(event_feature_names(feature_schema))),
        "event_context_schema": "seed-seat-step-item-quantity-image-scalars-v1",
        "seed_start": args.seed,
        "seed_count": args.seeds,
        "actions": list(ACTIONS),
        "items": list(items),
        "matching": {
            "strategy": "stable_event_context",
            "identity_fields": list(EVENT_IDENTITY_FIELDS),
            "encoded_fields": ["image", "scalars"],
        },
        "diagnostics": diagnostics,
        "examples": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    counts = {name: sum(row["label_name"] == name for row in rows) for name in ACTIONS}
    print(json.dumps({"output": str(args.output), "examples": len(rows), "labels": counts}, indent=2))


if __name__ == "__main__":
    main()
