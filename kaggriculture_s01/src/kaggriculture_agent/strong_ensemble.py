"""Conservative strong-action ensemble.

The incumbent candidate is always a member and the default. The public-data
policy is the only additional member currently admitted because it returns a
complete, validated action bundle and already contains its own fallback gate.
"""

from __future__ import annotations

from typing import Any

from kaggriculture_agent.public_hybrid import public_hybrid_agent


def _complete_action(action: Any) -> bool:
    if not isinstance(action, dict):
        return False
    farmer = action.get("farmer")
    hands = action.get("hands")
    market = action.get("market")
    return (
        isinstance(farmer, list)
        and len(farmer) >= 1
        and isinstance(hands, list)
        and isinstance(market, list)
    )


def strong_ensemble_agent(obs: dict[str, Any]) -> dict[str, list]:
    """Select between the current candidate and the public proposal policy."""

    from kaggriculture_agent.registry import candidate_agent

    incumbent = candidate_agent(obs)
    proposal = public_hybrid_agent(obs, incumbent=incumbent)
    if not _complete_action(proposal):
        return incumbent
    # public_hybrid_agent returns the incumbent when its proposal is not
    # supported; copy the selected complete bundle so callers cannot mutate it.
    return {
        "farmer": list(proposal["farmer"]),
        "hands": [list(order) for order in proposal["hands"]],
        "market": [list(order) for order in proposal["market"]],
    }


__all__ = ["strong_ensemble_agent"]
