"""Inference for an event-driven CNN actor-critic over OMW sell opportunities."""

from __future__ import annotations

from math import exp, log1p, tanh
from typing import Any

from .cnn_ppo import CHANNELS, encode_observation


ITEMS = ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "EGG", "MILK", "WOOL", "FERTILIZER")
ACTIONS = ("skip", "half", "full")
EVENT_SCHEMA_V1 = 1
EVENT_SCHEMA_V2 = 2
SUPPORTED_EVENT_SCHEMAS = (EVENT_SCHEMA_V1, EVENT_SCHEMA_V2)

_ITEM_FEATURES = tuple(f"item_{item.lower()}" for item in ITEMS)
_COMMON_EVENT_FEATURES = (
    "quantity",
    "net_rival_batch",
    "demand_recovery",
    "exposure",
    "sale_horizon",
    "current_price",
)
EVENT_FEATURES_V1 = (
    *_ITEM_FEATURES,
    *_COMMON_EVENT_FEATURES,
    "market_inventory",
    "rival_stock",
)
EVENT_FEATURES_V2 = (
    *_ITEM_FEATURES,
    *_COMMON_EVENT_FEATURES,
    "market_inventory_log",
    "rival_stock",
    "exposure_per_unit",
    "net_stock_ratio",
)
EVENT_FEATURES_BY_SCHEMA = {
    EVENT_SCHEMA_V1: EVENT_FEATURES_V1,
    EVENT_SCHEMA_V2: EVENT_FEATURES_V2,
}
# Keep the historical import and default encoder behavior intact.  New callers
# should select a schema explicitly with ``schema=EVENT_SCHEMA_V2``.
EVENT_FEATURES = EVENT_FEATURES_V1


def normalize_event_schema(schema: int | str | None) -> int:
    """Return a supported event feature schema number.

    Integer versions and human-readable ``"v1"``/``"v2"`` values are both
    accepted so command-line options can be passed through directly.
    """

    if schema is None:
        return EVENT_SCHEMA_V1
    if isinstance(schema, str):
        value = schema.strip().lower()
        if value.startswith("v"):
            value = value[1:]
        try:
            schema = int(value)
        except ValueError as exc:
            raise ValueError(f"unsupported event feature schema: {schema!r}") from exc
    try:
        version = int(schema)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"unsupported event feature schema: {schema!r}") from exc
    if version not in SUPPORTED_EVENT_SCHEMAS:
        raise ValueError(
            f"unsupported event feature schema: {version!r}; "
            f"expected one of {SUPPORTED_EVENT_SCHEMAS}"
        )
    return version


def event_feature_names(schema: int | str | None = EVENT_SCHEMA_V1) -> tuple[str, ...]:
    """Return the ordered event feature names for ``schema``."""

    return EVENT_FEATURES_BY_SCHEMA[normalize_event_schema(schema)]


def feature_schema_from_artifact(model: dict[str, Any]) -> int:
    """Resolve the encoder schema recorded in a model artifact.

    Existing v1 artifacts only contain ``schema`` and therefore continue to
    resolve to v1.  ``feature_schema`` is accepted for forward-compatible
    artifacts that use another top-level schema field for their file format;
    scalar-only artifacts fall back to the v2 inventory feature name.
    """

    schema = model.get("feature_schema", model.get("schema"))
    if schema is None:
        # A few lightweight artifacts only persist their ordered scalar names;
        # infer v2 from its non-v1 inventory feature in that case.
        recorded_scalars = tuple(model.get("scalars", ()))
        schema = (
            EVENT_SCHEMA_V2
            if "market_inventory_log" in recorded_scalars
            else EVENT_SCHEMA_V1
        )
    resolved = normalize_event_schema(schema)
    recorded_features = model.get("event_features")
    if recorded_features is not None and tuple(recorded_features) != event_feature_names(resolved):
        raise ValueError(
            "model event feature names do not match its feature schema: "
            f"{recorded_features!r} != {list(event_feature_names(resolved))!r}"
        )
    return resolved


# Historical alias for callers that refer to the model rather than the
# artifact format.
event_schema_from_model = feature_schema_from_artifact


def _encode_event_v1(
    observation: dict[str, Any],
    item: str,
    quantity: int,
    net_batch: int,
    recovery: int,
    exposure: float,
    first_sale: int,
    rival_stock: int,
):
    """The original encoder kept in a dedicated branch for exact parity."""

    image, base = encode_observation(observation)
    step = int(observation.get("step", 0))
    market = observation.get("market") or {}
    prices = market.get("prices") or {}
    inventory = market.get("inventory") or {}
    event = [float(item == name) for name in ITEMS]
    event.extend(
        [
            min(3.0, max(0, quantity) / 50.0),
            min(3.0, max(0, net_batch) / 100.0),
            min(3.0, max(0, recovery) / 100.0),
            min(5.0, max(0.0, exposure) / 500.0),
            min(2.0, max(0, first_sale - step) / 24.0),
            min(3.0, float(prices.get(item, 0) or 0) / 200.0),
            min(3.0, float(inventory.get(item, 0) or 0) / 200.0),
            min(3.0, max(0, rival_stock) / 100.0),
        ]
    )
    return image, base + event


def _encode_event_v2(
    observation: dict[str, Any],
    item: str,
    quantity: int,
    net_batch: int,
    recovery: int,
    exposure: float,
    first_sale: int,
    rival_stock: int,
):
    """Encode event context with scale-aware market signals.

    Inventory uses a log transform normalized at the historical 200-unit
    scale, so values above that level remain distinguishable.  Exposure per
    unit is normalized by the same 200-price scale, while net stock ratio is
    the observable remaining rival stock share.
    """

    image, base = encode_observation(observation)
    step = int(observation.get("step", 0))
    market = observation.get("market") or {}
    prices = market.get("prices") or {}
    inventory = market.get("inventory") or {}
    inventory_value = max(0.0, float(inventory.get(item, 0) or 0))
    quantity_value = max(1.0, float(quantity))
    rival_stock_value = max(1.0, float(rival_stock))
    event = [float(item == name) for name in ITEMS]
    event.extend(
        [
            min(3.0, max(0, quantity) / 50.0),
            min(3.0, max(0, net_batch) / 100.0),
            min(3.0, max(0, recovery) / 100.0),
            min(5.0, max(0.0, exposure) / 500.0),
            min(2.0, max(0, first_sale - step) / 24.0),
            min(3.0, float(prices.get(item, 0) or 0) / 200.0),
            log1p(inventory_value) / log1p(200.0),
            min(3.0, max(0, rival_stock) / 100.0),
            max(0.0, float(exposure)) / quantity_value / 200.0,
            max(0.0, float(net_batch)) / rival_stock_value,
        ]
    )
    return image, base + event


def encode_event(
    observation: dict[str, Any],
    item: str,
    quantity: int,
    net_batch: int,
    recovery: int,
    exposure: float,
    first_sale: int,
    rival_stock: int,
    schema: int | str = EVENT_SCHEMA_V1,
    *,
    feature_schema: int | str | None = None,
):
    """Encode an event using an explicitly selected feature schema.

    The default remains v1 for callers and existing model artifacts.  The
    keyword alias ``feature_schema`` makes the selection self-documenting in
    training/data-generation code.
    """

    if feature_schema is not None:
        requested = normalize_event_schema(schema)
        selected = normalize_event_schema(feature_schema)
        if requested != EVENT_SCHEMA_V1 and requested != selected:
            raise ValueError(f"conflicting event feature schemas: {schema!r} and {feature_schema!r}")
        schema = selected
    resolved = normalize_event_schema(schema)
    if resolved == EVENT_SCHEMA_V1:
        return _encode_event_v1(
            observation, item, quantity, net_batch, recovery, exposure, first_sale, rival_stock
        )
    return _encode_event_v2(
        observation, item, quantity, net_batch, recovery, exposure, first_sale, rival_stock
    )


def policy_value(model: dict[str, Any], image, scalars) -> tuple[list[float], float]:
    conv = model["conv"]
    pooled = []
    for filter_index, kernel in enumerate(conv["weights"]):
        total = 0.0
        for row in range(8):
            for column in range(8):
                value = float(conv["bias"][filter_index])
                for channel in range(len(CHANNELS)):
                    for dy in range(3):
                        for dx in range(3):
                            value += image[row + dy][column + dx][channel] * kernel[channel][dy][dx]
                total += max(0.0, value)
        pooled.append(total / 64.0)
    shared = pooled + list(scalars)
    hidden = [
        tanh(float(bias) + sum(float(weight) * value for weight, value in zip(row, shared)))
        for row, bias in zip(model["hidden"]["weights"], model["hidden"]["bias"])
    ]
    logits = [
        float(bias) + sum(float(weight) * value for weight, value in zip(row, hidden))
        for row, bias in zip(model["policy"]["weights"], model["policy"]["bias"])
    ]
    peak = max(logits)
    scores = [exp(max(-40.0, min(40.0, value - peak))) for value in logits]
    total = sum(scores)
    probs = [score / total for score in scores]
    value = float(model["value"]["bias"]) + sum(
        float(weight) * value for weight, value in zip(model["value"]["weights"], hidden)
    )
    return probs, value


def make_decider(model: dict[str, Any], telemetry: dict[str, Any] | None = None):
    schema = feature_schema_from_artifact(model)

    def decide(observation, item, quantity, net_batch, recovery, exposure, first_sale, rival_stock):
        image, scalars = encode_event(
            observation,
            item,
            quantity,
            net_batch,
            recovery,
            exposure,
            first_sale,
            rival_stock,
            schema=schema,
        )
        probs, _ = policy_value(model, image, scalars)
        action = max(range(len(ACTIONS)), key=lambda index: (probs[index], -index))
        if telemetry is not None:
            telemetry[ACTIONS[action]] = telemetry.get(ACTIONS[action], 0) + 1
            telemetry[f"item_{item}"] = telemetry.get(f"item_{item}", 0) + 1
        return action

    return decide
