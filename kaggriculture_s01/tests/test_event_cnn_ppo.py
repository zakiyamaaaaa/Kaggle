import math

from kaggriculture_agent.event_cnn_ppo import (
    ACTIONS,
    EVENT_FEATURES,
    EVENT_FEATURES_V2,
    EVENT_SCHEMA_V2,
    ITEMS,
    encode_event,
    event_feature_names,
    feature_schema_from_artifact,
)
from test_macro_rl import observation


def test_event_encoder_schema_and_item_identity():
    obs = observation(step=600)
    obs["market"]["inventory"] = {"MILK": 40}
    image, values = encode_event(obs, "MILK", 20, 30, 4, 120.0, 612, 34)
    assert len(image) == 10 and len(image[0]) == 10
    assert len(values) == 9 + len(EVENT_FEATURES)
    assert values[9 + ITEMS.index("MILK")] == 1.0
    assert len(ACTIONS) == 3


def test_v1_default_and_explicit_encoding_are_identical():
    obs = observation(step=600)
    obs["market"]["inventory"] = {"MILK": 1600}
    default = encode_event(obs, "MILK", 20, 30, 4, 120.0, 612, 34)
    explicit = encode_event(obs, "MILK", 20, 30, 4, 120.0, 612, 34, schema=1)
    assert default == explicit
    # The historical clip is intentionally retained only in v1.
    assert default[1][-2] == 3.0
    assert feature_schema_from_artifact({"schema": 1}) == 1


def test_v2_has_non_saturating_inventory_and_scale_aware_features():
    low = observation(step=600)
    high = observation(step=600)
    low["market"]["inventory"] = {"MILK": 800}
    high["market"]["inventory"] = {"MILK": 1600}
    _, low_values = encode_event(
        low, "MILK", 20, 30, 4, 120.0, 612, 34, schema=EVENT_SCHEMA_V2
    )
    _, high_values = encode_event(
        high, "MILK", 20, 30, 4, 120.0, 612, 34, feature_schema="v2"
    )
    names = ("day", "hour", "own_cash", "rival_cash", "cash_margin", "wheat_price",
             "milk_price", "wool_price", "melon_price") + EVENT_FEATURES_V2
    assert len(high_values) == len(names)
    assert tuple(names[9:]) == event_feature_names(2)
    market_index = names.index("market_inventory_log")
    assert high_values[market_index] > low_values[market_index]
    assert math.isfinite(high_values[market_index])
    assert high_values[names.index("exposure_per_unit")] == 120.0 / 20.0 / 200.0
    assert high_values[names.index("net_stock_ratio")] == 30.0 / 34.0
    assert feature_schema_from_artifact({"schema": 2}) == 2
    assert feature_schema_from_artifact({"scalars": names}) == 2


def test_event_wrapper_loads_with_default_full_decider():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "experiments/omw-event-cnn-ppo-v1/main.py"
    spec = importlib.util.spec_from_file_location("event_wrapper_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.agent)
    assert module._OR3_DECIDER(None) == 2
