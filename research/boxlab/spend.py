"""OpenRouter spend tracking — the run's budget guard and its cost meter.

Two jobs, both of which the harness log cannot do on its own:

1. **Guard.** Nine agents on a 1M-context reasoning model can burn a budget
   without any single run looking unusual. `SpendGuard.exceeded()` is checked
   before each launch, so the cap is a *launch gate* — running agents finish, and
   the next one does not start. A mid-flight kill would truncate one arm and
   silently bias the comparison, which is worse than overspending slightly.

2. **Meter.** OpenRouter is authoritative about cost in a way a parsed agent log
   is not, and `deepseek-v4-pro` is a reasoning model whose reasoning tokens bill
   as completion tokens. Snapshotting `usage` before and after a run gives the
   exact spend for that run with no parsing at all.

The key-level `limit` is a per-key cap, not the account balance — a key can show
headroom while the account is empty. `probe()` reports both so a run never starts
against a number that means something other than what it looks like.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional

KEY_URL = "https://openrouter.ai/api/v1/auth/key"
CREDITS_URL = "https://openrouter.ai/api/v1/credits"


@dataclass
class KeyStatus:
    """A point-in-time read of the key's spend and cap."""

    usage: float
    limit: Optional[float]
    limit_remaining: Optional[float]

    @property
    def headroom(self) -> Optional[float]:
        return self.limit_remaining


def _get(url: str, api_key: str, timeout: float = 20.0) -> dict:
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {api_key}"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def key_status(api_key: str) -> Optional[KeyStatus]:
    """Read the key's usage and cap, or None if OpenRouter is unreachable.

    A failed read must never be mistaken for zero spend, so it returns None and
    the caller decides — the guard treats None as "do not launch".
    """
    try:
        data = _get(KEY_URL, api_key).get("data") or {}
    except (urllib.error.URLError, OSError, ValueError):
        return None
    return KeyStatus(
        usage=float(data.get("usage") or 0.0),
        limit=(float(data["limit"]) if data.get("limit") is not None else None),
        limit_remaining=(float(data["limit_remaining"])
                         if data.get("limit_remaining") is not None else None),
    )


def account_usage(api_key: str) -> Optional[float]:
    """Total credits consumed on the account — the figure that actually moves.

    Measured on a live 27-minute run: the key's own `usage` field rose by $0.02
    while the account's `total_usage` rose by $0.82. A guard reading the key
    field would have let a run spend forty times its budget and reported 2% used
    the whole way. The account total is therefore the spend signal, and the key
    field is kept only for the per-key cap it reports.
    """
    try:
        data = _get(CREDITS_URL, api_key).get("data") or {}
    except (urllib.error.URLError, OSError, ValueError):
        return None
    value = data.get("total_usage")
    return None if value is None else float(value)


class SpendGuard:
    """A launch gate over an absolute spend budget for this run."""

    def __init__(self, api_key: str, budget_usd: float) -> None:
        self.api_key = api_key
        self.budget_usd = float(budget_usd)
        start = account_usage(api_key)
        if start is None:
            raise RuntimeError(
                "could not read OpenRouter account usage — refusing to start a "
                "run with no budget guard")
        self.start_usage = start
        self.start_status = key_status(api_key)

    def spent(self) -> Optional[float]:
        """Spend since the guard was created, or None if the read failed.

        Measured against the **account** total, not the key's own `usage` — see
        :func:`account_usage` for why the latter cannot be trusted here.
        """
        now = account_usage(self.api_key)
        return None if now is None else max(0.0, now - self.start_usage)

    def exceeded(self) -> bool:
        """True when no further launch should happen.

        An unreadable status counts as exceeded: launching blind is how a budget
        cap becomes decorative.
        """
        spent = self.spent()
        return True if spent is None else spent >= self.budget_usd

    def report(self) -> str:
        spent = self.spent()
        if spent is None:
            return "openrouter: spend unreadable"
        return (f"openrouter: ${spent:.2f} of ${self.budget_usd:.2f} used "
                f"({100 * spent / self.budget_usd:.0f}%)")


def probe(api_key: str) -> str:
    """A human-readable budget check for before a run — key cap and account both."""
    lines = []
    ks = key_status(api_key)
    if ks is None:
        return "openrouter: UNREACHABLE — cannot verify budget"
    lines.append(f"  key usage      ${ks.usage:.2f}")
    if ks.limit is not None:
        lines.append(f"  key cap        ${ks.limit:.2f} "
                     f"(remaining ${ks.limit_remaining:.2f})")
    else:
        lines.append("  key cap        none set")
    try:
        credits = _get(CREDITS_URL, api_key).get("data") or {}
        total = float(credits.get("total_credits") or 0.0)
        used = float(credits.get("total_usage") or 0.0)
        lines.append(f"  account        ${used:.2f} used of ${total:.2f} purchased")
        if used >= total:
            lines.append("  NOTE: account usage meets or exceeds purchased "
                         "credits; the key cap is not the same as funds.")
    except (urllib.error.URLError, OSError, ValueError):
        lines.append("  account        (unreadable)")
    return "openrouter budget:\n" + "\n".join(lines)
