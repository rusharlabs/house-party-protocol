"""Provider-neutral, auditable routing policy for declared work tiers."""
from __future__ import annotations

from typing import Any


TIERS = ("economy", "balanced", "frontier")
RISK = ("low", "medium", "high")
COMPLEXITY = ("low", "medium", "high")


class RoutingError(ValueError):
    """A routing request or provider declaration is incomplete."""


def _requested_tier(request: dict[str, Any], policy: str) -> str:
    if policy not in TIERS:
        raise RoutingError(f"unknown routing policy: {policy}")
    risk = request.get("risk")
    complexity = request.get("complexity")
    context = request.get("context")
    stage = request.get("stage")
    if risk not in RISK or complexity not in COMPLEXITY:
        raise RoutingError("risk and complexity must be low, medium or high")
    if not isinstance(context, int) or context < 0:
        raise RoutingError("context must be a non-negative integer")
    if not isinstance(stage, str) or not stage:
        raise RoutingError("stage must be a non-empty string")
    if risk == "high" or complexity == "high" or context > 16000:
        return "frontier"
    if risk == "medium" or complexity == "medium" or context > 8000:
        return "frontier" if policy == "frontier" else "balanced"
    if policy == "economy":
        return "economy"
    if policy == "frontier":
        return "frontier"
    return "balanced"


def _providers(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not raw:
        raise RoutingError("providers must be a non-empty list")
    providers: list[dict[str, Any]] = []
    seen: set[str] = set()
    for provider in raw:
        if not isinstance(provider, dict) or not isinstance(provider.get("id"), str) or not provider["id"]:
            raise RoutingError("every provider needs an id")
        provider_id = provider["id"]
        if provider_id in seen:
            raise RoutingError(f"duplicate provider: {provider_id}")
        seen.add(provider_id)
        tiers = provider.get("tiers")
        stages = provider.get("stages")
        maximum = provider.get("max_context")
        if not isinstance(tiers, list) or not tiers or any(tier not in TIERS for tier in tiers):
            raise RoutingError(f"provider {provider_id} has invalid tiers")
        if not isinstance(stages, list) or not stages or not all(isinstance(stage, str) and stage for stage in stages):
            raise RoutingError(f"provider {provider_id} has invalid stages")
        if not isinstance(maximum, int) or maximum < 0:
            raise RoutingError(f"provider {provider_id} has invalid max_context")
        providers.append({"id": provider_id, "tiers": sorted(set(tiers), key=TIERS.index),
                          "stages": sorted(set(stages)), "max_context": maximum})
    return sorted(providers, key=lambda provider: provider["id"])


def route(request: dict[str, Any], policy: str, providers: list[dict[str, Any]]) -> dict[str, Any]:
    """Return a deterministic route, never a vendor/model or pricing decision."""
    if not isinstance(request, dict):
        raise RoutingError("routing request must be an object")
    requested_tier = _requested_tier(request, policy)
    eligible = [
        provider for provider in _providers(providers)
        if request["stage"] in provider["stages"] and request["context"] <= provider["max_context"]
    ]
    if not eligible:
        raise RoutingError("no provider supports the requested stage and context")
    rank = {tier: index for index, tier in enumerate(TIERS)}
    exact = [provider for provider in eligible if requested_tier in provider["tiers"]]
    fallback: dict[str, str] | None = None
    candidates = exact
    if not candidates:
        candidates = [
            provider for provider in eligible
            if any(rank[tier] > rank[requested_tier] for tier in provider["tiers"])
        ]
        if not candidates:
            raise RoutingError(f"no provider satisfies the {requested_tier} risk floor")
        fallback = {"reason": "upgraded-above-requested-tier", "requested_tier": requested_tier}
    selected_provider = sorted(
        candidates,
        key=lambda provider: (
            min(rank[tier] for tier in provider["tiers"] if rank[tier] >= rank[requested_tier]),
            provider["id"],
        ),
    )[0]
    selected_tier = requested_tier if requested_tier in selected_provider["tiers"] else min(
        (tier for tier in selected_provider["tiers"] if rank[tier] > rank[requested_tier]),
        key=rank.get,
    )
    return {
        "schema": "hpp.route/v1",
        "policy": policy,
        "requested_tier": requested_tier,
        "selection": {"provider": selected_provider["id"], "tier": selected_tier},
        "fallback": fallback,
        "eligible_providers": [provider["id"] for provider in eligible],
        "rationale": {"risk": request["risk"], "complexity": request["complexity"],
                      "context": request["context"], "stage": request["stage"]},
    }
