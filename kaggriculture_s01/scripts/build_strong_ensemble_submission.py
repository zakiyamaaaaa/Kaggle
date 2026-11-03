#!/usr/bin/env python3
"""Build a self-contained Kaggriculture strong-action ensemble archive."""

from __future__ import annotations

import argparse
import hashlib
import textwrap
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE_ZIP = ROOT / "submissions" / "kaggriculture-candidate-early-milk-v1-ready.zip"
INDEX = ROOT / "outputs" / "public_strategy_pipeline" / "2026-09" / "proposal_index.json"
MODEL = ROOT / "outputs" / "public_strategy_pipeline" / "2026-09" / "behavior_model" / "model.joblib"
DEFAULT_OUTPUT = ROOT / "submissions" / "kaggriculture-strong-ensemble-v1.zip"

RUNTIME = textwrap.dedent(
    r'''

    # Conservative public-data strong-action ensemble.
    _ensemble_candidate_agent = agent
    try:
        import statistics as _ensemble_statistics
        from functools import lru_cache as _ensemble_lru_cache
        from pathlib import Path as _ensemble_Path
        import joblib as _ensemble_joblib
        import numpy as _ensemble_numpy
        import pandas as _ensemble_pandas
    except Exception:
        _ensemble_statistics = None
        _ensemble_lru_cache = lambda **kwargs: (lambda fn: fn)
        _ensemble_Path = None
        _ensemble_joblib = None
        _ensemble_numpy = None
        _ensemble_pandas = None

    _ENSEMBLE_SAFE_ACTIONS = {
        "PASS", "NORTH", "SOUTH", "EAST", "WEST", "CARE", "WATER", "FEED", "HARVEST", "DIG",
    }
    _ENSEMBLE_FEATURES = [
        "own_money", "opponent_money", "own_farmer_x", "own_farmer_y",
        "opponent_farmer_x", "opponent_farmer_y", "own_hands_count", "opponent_hands_count",
        "own_open_tile_count", "opponent_open_tile_count", "own_locked_tile_count",
        "opponent_locked_tile_count", "own_planted_tile_count", "opponent_planted_tile_count",
        "own_watered_tile_count", "opponent_watered_tile_count", "own_unlocked_quadrant_count",
        "opponent_unlocked_quadrant_count", "own_hires_today", "opponent_hires_today",
        "own_seed_total", "opponent_seed_total", "own_shed_total", "opponent_shed_total",
        "own_inventory_total", "opponent_inventory_total", "market_inventory_total",
        "market_mean_price", "market_min_price", "market_max_price", "town_unlocked_shop_count",
        "own_seed_wheat", "own_shed_wheat", "market_inventory_wheat", "market_price_wheat",
        "own_seed_fertilizer", "own_shed_fertilizer", "market_inventory_fertilizer", "market_price_fertilizer",
        "own_seed_melon", "own_shed_melon", "market_inventory_melon", "market_price_melon",
        "own_seed_milk", "own_shed_milk", "market_inventory_milk", "market_price_milk",
        "own_seed_strawberry", "own_shed_strawberry", "market_inventory_strawberry", "market_price_strawberry",
        "own_seed_wool", "own_shed_wool", "market_inventory_wool", "market_price_wool",
        "phase", "hours_remaining", "market_price_spread", "own_inventory_share", "own_cash_share",
        "inventory_advantage",
    ]

    def _ensemble_get(value, key, default=None):
        if isinstance(value, dict):
            return value.get(key, default)
        return getattr(value, key, default)

    def _ensemble_num(value):
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    def _ensemble_inv_total(value):
        if not value:
            return 0
        try:
            return sum(int(_ensemble_num(item)) for item in value.values())
        except AttributeError:
            return 0

    def _ensemble_inv_item(value, item):
        return int(_ensemble_num(_ensemble_get(value, item, 0)))

    def _ensemble_tile_counts(farm):
        opened = locked = planted = watered = 0
        for row in _ensemble_get(farm, "tiles", []) or []:
            for tile in row or []:
                if tile == "LOCKED":
                    locked += 1
                else:
                    opened += 1
                    if isinstance(tile, dict) or hasattr(tile, "get"):
                        planted += 1
                        if bool(_ensemble_get(tile, "watered_today", False)):
                            watered += 1
        return opened, locked, planted, watered

    def _ensemble_farm_features(farm, private):
        opened, locked, planted, watered = _ensemble_tile_counts(farm)
        farmer = _ensemble_get(farm, "farmer", []) or []
        inventories = _ensemble_get(private, "inventories", []) or []
        return {
            "money": _ensemble_num(_ensemble_get(farm, "money", 0)),
            "farmer_x": int(_ensemble_num(farmer[0])) if len(farmer) > 0 else 0,
            "farmer_y": int(_ensemble_num(farmer[1])) if len(farmer) > 1 else 0,
            "hands_count": len(_ensemble_get(farm, "hands", []) or []),
            "open_tile_count": opened, "locked_tile_count": locked,
            "planted_tile_count": planted, "watered_tile_count": watered,
            "unlocked_quadrant_count": len(_ensemble_get(farm, "unlocked_quadrants", []) or []),
            "hires_today": int(_ensemble_num(_ensemble_get(farm, "hires_today", 0))),
            "seed_total": _ensemble_inv_total(_ensemble_get(private, "seeds", {})),
            "shed_total": _ensemble_inv_total(_ensemble_get(private, "shed", {})),
            "inventory_total": sum(_ensemble_inv_total(item) for item in inventories),
        }

    def _ensemble_state_features(obs):
        farms = _ensemble_get(obs, "farms", []) or []
        private = _ensemble_get(obs, "private", {}) or {}
        own = _ensemble_farm_features(farms[0] if farms else {}, private)
        other = _ensemble_farm_features(farms[1] if len(farms) > 1 else {}, {})
        market = _ensemble_get(obs, "market", {}) or {}
        inventory = _ensemble_get(market, "inventory", {}) or {}
        prices_map = _ensemble_get(market, "prices", {}) or {}
        prices = [_ensemble_num(v) for v in prices_map.values()]
        row = {
            "own_money": own["money"], "opponent_money": other["money"],
            "own_farmer_x": own["farmer_x"], "own_farmer_y": own["farmer_y"],
            "opponent_farmer_x": other["farmer_x"], "opponent_farmer_y": other["farmer_y"],
            "own_hands_count": own["hands_count"], "opponent_hands_count": other["hands_count"],
            "own_open_tile_count": own["open_tile_count"], "opponent_open_tile_count": other["open_tile_count"],
            "own_locked_tile_count": own["locked_tile_count"], "opponent_locked_tile_count": other["locked_tile_count"],
            "own_planted_tile_count": own["planted_tile_count"], "opponent_planted_tile_count": other["planted_tile_count"],
            "own_watered_tile_count": own["watered_tile_count"], "opponent_watered_tile_count": other["watered_tile_count"],
            "own_unlocked_quadrant_count": own["unlocked_quadrant_count"], "opponent_unlocked_quadrant_count": other["unlocked_quadrant_count"],
            "own_hires_today": own["hires_today"], "opponent_hires_today": other["hires_today"],
            "own_seed_total": own["seed_total"], "opponent_seed_total": other["seed_total"],
            "own_shed_total": own["shed_total"], "opponent_shed_total": other["shed_total"],
            "own_inventory_total": own["inventory_total"], "opponent_inventory_total": other["inventory_total"],
            "market_inventory_total": _ensemble_inv_total(inventory),
            "market_mean_price": _ensemble_statistics.fmean(prices) if prices else 0.0,
            "market_min_price": min(prices) if prices else 0.0,
            "market_max_price": max(prices) if prices else 0.0,
            "town_unlocked_shop_count": len(_ensemble_get(_ensemble_get(obs, "town", {}), "unlocked_shops", []) or []),
        }
        seeds = _ensemble_get(private, "seeds", {}) or {}
        shed = _ensemble_get(private, "shed", {}) or {}
        items = ("WHEAT", "FERTILIZER", "MELON", "MILK", "STRAWBERRY", "WOOL")
        for item in items:
            suffix = item.lower()
            row[f"own_seed_{suffix}"] = _ensemble_inv_item(seeds, item)
            row[f"own_shed_{suffix}"] = _ensemble_inv_item(shed, item)
            row[f"market_inventory_{suffix}"] = _ensemble_inv_item(inventory, item)
            row[f"market_price_{suffix}"] = _ensemble_num(_ensemble_get(prices_map, item, 0))
        step = int(_ensemble_num(_ensemble_get(obs, "step", 0)))
        day = int(_ensemble_num(_ensemble_get(obs, "day", 0)))
        row["phase"] = day // 10
        row["hours_remaining"] = max(0, 720 - step)
        row["market_price_spread"] = row["market_max_price"] - row["market_min_price"]
        row["own_inventory_share"] = row["own_inventory_total"] / (row["own_inventory_total"] + row["market_inventory_total"] + 1.0)
        row["own_cash_share"] = row["own_money"] / (row["own_money"] + row["opponent_money"] + 1.0)
        row["inventory_advantage"] = row["own_inventory_total"] - row["opponent_inventory_total"]
        return row

    @(_ensemble_lru_cache(maxsize=1) if _ensemble_lru_cache else (lambda fn: fn))
    def _ensemble_artifacts():
        base = _ensemble_Path(__file__).resolve().parent
        with (base / "proposal_index.json").open(encoding="utf-8") as handle:
            index = json.load(handle)
        model = _ensemble_joblib.load(base / "behavior_model.joblib")
        return index, model

    def _ensemble_proposal(obs, incumbent):
        step = int(_ensemble_num(_ensemble_get(obs, "step", 0)))
        day = int(_ensemble_num(_ensemble_get(obs, "day", 0)))
        if step % 12 != 0 or day >= 20 or incumbent.get("hands") or incumbent.get("market"):
            return incumbent
        index, artifact = _ensemble_artifacts()
        state = _ensemble_state_features(obs)
        columns = list(artifact["feature_columns"])
        frame = _ensemble_pandas.DataFrame([state], columns=columns)
        probabilities = artifact["model"].predict_proba(frame)[0]
        labels = list(artifact["labels"])
        phase = min(1, day // 10)
        means = _ensemble_numpy.asarray(index["means"], dtype=float)
        stds = _ensemble_numpy.maximum(_ensemble_numpy.asarray(index["stds"], dtype=float), 1e-6)
        vector = _ensemble_numpy.asarray([float(state[name]) for name in index["state_features"]])
        normalized = (vector - means) / stds
        for action_index in probabilities.argsort()[::-1][:3]:
            if float(probabilities[action_index]) < 0.20:
                continue
            label = labels[action_index]
            templates = index["groups"].get(f"{phase}|{label}", [])
            templates = [t for t in templates if t.get("safe_empty_bundle")]
            if not templates or label not in _ENSEMBLE_SAFE_ACTIONS:
                continue
            template = min(
                templates,
                key=lambda t: float(_ensemble_numpy.mean(((
                    _ensemble_numpy.asarray(t["features"], dtype=float) - means
                ) / stds - normalized) ** 2)),
            )
            action = template.get("action") or {}
            if (
                isinstance(action, dict)
                and isinstance(action.get("farmer"), list)
                and action["farmer"] == [label]
                and not action.get("hands")
                and not action.get("market")
            ):
                return {"farmer": [label], "hands": [], "market": []}
        return incumbent

    def agent(obs):
        incumbent = _ensemble_candidate_agent(obs)
        try:
            return _ensemble_proposal(obs, incumbent)
        except Exception:
            return incumbent
    '''
)


def build(output: Path) -> tuple[str, str]:
    with zipfile.ZipFile(BASE_ZIP) as archive:
        source = archive.read("main.py")
    main = source + RUNTIME.encode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("main.py", main)
        archive.write(INDEX, "proposal_index.json")
        archive.write(MODEL, "behavior_model.joblib")
    return hashlib.sha256(main).hexdigest(), hashlib.sha256(output.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    main_hash, archive_hash = build(args.output)
    print(f"output={args.output.resolve()}")
    print(f"main_sha256={main_hash}")
    print(f"zip_sha256={archive_hash}")


if __name__ == "__main__":
    main()
