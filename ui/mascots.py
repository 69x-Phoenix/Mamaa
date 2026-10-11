"""Original mascot artwork (inline SVG, no external assets).

BSOD         - a tiny blue-screen gremlin (black side)
Null Signal  - a quiet signal from the void (white side)

SVGs are embedded as base64 <img> tags so Streamlit's HTML sanitizer cannot strip them,
and each SVG carries its own <style> for its idle animation.
"""
from __future__ import annotations

import base64

BSOD_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 190">
<defs>
  <linearGradient id="scr" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#2f6bff"/><stop offset="1" stop-color="#1237a8"/></linearGradient>
  <filter id="glow" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
</defs>
<style>
  .float{animation:float 4.5s ease-in-out infinite;transform-origin:80px 100px}
  .blink{animation:blink 5s infinite;transform-origin:center;transform-box:fill-box}
  .glitch{animation:glitch 3.2s steps(1) infinite}
  @keyframes float{0%,100%{transform:translateY(0)}50%{transform:translateY(-5px)}}
  @keyframes blink{0%,92%,100%{transform:scaleY(1)}95%{transform:scaleY(.1)}}
  @keyframes glitch{0%,86%,100%{opacity:0;transform:translateX(0)}88%{opacity:.9;transform:translateX(-5px)}92%{opacity:.9;transform:translateX(4px)}}
</style>
<g class="float">
  <!-- cable tail with plug -->
  <path d="M104 150 C132 150 138 128 126 120 C118 114 112 124 120 128" fill="none" stroke="#3b82f6" stroke-width="3" stroke-linecap="round"/>
  <rect x="116" y="124" width="12" height="8" rx="2" fill="#0b1020" stroke="#60a5fa" stroke-width="1.5" transform="rotate(30 122 128)"/>
  <!-- legs -->
  <rect x="62" y="148" width="14" height="22" rx="6" fill="#0b1020" stroke="#3b82f6" stroke-width="1.6"/>
  <rect x="84" y="148" width="14" height="22" rx="6" fill="#0b1020" stroke="#3b82f6" stroke-width="1.6"/>
  <rect x="58" y="164" width="22" height="9" rx="4.5" fill="#0b1020" stroke="#3b82f6" stroke-width="1.6"/>
  <rect x="80" y="164" width="22" height="9" rx="4.5" fill="#0b1020" stroke="#3b82f6" stroke-width="1.6"/>
  <!-- body + arms -->
  <rect x="56" y="108" width="48" height="46" rx="14" fill="#0b1020" stroke="#3b82f6" stroke-width="1.6"/>
  <path d="M56 122 C42 124 40 138 46 144" fill="none" stroke="#3b82f6" stroke-width="3.5" stroke-linecap="round"/>
  <path d="M104 122 C118 124 120 138 114 144" fill="none" stroke="#3b82f6" stroke-width="3.5" stroke-linecap="round"/>
  <rect x="70" y="122" width="20" height="4" rx="2" fill="#2f6bff" opacity=".8"/>
  <rect x="74" y="131" width="12" height="4" rx="2" fill="#60a5fa" opacity=".5"/>
  <!-- ears -->
  <polygon points="34,36 20,8 58,24" fill="#0b1020" stroke="#3b82f6" stroke-width="1.6" stroke-linejoin="round"/>
  <polygon points="126,36 140,8 102,24" fill="#0b1020" stroke="#3b82f6" stroke-width="1.6" stroke-linejoin="round"/>
  <!-- head (tiny monitor) -->
  <rect x="26" y="24" width="108" height="88" rx="20" fill="#0b1020" stroke="#3b82f6" stroke-width="2" filter="url(#glow)"/>
  <rect x="36" y="34" width="88" height="68" rx="12" fill="url(#scr)"/>
  <!-- face: eyes + smirk -->
  <g class="blink"><rect x="55" y="52" width="11" height="11" rx="2" fill="#fff"/></g>
  <g class="blink"><rect x="94" y="52" width="11" height="11" rx="2" fill="#fff"/></g>
  <path d="M68 78 Q80 86 94 76" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round"/>
  <!-- error text lines -->
  <rect x="46" y="90" width="30" height="3" rx="1.5" fill="#bcd2ff" opacity=".7"/>
  <rect x="80" y="90" width="22" height="3" rx="1.5" fill="#bcd2ff" opacity=".45"/>
  <!-- glitch strip -->
  <rect class="glitch" x="36" y="68" width="88" height="5" fill="#67e8f9" opacity="0"/>
</g>
</svg>"""

NULL_SIGNAL_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 190">
<defs>
  <linearGradient id="body" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#e3e8f1"/></linearGradient>
  <filter id="soft" x="-30%" y="-30%" width="160%" height="170%"><feDropShadow dx="0" dy="6" stdDeviation="6" flood-color="#5b6b8c" flood-opacity=".22"/></filter>
</defs>
<style>
  .float{animation:float 5.5s ease-in-out infinite;transform-origin:80px 120px}
  .arc{animation:pulse 3.6s ease-in-out infinite}
  .a2{animation-delay:.5s}.a3{animation-delay:1s}
  .dot{animation:dot 3.6s ease-in-out infinite;transform-origin:center;transform-box:fill-box}
  @keyframes float{0%,100%{transform:translateY(0)}50%{transform:translateY(-6px)}}
  @keyframes pulse{0%,100%{opacity:.25}50%{opacity:.95}}
  @keyframes dot{0%,100%{transform:scale(1)}50%{transform:scale(1.35)}}
</style>
<g class="float">
  <!-- signal arcs rising from the void -->
  <path class="arc a3" d="M38 52 A42 42 0 0 1 122 52" fill="none" stroke="#9aa8c2" stroke-width="2.5" stroke-linecap="round"/>
  <path class="arc a2" d="M52 52 A28 28 0 0 1 108 52" fill="none" stroke="#9aa8c2" stroke-width="2.5" stroke-linecap="round"/>
  <path class="arc"    d="M66 52 A14 14 0 0 1 94 52" fill="none" stroke="#9aa8c2" stroke-width="2.5" stroke-linecap="round"/>
  <circle class="dot" cx="80" cy="54" r="3.6" fill="#2f6bff"/>
  <!-- soft pebble body with a drifting hem -->
  <path filter="url(#soft)" fill="url(#body)" stroke="#c5cddd" stroke-width="1.8"
        d="M36 160 C36 106 56 74 80 74 C104 74 124 106 124 160 C114 153 106 166 96 160 C88 155 72 155 64 160 C54 166 46 153 36 160 Z"/>
  <!-- face: one calm eye, one null eye, quiet mouth -->
  <circle cx="66" cy="116" r="3.4" fill="#4b5873"/>
  <circle cx="96" cy="116" r="6" fill="none" stroke="#4b5873" stroke-width="2.2"/>
  <line x1="91.5" y1="121" x2="100.5" y2="111" stroke="#4b5873" stroke-width="2.2" stroke-linecap="round"/>
  <line x1="74" y1="134" x2="86" y2="134" stroke="#8a97b0" stroke-width="2.4" stroke-linecap="round"/>
</g>
</svg>"""


def _data_uri(svg: str) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")


BSOD_URI = _data_uri(BSOD_SVG)
NULL_SIGNAL_URI = _data_uri(NULL_SIGNAL_SVG)
