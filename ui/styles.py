"""All CSS for the MAMA interface (presentation only)."""
from __future__ import annotations

import streamlit as st

CSS = r"""
@import url('https://fonts.googleapis.com/css2?family=Caveat:wght@600;700&display=swap');

:root{
  --mama-blue:#2f6bff; --mama-blue-2:#5b8cff; --mama-ink:#06080c; --mama-paper:#fafbfd;
  --mama-text:#0b1020; --mama-glass:rgba(10,14,26,.84);
  --nav-h:60px;
}

/* ---------- 1. Canvas: permanent 50/50 black | white split ---------- */
html, body, .stApp{ background:var(--mama-ink) !important; }
.stApp{
  background:
    radial-gradient(55% 45% at 25% 38%, rgba(47,107,255,.16), transparent 70%),
    radial-gradient(55% 45% at 75% 38%, rgba(47,107,255,.06), transparent 70%),
    linear-gradient(90deg, #06080c 0%, #06080c 50%, #fafbfd 50%, #fafbfd 100%) !important;
  background-attachment: fixed !important;
}
.stApp::after{               /* hairline glow on the seam */
  content:""; position:fixed; left:50%; top:var(--nav-h); bottom:0; width:1px; z-index:0; pointer-events:none;
  background:linear-gradient(180deg, transparent, rgba(91,140,255,.55), transparent);
}
[data-testid="stAppViewContainer"], [data-testid="stMain"], [data-testid="stMainBlockContainer"],
[data-testid="stBottom"], [data-testid="stBottom"] > div, [data-testid="stBottomBlockContainer"]{ background:transparent !important; }
[data-testid="stAppViewContainer"]{ z-index:0; }   /* stacking context: mascot layer (z -1) stays above the page background */
header[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], footer, #MainMenu{ display:none !important; }

.block-container, [data-testid="stMainBlockContainer"]{
  max-width:860px !important; margin:0 auto;
  padding:calc(var(--nav-h) + 28px) 20px 190px !important;
}
html{ scroll-behavior:smooth; }
* { -webkit-font-smoothing:antialiased; }

/* ---------- 2. Top navigation (fixed, frosted blue) ---------- */
.st-key-topbar{
  position:fixed !important; top:0; left:0; right:0; height:var(--nav-h); z-index:1000;
  display:flex !important; flex-direction:row !important; align-items:center; gap:16px;
  padding:0 20px; margin:0 !important; width:100% !important;
  background:linear-gradient(120deg, rgba(31,84,230,.97), rgba(66,128,255,.95));
  -webkit-backdrop-filter:blur(16px) saturate(150%); backdrop-filter:blur(16px) saturate(150%);
  border-bottom:1px solid rgba(255,255,255,.2);
  box-shadow:0 8px 30px rgba(31,84,230,.28);
}
.st-key-topbar > *{ width:auto !important; flex:0 0 auto; min-width:0; }
.st-key-topbar > *:has(.st-key-nav-search){ flex:1 1 auto !important; max-width:340px; }
.st-key-topbar > *:has(.st-key-nav-icons){ margin-left:auto; }
.mama-logo{ display:flex; flex-direction:column; align-items:flex-start; line-height:1; user-select:none; }
.mama-logo span{
  font-family:'Caveat','Segoe Script','Bradley Hand','Comic Sans MS',cursive; font-weight:700;
  font-size:2.15rem; color:#fff; letter-spacing:.04em; transform:rotate(-3deg); display:inline-block;
  text-shadow:0 2px 12px rgba(255,255,255,.35);
}
.mama-logo svg{ margin-top:-4px; margin-left:2px; }
.st-key-nav-search{ width:100% !important; min-width:110px !important; }
.st-key-nav-search [data-testid="stTextInputRootElement"]{
  background:rgba(255,255,255,.18) !important; border:1px solid rgba(255,255,255,.42) !important;
  border-radius:999px !important; height:38px; min-height:38px; transition:background .2s, box-shadow .2s;
}
.st-key-nav-search [data-testid="stTextInputRootElement"]:focus-within{ background:rgba(255,255,255,.28) !important; box-shadow:0 0 0 3px rgba(255,255,255,.22); }
.st-key-nav-search input{ color:#fff !important; -webkit-text-fill-color:#fff; padding-left:16px !important; font-size:.92rem; background:transparent !important; }
.st-key-nav-search input::placeholder{ color:rgba(255,255,255,.82) !important; -webkit-text-fill-color:rgba(255,255,255,.82); opacity:1; }
.st-key-nav-search label{ display:none; }
.st-key-nav-icons{ display:flex !important; flex-direction:row !important; align-items:center; gap:4px; width:auto !important; }
.st-key-nav-icons > *{ width:auto !important; flex:0 0 auto; }
.st-key-topbar [data-testid="stPopover"] > button,
.st-key-topbar [data-testid="stPopoverButton"]{
  background:transparent !important; border:none !important; color:#fff !important; box-shadow:none !important;
  width:40px; height:40px; min-height:40px; padding:0 !important; border-radius:12px !important; justify-content:center;
  transition:background .2s, transform .15s;
}
.st-key-topbar [data-testid="stPopover"] > button:hover{ background:rgba(255,255,255,.2) !important; transform:translateY(-1px); }
.st-key-topbar [data-testid="stPopoverButton"] [data-testid="stMarkdownContainer"]{ display:none; }          /* label */
.st-key-topbar [data-testid="stPopoverButton"] > div > div[aria-hidden="true"]{ display:none; }                 /* chevron */
.st-key-topbar [data-testid="stPopoverButton"] [data-testid="stIconMaterial"]{ color:#fff !important; font-size:1.45rem; }
.st-key-topbar [data-testid="stPopoverButton"] [data-has-shortcut]{ gap:0; }

/* Popover panels (usage / history / profile / settings) */
[data-testid="stPopoverBody"]{
  border-radius:18px !important; border:1px solid rgba(47,107,255,.18) !important;
  box-shadow:0 24px 60px rgba(6,8,12,.35) !important; min-width:300px; max-width:360px;
  background:rgba(255,255,255,.97) !important; -webkit-backdrop-filter:blur(18px); backdrop-filter:blur(18px);
  animation:mama-pop .18s ease-out;
}
@keyframes mama-pop{ from{opacity:0; transform:translateY(-6px) scale(.98)} to{opacity:1; transform:none} }
.mama-panel-title{ font-size:.72rem; letter-spacing:.14em; text-transform:uppercase; color:#6b7792; margin:2px 0 10px; font-weight:600; }
.mama-usage-row{ display:flex; justify-content:space-between; align-items:baseline; padding:9px 0; border-bottom:1px solid #eef1f7; color:#0b1020; }
.mama-usage-row:last-of-type{ border-bottom:none; }
.mama-usage-row b{ font-variant-numeric:tabular-nums; font-size:1.15rem; color:var(--mama-blue); }
.mama-note{ font-size:.74rem; color:#7a859c; margin-top:8px; line-height:1.4; }
.mama-chip{ display:inline-block; padding:2px 8px; border-radius:999px; background:#eef3ff; color:#2f6bff; font-size:.72rem; font-weight:600; }
[data-testid="stPopoverBody"] .stButton > button{
  border-radius:12px; border:1px solid #e3e8f3; background:#fff; color:#0b1020; text-align:left; justify-content:flex-start;
  transition:background .15s, border-color .15s;
}
[data-testid="stPopoverBody"] .stButton > button:hover{ background:#f3f6ff; border-color:rgba(47,107,255,.45); color:#0b1020; }

/* Search results dropdown */
.st-key-search-results{
  position:fixed !important; top:calc(var(--nav-h) + 8px); left:120px; width:min(380px, calc(100vw - 40px)); z-index:1001;
  background:rgba(255,255,255,.97); border:1px solid rgba(47,107,255,.2); border-radius:16px; padding:10px;
  box-shadow:0 24px 60px rgba(6,8,12,.35); animation:mama-pop .18s ease-out;
}
.st-key-search-results .stButton > button{ border-radius:10px; border:none; background:transparent; justify-content:flex-start; text-align:left; width:100%; }
.st-key-search-results .stButton > button:hover{ background:#f1f5ff; }

/* ---------- 3. Mascots + tip (decorative layer behind the chat) ---------- */
.mama-stage{
  position:fixed; z-index:-1; top:var(--nav-h); left:0; right:0; bottom:130px; pointer-events:none;
  display:flex; flex-direction:column; align-items:center; justify-content:center;
}
.mama-pair{ display:flex; width:100%; }
.mama-half{ flex:1 1 50%; display:flex; flex-direction:column; align-items:center; }
.mama-half img{ width:clamp(150px, 15vw, 210px); height:auto; filter:drop-shadow(0 10px 28px rgba(47,107,255,.35)); transition:width .4s ease; }
.mama-half.left img{ filter:drop-shadow(0 12px 24px rgba(70,88,130,.22)); }
.mama-half.right img{ filter:drop-shadow(0 10px 28px rgba(47,107,255,.35)); }
.mama-half figcaption{ margin-top:6px; text-align:center; font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; }
.mama-half figcaption b{ display:block; font-size:.95rem; letter-spacing:.18em; text-transform:uppercase; }
.mama-half figcaption span{ font-size:.72rem; opacity:1; }
.mama-half.left figcaption{ color:#dbe6ff; }
.mama-half.right figcaption{ color:#27324a; }
.mama-tip{
  margin-top:30px; max-width:min(560px, 86vw); text-align:center; padding:9px 18px; border-radius:999px;
  font-size:.84rem; color:#e9eeff; background:rgba(14,19,34,.78); border:1px solid rgba(91,140,255,.4);
  -webkit-backdrop-filter:blur(10px); backdrop-filter:blur(10px); box-shadow:0 8px 28px rgba(6,8,12,.28);
  animation:mama-fade .6s ease;
}
@keyframes mama-fade{ from{opacity:0; transform:translateY(4px)} to{opacity:1; transform:none} }

/* compact mode: after the first message the mascots shrink into the corners */
.mama-stage.compact{ display:block; }
.mama-stage.compact .mama-pair{ position:absolute; top:14px; left:0; right:0; }
.mama-stage.compact .mama-half.left{ align-items:flex-start; padding-left:26px; }
.mama-stage.compact .mama-half.right{ align-items:flex-end; padding-right:26px; }
.mama-stage.compact .mama-half img{ width:64px; }
.mama-stage.compact .mama-half figcaption span{ display:none; }
.mama-stage.compact .mama-half figcaption b{ font-size:.62rem; }
.mama-stage.compact .mama-tip{ position:fixed; left:50%; bottom:34px; transform:translateX(-50%); margin:0; font-size:.76rem; padding:6px 14px; width:max-content; }

/* ---------- 4. Chat messages ---------- */
[class*="st-key-msg-"]{ display:flex; flex-direction:column; gap:.15rem; padding:14px 18px 14px; border-radius:20px; width:fit-content !important; animation:mama-fade .35s ease; }
.mama-who{ font-size:.66rem; letter-spacing:.16em; text-transform:uppercase; font-weight:700; opacity:.7; }
[class*="st-key-msg-user"]{
  align-self:flex-end; max-width:72%; color:#fff;
  background:linear-gradient(135deg,#2f6bff,#5b8cff); border-bottom-right-radius:6px;
  box-shadow:0 10px 28px rgba(47,107,255,.35);
}
[class*="st-key-msg-user"] p, [class*="st-key-msg-user"] li{ color:#fff; }
[class*="st-key-msg-bot"]{
  align-self:flex-start; max-width:92%; color:var(--mama-text);
  background:rgba(255,255,255,.97); border:1px solid rgba(47,107,255,.16); border-bottom-left-radius:6px;
  box-shadow:0 12px 34px rgba(6,8,12,.28);
}
[class*="st-key-msg-bot"] .mama-who{ color:var(--mama-blue); opacity:1; }
[class*="st-key-msg-bot"] [data-testid="stMarkdownContainer"] p:last-child{ margin-bottom:.2rem; }
[class*="st-key-msg-bot"] .stDownloadButton > button{ border-radius:12px; }

/* tool activity */
.st-key-activity [data-testid="stExpander"], .st-key-activity details{
  border:1px solid rgba(91,140,255,.35) !important; border-radius:16px !important;
  background:rgba(14,19,34,.82) !important; color:#e9eeff; backdrop-filter:blur(10px);
}
.st-key-activity summary, .st-key-activity summary *, .st-key-activity p{ color:#e9eeff !important; }

/* ---------- 5. Command box (chat input) ---------- */
[data-testid="stBottom"]{ padding-bottom:26px; }
[data-testid="stChatInput"]{
  max-width:780px; margin:0 auto; border-radius:26px !important; min-height:58px;
  background:var(--mama-glass) !important; border:1px solid rgba(120,160,255,.45) !important;
  -webkit-backdrop-filter:blur(18px) saturate(140%); backdrop-filter:blur(18px) saturate(140%);
  box-shadow:0 18px 50px rgba(6,8,12,.38), 0 0 0 1px rgba(255,255,255,.04) inset, 0 0 32px rgba(47,107,255,.18);
  transition:box-shadow .25s, border-color .25s;
}
[data-testid="stChatInput"]:focus-within{ border-color:rgba(130,170,255,.9) !important; box-shadow:0 18px 50px rgba(6,8,12,.4), 0 0 0 3px rgba(47,107,255,.28), 0 0 36px rgba(47,107,255,.3); }
[data-testid="stChatInput"] > div, [data-testid="stChatInput"] [data-baseweb="textarea"], [data-testid="stChatInput"] [data-baseweb="base-input"]{ background:transparent !important; border:none !important; }
[data-testid="stChatInput"] textarea{ color:#f1f5ff !important; -webkit-text-fill-color:#f1f5ff; font-size:1rem; padding:16px 8px 16px 18px; caret-color:#8fb0ff; }
[data-testid="stChatInput"] textarea::placeholder{ color:rgba(220,230,255,.6) !important; -webkit-text-fill-color:rgba(220,230,255,.6); opacity:1; }
[data-testid="stChatInput"] button{ background:linear-gradient(135deg,#2f6bff,#5b8cff) !important; color:#fff !important; border-radius:50% !important; margin:8px 10px 8px 0; }
[data-testid="stChatInput"] button:disabled{ opacity:.35; }

/* ---------- 6. Login card ---------- */
.st-key-login{ max-width:380px; margin:14vh auto 0; padding:28px; border-radius:24px; background:rgba(14,19,34,.82);
  border:1px solid rgba(91,140,255,.4); backdrop-filter:blur(16px); box-shadow:0 24px 60px rgba(6,8,12,.45); }
.st-key-login label, .st-key-login p{ color:#dbe6ff !important; }

/* ---------- 7. Responsive ---------- */
@media (max-width:1100px){
  .mama-stage.compact .mama-pair{ display:none; }
}
@media (max-width:900px){
  .block-container, [data-testid="stMainBlockContainer"]{ padding-left:12px !important; padding-right:12px !important; }
  [class*="st-key-msg-user"]{ max-width:88%; } [class*="st-key-msg-bot"]{ max-width:98%; }
  .mama-half img{ width:clamp(110px, 20vw, 160px); }
  .st-key-topbar{ gap:10px; padding:0 12px; }
  .mama-logo span{ font-size:1.8rem; }
  .st-key-search-results{ left:12px; }
}
@media (max-width:640px){
  .st-key-nav-search{ max-width:none; }
  .mama-half figcaption span{ display:none; }
  [data-testid="stPopoverBody"]{ min-width:260px; }
}
@media (prefers-reduced-motion:reduce){ *{ animation:none !important; transition:none !important; } }
"""


def inject_styles() -> None:
    """Inject the global stylesheet (call once per script run, before any content)."""
    st.html(f"<style>{CSS}</style>")
