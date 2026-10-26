"""Smart tool routing: send the model only the tool packs a request needs.

Every request carries the descriptions of all tools it may call. With many tools that costs tokens and
makes the model's choice worse, so specialised tools live in packs that switch on when the conversation
needs them (English and Bangla keywords). Tools outside every pack are always available.
Packs stay on for the rest of the conversation; the "All tools" setting turns routing off.
"""
from __future__ import annotations

import re

from tools.registry import ToolRegistry, ToolSpec
from tools.trading import TRADING_TOOL_NAMES

PACKS: dict[str, frozenset[str]] = {"trading": TRADING_TOOL_NAMES}

_TRIGGERS: dict[str, re.Pattern[str]] = {
    "trading": re.compile(
        r"\b(position\s*siz\w*|stop[\s-]?loss|take[\s-]?profit|leverage\w*|liquidat\w*|futures?|perp\w*|pnl|funding|drawdown|"
        r"win[\s-]?rate|expectancy|journal|margin|crypto\w*|bitcoin|btc|eth|usdt|longs?|shorts?|sl|tp|rrr|r:r|risk|"
        r"trad(?:e|es|ed|er|ing)|entry)\b"
        r"|ট্রেড|লিভারেজ|স্টপ|টেক\s?প্রফিট|ঝুঁকি|পজিশন|লং|শর্ট|ক্রিপ্টো|বিটকয়েন|মার্জিন|জার্নাল|লিকুইডেশন|ফান্ডিং|ড্রডাউন|লাভ-?লস",
        re.IGNORECASE),
}


def pack_of(tool_name: str) -> str | None:
    for pack, names in PACKS.items():
        if tool_name in names:
            return pack
    return None


class ToolRouter:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry
        self.mode = "auto"  # "auto" or "all"
        self._active: set[str] = set()

    def reset(self) -> None:
        self._active.clear()

    def select(self, user_text: str) -> list[ToolSpec]:
        specs = self.registry.specs()
        if self.mode == "all":
            return specs
        for pack, trigger in _TRIGGERS.items():
            if trigger.search(user_text or ""):
                self._active.add(pack)
        return [s for s in specs if (pack_of(s.name) is None or pack_of(s.name) in self._active)]
