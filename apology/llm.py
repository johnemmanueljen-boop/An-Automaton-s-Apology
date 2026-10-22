"""Model calls that return JSON, with a disk cache and a hard spending cap.

- Cache: every answer is stored in `.llm_cache/<sha256 of the full request>.json`, so re-running an
  experiment costs nothing and gives the same answer. The cache ships with the repository: every number
  in the README can be reproduced without an API key.
- Budget: `LLM_BUDGET_USD` (default 6). A call is refused if its worst case could exceed the cap; every
  paid call is logged in `.llm_cache/ledger.jsonl`.
- Models: Opus for the audit (judgment), Sonnet for writing Lean (Lean checks it anyway). Override with
  LLM_MODEL_AUDIT / LLM_MODEL_PROBE.
- Batch: `complete_json_many` sends many prompts through the Message Batches API at half price.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import copy

from .paths import CACHE, ROOT

LEDGER = CACHE / "ledger.jsonl"
PROVIDER = "anthropic"  # part of every cache key
DEFAULT_MODELS = {"audit": "claude-opus-5-5", "probe": "claude-sonnet-5-5"}
PRICES = {  # USD per million tokens (input, output), Oct 2026
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
}
JSON_RETRY = (
    "\n\nIMPORTANT: answer with ONE JSON object only, exactly in the schema requested. "
    "No tool calls, no XML, no prose. [JSON-RETRY]"
)
REQUEST_TRACE: list[dict] = []


class OfflineCacheMiss(RuntimeError):
    pass


def is_offline() -> bool:
    return os.environ.get("APOLOGY_OFFLINE", "1").lower() not in {"0", "false", "no"}


def _trace(key, model, system, user, max_tokens, hit, cost=0.0):
    REQUEST_TRACE.append({"request_id": key, "model": model, "system": system, "user": user,
                          "max_tokens": max_tokens, "cache_hit": hit, "actual_api_usd": cost})


def _load_env() -> None:
    env = ROOT / ".env"  # git-ignored; see .env.example
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())


_load_env()
CACHE.mkdir(exist_ok=True)


# ---------------------------------------------------------------- bookkeeping


def model_name(role: str = "probe") -> str:
    return os.environ.get(f"LLM_MODEL_{role.upper()}") or os.environ.get("LLM_MODEL") or DEFAULT_MODELS[role]


def cache_key(model: str, system: str, user: str, max_tokens: int) -> str:
    request = [PROVIDER, model, system, user, max_tokens, 0.0]
    return hashlib.sha256(json.dumps(request).encode()).hexdigest()


def cached(key: str):
    path = CACHE / f"{key}.json"
    return json.loads(path.read_text(encoding="utf-8"))["parsed"] if path.exists() else None


def _store(key: str, model: str, text: str, parsed) -> None:
    record = {"provider": PROVIDER, "model": model, "raw": text, "parsed": parsed}
    (CACHE / f"{key}.json").write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")


def spent_usd() -> float:
    if not LEDGER.exists():
        return 0.0
    return sum(json.loads(line)["usd"] for line in LEDGER.read_text().splitlines() if line.strip())


def budget_usd() -> float:
    return float(os.environ.get("LLM_BUDGET_USD", "6.0"))


def _cost(usage, model: str, discount: float = 1.0) -> float:
    """Dollar cost of one response; cache writes cost 1.25x input, cache reads 0.05x."""
    price_in, price_out = PRICES.get(model, (4.0, 20.0))
    tokens_in = (
        (usage.input_tokens or 0)
        + (getattr(usage, "cache_creation_input_tokens", 0) or 0) * 1.25
        + (getattr(usage, "cache_read_input_tokens", 0) or 0) * 0.05
    )
    return discount * (tokens_in * price_in + (usage.output_tokens or 0) * price_out) / 1e6


def _worst_case(model: str, system: str, user: str, max_tokens: int) -> float:
    price_in, price_out = PRICES.get(model, (4.0, 20.0))
    return (len(system) + len(user)) / 3.0 * price_in / 1e6 + max_tokens * price_out / 1e6  # ~3 chars per token


def _log(entry: dict) -> None:
    with LEDGER.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def _check_budget(cost: float) -> None:
    if spent_usd() + cost > budget_usd():
        raise RuntimeError(
            f"Budget cap: spent ${spent_usd():.2f}, next call could cost up to ${cost:.2f}, "
            f"cap is ${budget_usd():.2f} (raise LLM_BUDGET_USD to continue)."
        )


def _client():
    if is_offline():
        raise OfflineCacheMiss("offline mode prohibits provider access")
    import anthropic

    # Always the public API with this project's key, whatever ANTHROPIC_BASE_URL the shell has.
    return anthropic.Anthropic(
        api_key=os.environ["ANTHROPIC_API_KEY"], base_url="https://api.anthropic.com", max_retries=3, timeout=600
    )


def _extract_json(text: str):
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1)
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=0)
    return json.loads(text[start:])


def _request(model: str, system: str, user: str, max_tokens: int) -> dict:
    return {
        "model": model,
        "max_tokens": max_tokens,
        "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": user}],
    }


# ---------------------------------------------------------------- one call


def complete_json(system: str, user: str, max_tokens: int = 8000, role: str = "probe"):
    """Answer one prompt as parsed JSON (from the cache when possible)."""
    model = model_name(role)
    key = cache_key(model, system, user, max_tokens)
    if (hit := cached(key)) is not None:
        _trace(key, model, system, user, max_tokens, True)
        return copy.deepcopy(hit)
    if is_offline():
        raise OfflineCacheMiss(f"offline cache miss: {key}; no provider call made")
    _check_budget(_worst_case(model, system, user, max_tokens))

    client, budget = _client(), max_tokens
    for _ in range(2):  # if the answer is cut off, retry once with twice the room
        with client.messages.stream(**_request(model, system, user, budget)) as stream:
            response = stream.get_final_message()
        cost = _cost(response.usage, model)
        _trace(key, model, system, user, budget, False, cost)
        truncated = response.stop_reason == "max_tokens"
        _log(
            {
                "model": model,
                "role": role,
                "in": response.usage.input_tokens,
                "out": response.usage.output_tokens,
                "usd": round(cost, 5),
                "truncated": truncated,
            }
        )
        if not truncated:
            break
        budget = min(2 * budget, 64000)
        print(f"warning: {model} answer truncated; retrying with max_tokens={budget}", file=sys.stderr)
        _check_budget(_worst_case(model, system, user, budget))
    else:
        raise RuntimeError(f"{model} answer still truncated at {budget} tokens")

    text = "".join(b.text for b in response.content if getattr(b, "type", "") == "text")
    try:
        parsed = _extract_json(text)
    except ValueError as e:
        if user.endswith("[JSON-RETRY]"):
            raise RuntimeError(f"{model} did not return JSON: {e}") from e
        print(f"warning: non-JSON answer from {model}; asking again", file=sys.stderr)
        return complete_json(system, user + JSON_RETRY, max_tokens, role)
    _store(key, model, text, parsed)
    return parsed


# ---------------------------------------------------------------- many calls, half price


def complete_json_many(
    items: list[tuple[str, str, int]], role: str = "audit", poll_s: int = 20, timeout_s: int = 7200
) -> list:
    """Answer many (system, user, max_tokens) prompts via the Message Batches API.

    Uses the same cache as `complete_json`. Batches are sized so their worst case fits the remaining
    budget. Failed, truncated or non-JSON answers fall back to `complete_json` with more room."""
    model = model_name(role)
    keys = [cache_key(model, s, u, m) for s, u, m in items]
    out = [cached(k) for k in keys]
    todo = [i for i, x in enumerate(out) if x is None]
    for i, value in enumerate(out):
        if value is not None:
            _trace(keys[i], model, *items[i], True)
    if todo and is_offline():
        raise OfflineCacheMiss(f"offline batch cache misses: {len(todo)}; no batch submitted")

    def worst(i):
        return 0.5 * _worst_case(model, *items[i])

    while todo:
        room = budget_usd() - spent_usd() - 0.25
        chunk, total = [], 0.0
        for i in todo:
            if total + worst(i) > room:
                break
            chunk.append(i)
            total += worst(i)
        if not chunk:
            raise RuntimeError(
                f"Budget cap: next request could cost up to ${worst(todo[0]):.2f}; "
                f"spent ${spent_usd():.2f} of ${budget_usd():.2f}."
            )
        todo = todo[len(chunk) :]
        _run_batch(chunk, items, keys, out, model, role, poll_s, timeout_s)
    return out


def _run_batch(chunk, items, keys, out, model, role, poll_s, timeout_s) -> None:
    if is_offline():
        raise OfflineCacheMiss("offline mode prohibits batch submission")
    client = _client()
    requests = [{"custom_id": f"r{i}", "params": _request(model, *items[i])} for i in chunk]
    batch = client.messages.batches.create(requests=requests)
    print(f"batch {batch.id}: {len(requests)} requests", file=sys.stderr)
    started = time.time()
    while client.messages.batches.retrieve(batch.id).processing_status != "ended":
        if time.time() - started > timeout_s:
            raise RuntimeError(f"batch {batch.id} not finished after {timeout_s}s")
        time.sleep(poll_s)

    retry = []
    for entry in client.messages.batches.results(batch.id):
        i = int(entry.custom_id[1:])
        if entry.result.type != "succeeded":
            retry.append(i)
            continue
        msg = entry.result.message
        _trace(keys[i], model, *items[i], False, _cost(msg.usage, model, discount=0.5))
        truncated = msg.stop_reason == "max_tokens"
        _log(
            {
                "model": model,
                "role": role,
                "in": msg.usage.input_tokens,
                "out": msg.usage.output_tokens,
                "usd": round(_cost(msg.usage, model, discount=0.5), 5),
                "batch": True,
                "truncated": truncated,
            }
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        try:
            parsed = None if truncated else _extract_json(text)
        except ValueError:
            parsed = None
        if parsed is None:
            retry.append(i)
            continue
        _store(keys[i], model, text, parsed)
        out[i] = parsed
    for i in retry:
        system, user, max_tokens = items[i]
        out[i] = complete_json(system, user, max_tokens=min(2 * max_tokens, 64000), role=role)
