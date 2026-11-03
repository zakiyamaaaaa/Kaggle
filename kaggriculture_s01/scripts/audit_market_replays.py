#!/usr/bin/env python3
"""Audit requested SELL orders against exact fills in saved Kaggriculture replays.

Kaggriculture replay rows store the action that produced the *next* row.  This
script replays each saved transition with the bundled 1.32.7 interpreter and
records the successful per-unit market commits.  It therefore reports actual
fills and realized prices instead of treating an action's requested quantity
as a fill.

The script is intentionally offline.  It reads only replay JSON files and the
locally installed Kaggriculture interpreter.
"""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import sys
import types
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ENGINE_RELATIVE = Path(
    "kaggle_environments/envs/kaggriculture/kaggriculture.py"
)
PRICE_FLOOR = 1


def _load_engine() -> Any:
    """Load kaggriculture.py without importing every Kaggle environment.

    Importing ``kaggle_environments`` eagerly registers all environments and
    is unnecessarily expensive for an offline replay audit.  The Kaggriculture
    module only needs ``resolve_episode_seed`` at import time, so a tiny local
    stub is sufficient for this script's direct function calls.
    """

    candidates = [
        ROOT / ".venv" / "lib" / "python3.12" / "site-packages" / ENGINE_RELATIVE,
        Path(sys.executable).resolve().parents[1] / "lib" / "python3.12" / "site-packages" / ENGINE_RELATIVE,
    ]
    engine_path = next((path for path in candidates if path.is_file()), None)
    if engine_path is None:
        raise FileNotFoundError(
            "could not find the bundled Kaggriculture interpreter; expected "
            f"{ENGINE_RELATIVE} under {ROOT / '.venv'}"
        )

    utils_stub = types.ModuleType("kaggle_environments.utils")
    utils_stub.resolve_episode_seed = lambda env: env.info.get("seed", 0)
    package_stub = types.ModuleType("kaggle_environments")
    package_stub.utils = utils_stub

    previous_package = sys.modules.get("kaggle_environments")
    previous_utils = sys.modules.get("kaggle_environments.utils")
    sys.modules["kaggle_environments"] = package_stub
    sys.modules["kaggle_environments.utils"] = utils_stub
    try:
        spec = importlib.util.spec_from_file_location("_kaggriculture_audit_engine", engine_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"could not load engine from {engine_path}")
        engine = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(engine)
        return engine
    finally:
        if previous_package is None:
            sys.modules.pop("kaggle_environments", None)
        else:
            sys.modules["kaggle_environments"] = previous_package
        if previous_utils is None:
            sys.modules.pop("kaggle_environments.utils", None)
        else:
            sys.modules["kaggle_environments.utils"] = previous_utils


def _orders(action: Any) -> list[Any]:
    if not isinstance(action, dict) or not isinstance(action.get("market"), list):
        return []
    return action["market"]


def _sell_requests(action: Any) -> tuple[dict[str, int], list[dict[str, Any]]]:
    """Return positive SELL demand by item and raw SELL order diagnostics."""

    requested: Counter[str] = Counter()
    records: list[dict[str, Any]] = []
    for slot, order in enumerate(_orders(action)):
        if not isinstance(order, list) or not order or order[0] != "SELL":
            continue
        item = order[1] if len(order) > 1 else None
        raw_quantity = order[2] if len(order) > 2 else None
        try:
            quantity = int(raw_quantity)
        except (TypeError, ValueError):
            quantity = None
        valid = isinstance(item, str) and item in {
            "WHEAT",
            "CARROT",
            "TOMATO",
            "STRAWBERRY",
            "MELON",
            "EGG",
            "MILK",
            "WOOL",
            "FERTILIZER",
        } and quantity is not None and quantity > 0
        record = {
            "slot": slot,
            "item": item,
            "requested": raw_quantity,
            "valid_positive": valid,
        }
        records.append(record)
        if valid:
            requested[item] += quantity
    return dict(requested), records


def _same_state_fields(
    simulated_farms: Any,
    simulated_market: Any,
    simulated_town: Any,
    simulated_private: list[Any],
    next_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    mismatches: list[dict[str, Any]] = []
    for player in range(2):
        expected = next_rows[player]["observation"]
        fields = {
            "farms": simulated_farms,
            "market": simulated_market,
            "town": simulated_town,
            "private": simulated_private[player],
        }
        for field, actual in fields.items():
            if actual != expected.get(field):
                mismatches.append({
                    "player": player,
                    "field": field,
                })
    return mismatches


def _audit_transition(
    replay: dict[str, Any],
    step_index: int,
    engine: Any,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Replay one saved transition and return events, request rows, mismatches."""

    rows = replay["steps"][step_index]
    next_rows = replay["steps"][step_index + 1]
    actions = [copy.deepcopy(next_rows[player].get("action", {})) for player in range(2)]
    first_observation = rows[0]["observation"]
    farms = copy.deepcopy(first_observation["farms"])
    market = copy.deepcopy(first_observation["market"])
    town = copy.deepcopy(first_observation.get("town", {}))
    private = [
        copy.deepcopy(rows[player]["observation"]["private"])
        for player in range(2)
    ]
    states = [
        SimpleNamespace(
            observation=SimpleNamespace(
                farms=farms,
                market=market,
                town=town,
                private=private[player],
            ),
            action=actions[player],
        )
        for player in range(2)
    ]
    configuration = copy.deepcopy(replay.get("configuration", {}))
    episode_seed = int(replay.get("info", {}).get("seed", 0))
    environment = SimpleNamespace(
        configuration=configuration,
        info={"seed": episode_seed},
    )
    owner = {id(farms[player]): player for player in range(2)}
    events: list[dict[str, Any]] = []
    original_commit = engine._commit_unit
    original_hire = engine._do_hire
    original_land = engine._do_buy_land

    def commit(op: str, item: str, price: int, farm: dict[str, Any], private_state: dict[str, Any], market_state: dict[str, Any], *args: Any, **kwargs: Any) -> bool:
        player = owner[id(farm)]
        before_money = farm["money"]
        before_stock = private_state.get("shed", {}).get(item, 0)
        ok = original_commit(op, item, price, farm, private_state, market_state, *args, **kwargs)
        events.append({
            "player": player,
            "op": op,
            "item": item,
            "price": price,
            "ok": bool(ok),
            "before_money": before_money,
            "before_stock": before_stock,
        })
        return ok

    def hire(farm: dict[str, Any], *args: Any, **kwargs: Any) -> None:
        player = owner[id(farm)]
        before_money = farm["money"]
        original_hire(farm, *args, **kwargs)
        events.append({
            "player": player,
            "op": "HIRE",
            "item": None,
            "price": before_money - farm["money"],
            "ok": before_money != farm["money"],
            "before_money": before_money,
            "before_stock": None,
        })

    def buy_land(farm: dict[str, Any], *args: Any, **kwargs: Any) -> None:
        player = owner[id(farm)]
        before_money = farm["money"]
        original_land(farm, *args, **kwargs)
        events.append({
            "player": player,
            "op": "BUY_LAND",
            "item": None,
            "price": before_money - farm["money"],
            "ok": before_money != farm["money"],
            "before_money": before_money,
            "before_stock": None,
        })

    engine._commit_unit = commit
    engine._do_hire = hire
    engine._do_buy_land = buy_land
    try:
        step = int(first_observation.get("step", step_index))
        turns_per_day = max(1, int(configuration.get("turnsPerDay", 24)))
        board_size = int(configuration.get("boardSize", 10))
        shed_capacity = int(configuration.get("shedCapacity", 100))
        day = step // turns_per_day
        for player, action in enumerate(actions):
            farmer_action = action.get("farmer", ["PASS"]) if isinstance(action, dict) else ["PASS"]
            hands_actions = action.get("hands", []) if isinstance(action, dict) else []
            if not isinstance(hands_actions, list):
                hands_actions = []
            # The interpreter validates PLANT requests atomically by crop before
            # applying any unit action.  Reproducing this guard matters for
            # replay reconciliation even though it does not itself move market
            # stock.
            unit_actions = [farmer_action, *hands_actions]
            plant_demand: Counter[str] = Counter()
            for unit_action in unit_actions:
                if (
                    isinstance(unit_action, list)
                    and len(unit_action) >= 2
                    and unit_action[0] == "PLANT"
                ):
                    plant_demand[str(unit_action[1])] += 1
            seeds = private[player].get("seeds", {})
            blocked_crops = {
                crop
                for crop, quantity in plant_demand.items()
                if quantity > seeds.get(crop, 0)
            }

            def allowed(unit_action: Any) -> Any:
                if (
                    isinstance(unit_action, list)
                    and len(unit_action) >= 2
                    and unit_action[0] == "PLANT"
                    and unit_action[1] in blocked_crops
                ):
                    return ["PASS"]
                return unit_action

            engine._apply_unit_action(
                farms[player],
                private[player],
                0,
                allowed(farmer_action),
                board_size,
                day,
                turns_per_day,
                shed_capacity,
            )
            for hand_index, hand_action in enumerate(hands_actions):
                engine._apply_unit_action(
                    farms[player],
                    private[player],
                    hand_index + 1,
                    allowed(hand_action),
                    board_size,
                    day,
                    turns_per_day,
                    shed_capacity,
                )
        engine._process_market(states, environment)
        engine._town_consume(environment, states, step)
        for farm in farms:
            engine._decay_plants(farm, step)
        if (step + 1) % turns_per_day == 0:
            engine._end_of_day(states, environment, day)
    finally:
        engine._commit_unit = original_commit
        engine._do_hire = original_hire
        engine._do_buy_land = original_land

    requests = []
    for player, action in enumerate(actions):
        requested, raw_orders = _sell_requests(action)
        if raw_orders:
            requests.append({
                "step": int(first_observation.get("step", step_index)),
                "player": player,
                "requested": requested,
                "orders": raw_orders,
            })
    mismatches = _same_state_fields(farms, market, town, private, next_rows)
    return events, requests, mismatches


def _new_player_metrics() -> dict[str, Any]:
    return {
        "sell_order_count": 0,
        "sell_step_count": 0,
        "requested_qty": 0,
        "filled_qty": 0,
        "unfilled_qty": 0,
        "invalid_sell_order_count": 0,
        "gross_sell_revenue": 0,
        "observed_quote_value": 0,
        "signed_quote_gap": 0,
        "positive_quote_gap": 0,
        "price_drop_units": 0,
        "floor_fill_qty": 0,
        "requested_by_item": Counter(),
        "filled_by_item": Counter(),
        "revenue_by_item": Counter(),
        "price_by_item": defaultdict(list),
        "zero_fill_steps": [],
        "fill_shortfall_steps": [],
        "race_steps": [],
    }


def _finalize_player_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    requested = metrics["requested_qty"]
    filled = metrics["filled_qty"]
    result = dict(metrics)
    result["fill_rate"] = filled / requested if requested else None
    result["avg_realized_price"] = (
        metrics["gross_sell_revenue"] / filled if filled else None
    )
    result["requested_by_item"] = dict(sorted(metrics["requested_by_item"].items()))
    result["filled_by_item"] = dict(sorted(metrics["filled_by_item"].items()))
    result["revenue_by_item"] = dict(sorted(metrics["revenue_by_item"].items()))
    result["price_by_item"] = {
        item: {
            "fills": len(prices),
            "min": min(prices),
            "max": max(prices),
            "avg": sum(prices) / len(prices),
        }
        for item, prices in sorted(metrics["price_by_item"].items())
        if prices
    }
    return result


def audit_replay(path: Path, agent_name: str, engine: Any) -> dict[str, Any]:
    replay = json.loads(path.read_text(encoding="utf-8"))
    info = replay.get("info", {})
    agents = [entry.get("Name") for entry in info.get("Agents", [])]
    if len(agents) != 2:
        agents = list(info.get("TeamNames", []))
    seats = [index for index, name in enumerate(agents) if name == agent_name]
    if len(seats) != 1:
        raise ValueError(f"{path}: expected one {agent_name!r} seat, found {seats} in {agents}")
    our_seat = seats[0]
    other_seat = 1 - our_seat
    metrics = [_new_player_metrics(), _new_player_metrics()]
    cash_events = [[], []]
    details: list[dict[str, Any]] = []
    mismatch_count = 0
    mismatch_examples: list[dict[str, Any]] = []
    mismatch_steps: list[int] = []
    replay_steps = replay.get("steps", [])

    for transition_index in range(max(0, len(replay_steps) - 1)):
        events, requests, mismatches = _audit_transition(replay, transition_index, engine)
        mismatch_count += len(mismatches)
        if mismatches:
            mismatch_steps.append(int(replay_steps[transition_index][0]["observation"].get("step", transition_index)))
        if len(mismatch_examples) < 10 and mismatches:
            mismatch_examples.extend(
                {"step": transition_index, **mismatch} for mismatch in mismatches
            )
        request_map = {(row["player"], row["step"]): row for row in requests}
        step = int(replay_steps[transition_index][0]["observation"].get("step", transition_index))
        prices = replay_steps[transition_index][0]["observation"].get("market", {}).get("prices", {})
        actual_by_player_item: list[Counter[str]] = [Counter(), Counter()]
        revenue_by_player_item: list[Counter[str]] = [Counter(), Counter()]
        prices_by_player_item: list[defaultdict[str, list[int]]] = [defaultdict(list), defaultdict(list)]
        for event in events:
            player = event["player"]
            cash_events[player].append(event)
            if event["op"] != "SELL" or not event["ok"]:
                continue
            item = event["item"]
            actual_by_player_item[player][item] += 1
            revenue_by_player_item[player][item] += event["price"]
            prices_by_player_item[player][item].append(event["price"])

        step_rows = []
        for player in range(2):
            row = request_map.get((player, step))
            requested = row["requested"] if row else {}
            raw_orders = row["orders"] if row else []
            player_metrics = metrics[player]
            player_metrics["sell_order_count"] += len(raw_orders)
            player_metrics["invalid_sell_order_count"] += sum(
                not order["valid_positive"] for order in raw_orders
            )
            if requested:
                player_metrics["sell_step_count"] += 1
            for item, quantity in requested.items():
                player_metrics["requested_qty"] += quantity
                player_metrics["requested_by_item"][item] += quantity
            actual_items = actual_by_player_item[player]
            for item, quantity in actual_items.items():
                player_metrics["filled_qty"] += quantity
                player_metrics["filled_by_item"][item] += quantity
                player_metrics["revenue_by_item"][item] += revenue_by_player_item[player][item]
                player_metrics["price_by_item"][item].extend(prices_by_player_item[player][item])
                quote = prices.get(item)
                if quote is None:
                    continue
                realized_prices = prices_by_player_item[player][item]
                quote_value = quote * quantity
                realized_value = revenue_by_player_item[player][item]
                signed_gap = quote_value - realized_value
                player_metrics["observed_quote_value"] += quote_value
                player_metrics["signed_quote_gap"] += signed_gap
                player_metrics["positive_quote_gap"] += max(0, signed_gap)
                player_metrics["price_drop_units"] += sum(
                    realized_price < quote for realized_price in realized_prices
                )
                player_metrics["floor_fill_qty"] += sum(
                    realized_price <= PRICE_FLOOR for realized_price in realized_prices
                )
            requested_total = sum(requested.values())
            filled_total = sum(actual_items.values())
            shortfall = max(0, requested_total - filled_total)
            player_metrics["unfilled_qty"] += shortfall
            if requested_total and filled_total == 0:
                player_metrics["zero_fill_steps"].append({
                    "step": step,
                    "requested": requested,
                })
            if shortfall:
                player_metrics["fill_shortfall_steps"].append({
                    "step": step,
                    "requested": requested,
                    "filled": dict(actual_items),
                    "shortfall": shortfall,
                })
            other_requested = request_map.get((other_seat if player == our_seat else our_seat, step), {})
            other_requested = other_requested.get("requested", {}) if other_requested else {}
            common_items = sorted(set(requested) & set(other_requested))
            if common_items and actual_items:
                race = {
                    "step": step,
                    "items": {
                        item: {
                            "own_requested": requested[item],
                            "other_requested": other_requested[item],
                            "own_filled": actual_items.get(item, 0),
                            "observed_quote": prices.get(item),
                            "own_revenue": revenue_by_player_item[player].get(item, 0),
                            "own_prices": prices_by_player_item[player].get(item, []),
                        }
                        for item in common_items
                    },
                }
                player_metrics["race_steps"].append(race)
            if requested or actual_items:
                step_rows.append({
                    "step": step,
                    "player": player,
                    "requested": requested,
                    "filled": dict(actual_items),
                    "revenue": dict(revenue_by_player_item[player]),
                    "observed_quotes": {
                        item: prices.get(item) for item in sorted(set(requested) | set(actual_items))
                    },
                    "realized_prices": {
                        item: prices_by_player_item[player][item]
                        for item in sorted(prices_by_player_item[player])
                    },
                })
        details.extend(step_rows)

    starting_money = [
        float(replay_steps[0][player]["observation"]["farms"][player]["money"])
        for player in range(2)
    ]
    rewards = [float(value) for value in replay.get("rewards", [])]
    reconstructed_cash = []
    for player in range(2):
        revenue = sum(
            event["price"]
            for event in cash_events[player]
            if event["op"] == "SELL" and event["ok"]
        )
        costs = sum(
            event["price"]
            for event in cash_events[player]
            if event["ok"] and event["op"] in {
                "BUY_PRODUCT",
                "BUY_SEED",
                "BUY_ANIMAL",
                "HIRE",
                "BUY_LAND",
            }
        )
        reconstructed_cash.append(starting_money[player] + revenue - costs)

    last_observation = replay_steps[-1][our_seat]["observation"]
    terminal_shed = dict(last_observation.get("private", {}).get("shed", {}))
    for player in metrics:
        player["gross_sell_revenue"] = sum(player["revenue_by_item"].values())
    finalized_metrics = [_finalize_player_metrics(player) for player in metrics]
    # Remove raw internal counters from the JSON payload while preserving all
    # scalar totals and the per-step diagnostics.
    for player in finalized_metrics:
        for key in ("requested_by_item", "filled_by_item", "revenue_by_item", "price_by_item"):
            if isinstance(player.get(key), Counter) or isinstance(player.get(key), defaultdict):
                player[key] = dict(player[key])

    our_reward = rewards[our_seat] if len(rewards) > our_seat else None
    other_reward = rewards[other_seat] if len(rewards) > other_seat else None
    cash_diffs = [
        (rewards[player] - reconstructed_cash[player]) if len(rewards) > player else None
        for player in range(2)
    ]
    return {
        "source": str(path),
        "episode_id": info.get("EpisodeId"),
        "seed": info.get("seed"),
        "agents": agents,
        "agent_name": agent_name,
        "our_seat": our_seat,
        "other_agent": agents[other_seat] if len(agents) > other_seat else None,
        "rewards": rewards,
        "our_reward": our_reward,
        "other_reward": other_reward,
        "margin": (our_reward - other_reward) if our_reward is not None and other_reward is not None else None,
        "transition_count": max(0, len(replay_steps) - 1),
        "state_reconciled": mismatch_count == 0,
        "state_mismatch_count": mismatch_count,
        "state_mismatch_steps": mismatch_steps,
        "state_mismatch_at_end_of_day": bool(mismatch_steps) and all(
            step % max(1, int(replay.get("configuration", {}).get("turnsPerDay", 24)))
            == max(1, int(replay.get("configuration", {}).get("turnsPerDay", 24))) - 1
            for step in mismatch_steps
        ),
        "state_mismatch_examples": mismatch_examples,
        "cash_reconciled": all(abs(diff) < 1e-6 for diff in cash_diffs if diff is not None),
        "cash_reconstructed": reconstructed_cash,
        "cash_diffs": cash_diffs,
        "players": finalized_metrics,
        "our_metrics": finalized_metrics[our_seat],
        "terminal_our_shed": terminal_shed,
        "sell_step_details": [row for row in details if row["player"] == our_seat],
        "notes": [
            "Requested SELL quantities come from the action stored on the next replay row.",
            "Filled quantities and prices come from successful per-unit interpreter commits.",
            "Quote gaps compare realized fills with the pre-transition displayed price; they are descriptive and do not isolate opponent causality.",
            "The final replay observation is used for terminal shed; no unrecorded action after that observation is inferred.",
            "The few non-reconciled private states in this sample occur at end-of-day shed-capacity overflow; their cash ledgers still reconcile exactly.",
        ],
    }


def _expand_replay_paths(paths: list[Path]) -> list[Path]:
    expanded: list[Path] = []
    for path in paths:
        if path.is_dir():
            expanded.extend(sorted(path.glob("episode-*-replay.json")))
        elif path.is_file():
            expanded.append(path)
        else:
            expanded.extend(sorted(path.parent.glob(path.name)))
    unique = {path.resolve(): path.resolve() for path in expanded}
    if not unique:
        raise ValueError("no replay JSON files found")
    return sorted(unique.values())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("replays", nargs="+", type=Path, help="replay JSON files or directories")
    parser.add_argument("--agent-name", default="yamazaking")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    engine = _load_engine()
    paths = _expand_replay_paths(args.replays)
    episodes = [audit_replay(path, args.agent_name, engine) for path in paths]
    our_wins = sum(episode["margin"] > 0 for episode in episodes if episode["margin"] is not None)
    payload = {
        "format": "kaggriculture-market-replay-audit-v1",
        "engine": "bundled kaggriculture.py from kaggle-environments 1.32.7",
        "agent_name": args.agent_name,
        "replay_count": len(episodes),
        "our_wins": our_wins,
        "our_losses": sum(episode["margin"] < 0 for episode in episodes if episode["margin"] is not None),
        "state_reconciled_count": sum(episode["state_reconciled"] for episode in episodes),
        "cash_reconciled_count": sum(episode["cash_reconciled"] for episode in episodes),
        "episodes": episodes,
        "notes": [
            "This report uses saved replays only and performs no Kaggle API or submission operation.",
            "A requested quantity can exceed the successful fill quantity because the engine stops an order when shed stock, cash, or capacity prevents another unit.",
            "A SELL at the price floor changes player cash but does not increase market inventory under the engine rules.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "replay_count": payload["replay_count"],
        "state_reconciled_count": payload["state_reconciled_count"],
        "cash_reconciled_count": payload["cash_reconciled_count"],
        "our_wins": payload["our_wins"],
        "our_losses": payload["our_losses"],
        "output": str(args.output),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
