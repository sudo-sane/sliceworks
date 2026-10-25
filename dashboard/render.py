# sliceworks 0.7.0. Dashboard, render stage: one self-contained HTML page from a snapshot and its computed numbers.
# The look is the first run's page (method chapter 9): design tokens with a dark mode, system fonts, tiles, chips,
# slice steppers, segmented bars, per-increment timelines, folds whose open state survives the 30-second refresh.
# No network, no fonts, no external scripts. Writes nothing; the command line writes the file.
from __future__ import annotations

import datetime as dt
import html
import posixpath
import re

from . import compute as C
from .collect import inc_set, parse_iso


def esc(v) -> str:
    return html.escape("" if v is None else str(v))


def short(s, n: int = 150) -> str:
    s = re.sub(r"`", "", str(s or ""))
    return s if len(s) <= n else s[: n - 1].rsplit(" ", 1)[0] + "…"


_SLICE_REF = re.compile(r"\bslice-?\d+[a-z0-9-]*\b")
_MD_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")


def _slice_links(text: str) -> str:
    out, pos = [], 0
    for m in _SLICE_REF.finditer(text):
        out.append(esc(text[pos:m.start()]))
        sid = m.group(0) if m.group(0).startswith("slice-") else "slice-" + m.group(0)[5:]
        out.append(f'<a class="sref" href="#s-{esc(sid)}">{esc(m.group(0))}</a>')
        pos = m.end()
    out.append(esc(text[pos:]))
    return "".join(out)


def linkify(text, links: dict | None = None) -> str:
    """Escape text; markdown links become links to the repository file (relative to the state directory), slice
    ids become in-page links to their cards. links: {"base": URL prefix of the repository root, or "" for a
    page-relative path; "page_to_root": path from the page's directory to the root; "state_rel": state dir}."""
    links = links or {}
    text = re.sub(r"`", "", str(text or ""))
    out, pos = [], 0
    for m in _MD_LINK.finditer(text):
        out.append(_slice_links(text[pos:m.start()]))
        label, target = m.group(1), m.group(2)
        if not re.match(r"^[a-z][a-z0-9+.-]*:|^#|^/", target):
            rel = posixpath.normpath(posixpath.join(links.get("state_rel", "."), target))
            base = links.get("base") or (links.get("page_to_root", ".").rstrip("/") + "/")
            target = base + rel
        out.append(f'<a href="{esc(target)}">{esc(label)}</a>')
        pos = m.end()
    out.append(_slice_links(text[pos:]))
    return "".join(out)


def unlink_missing(page_html: str) -> str:
    """Drop in-page slice links whose card is not on the page (no dead anchors)."""
    present = set(re.findall(r'id="(s-[^"]+)"', page_html))
    return re.sub(r'<a class="sref" href="#(s-[^"]+)">([^<]*)</a>',
                  lambda m: m.group(0) if m.group(1) in present else m.group(2), page_html)


def nh_item(r: dict, links: dict | None, words: int, show_inc: bool) -> str:
    """One NEEDS-HUMAN row: the summary is the short act; expanding shows the full act and its fields."""
    urg = r.get("urgency", "")
    cls = "urgent" if "urgent" in urg or urg.startswith("now") else ""
    inc = f'<span class="muted">inc {esc(r.get("increment"))}</span> ' if show_inc else ""
    fields = "".join(f'<div><span class="muted">{esc(k)}:</span> {linkify(r.get(k, ""), links)}</div>'
                     for k in ("unblocks", "urgency", "added") if r.get(k))
    return (f'<li class="{cls}" id="nh-{esc(r["id"])}"><details class="nh"><summary><code>{esc(r["id"])}</code> {inc}'
            f'{esc(short(r.get("act", ""), words))}<span class="muted"> · {esc(short(urg, 40))}</span></summary>'
            f'<div class="nhbody"><p>{linkify(r.get("act", ""), links)}</p>{fields}</div></details></li>')


# A slice whose agents may be mid-run: its counters arrive when the run ends.
AGENT_RUNNING = ("active", "repair", "testing", "candidate", "review", "in_review")
AGENTS_TIP = ("Agent time and fresh tokens of the slices' recorded runs. \"so far\" or \"in progress\": a slice is running and its "
              "counters arrive when the run ends. UNKNOWN: a run ended without usage counters. Partial: the coordinator's own "
              "session is not counted.")


def fmt_dur(sec) -> str:
    sec = int(sec or 0)
    h, m = divmod(sec // 60, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


def fmt_tok(n) -> str:
    n = int(n or 0)
    return f"{n / 1e6:.1f}M" if n >= 1e6 else f"{round(n / 1e3)}k" if n >= 1e3 else str(n)


def time_axis(t0: dt.datetime, t1: dt.datetime, tz: dt.tzinfo, max_ticks: int = 7):
    """One timeline's own scale: t0..t1 plus a small margin. Returns (pos, ticks_html), pos(t) in percent.
    Ticks are hours under 2 days, days up to 3 weeks, weeks beyond, aligned in tz; every other tick carries
    class n2 so a narrow screen can drop it and labels never collide."""
    span = max((t1 - t0).total_seconds(), 60.0)
    pad = max(span * 0.02, 120.0)
    lo, hi = t0 - dt.timedelta(seconds=pad), t1 + dt.timedelta(seconds=pad)
    full = (hi - lo).total_seconds()
    pos = lambda t: max(0.0, min(100.0, 100 * (t - lo).total_seconds() / full))
    loc = lo.astimezone(tz)
    if span < 2 * 86400:
        unit, steps, fmt = dt.timedelta(hours=1), (1, 2, 3, 4, 6, 12, 24), "%H:%M"
        x = loc.replace(minute=0, second=0, microsecond=0)
    elif span <= 21 * 86400:
        unit, steps, fmt = dt.timedelta(days=1), (1, 2, 3, 4, 7), "%d.%m"
        x = loc.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        unit, steps, fmt = dt.timedelta(weeks=1), (1, 2, 4, 8, 13, 26, 52), "%d.%m"
        x = loc.replace(hour=0, minute=0, second=0, microsecond=0) - dt.timedelta(days=loc.weekday())
    step = next((s for s in steps if full / (s * unit.total_seconds()) <= max_ticks), steps[-1])
    if unit == dt.timedelta(hours=1):
        while x < loc or x.hour % step:
            x += unit
    else:
        while x < loc:
            x += unit
    ticks = []
    while x <= hi:
        p = pos(x)
        if 3.0 <= p <= 97.0:
            lbl = x.strftime("%d.%m" if fmt == "%H:%M" and x.hour == 0 else fmt)
            ticks.append(f'<span class="tick{" n2" if len(ticks) % 2 else ""}" style="left:{p:.2f}%">{lbl}</span>')
        x += unit * step
    return pos, "".join(ticks)


CSS = """
details.nh>summary{cursor:pointer;list-style:none}details.nh>summary::-webkit-details-marker{display:none}
details.nh>summary::before{content:"▸ ";color:var(--muted,#888)}details.nh[open]>summary::before{content:"▾ "}
.nhbody{margin:4px 0 8px 14px;font-size:.92em;overflow-wrap:anywhere}.nhbody p{margin:2px 0 4px}a.sref{text-decoration:none;border-bottom:1px dotted}
:root{--bg:#f7f7f5;--card:#fff;--ink:#1d1d1b;--muted:#6b6b66;--line:#e4e3de;--accent:#2f6fde;
--ok:#1f8a4c;--okbg:#e3f3e9;--work:#2f6fde;--workbg:#e5eefc;--warn:#b26a00;--warnbg:#fbefd9;
--bad:#c0392b;--badbg:#fbe4e1;--idle:#7a7a74;--idlebg:#efefec;--readybg:#f1e9fb;--ready:#7a3fc2;--fill:#8a8a84}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#151514;--card:#1f1f1d;--ink:#ecebe6;
--muted:#9c9b94;--line:#33322f;--accent:#7aa7ff;--ok:#5cc98a;--okbg:#1c3326;--work:#7aa7ff;--workbg:#1d2a44;
--warn:#f0b35a;--warnbg:#3a2d17;--bad:#ff8a7d;--badbg:#3d1f1c;--idle:#a3a29b;--idlebg:#2a2a27;
--readybg:#2e2340;--ready:#c39cf5;--fill:#8d8c86}}
:root[data-theme="dark"]{--bg:#151514;--card:#1f1f1d;--ink:#ecebe6;
--muted:#9c9b94;--line:#33322f;--accent:#7aa7ff;--ok:#5cc98a;--okbg:#1c3326;--work:#7aa7ff;--workbg:#1d2a44;
--warn:#f0b35a;--warnbg:#3a2d17;--bad:#ff8a7d;--badbg:#3d1f1c;--idle:#a3a29b;--idlebg:#2a2a27;
--readybg:#2e2340;--ready:#c39cf5;--fill:#8d8c86}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 -apple-system,
BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}main{max-width:1180px;margin:0 auto;padding:20px 16px 48px}
h1{font-size:22px;margin:0}h3{margin:0;font-size:16px}h4{margin:14px 0 6px;font-size:13px;color:var(--muted);
text-transform:uppercase;letter-spacing:.04em}code{font:12px ui-monospace,SFMono-Regular,Menlo,monospace}
.muted{color:var(--muted)}.hd{padding:12px 0 10px;margin-bottom:6px}.hrow{display:flex;justify-content:space-between;align-items:baseline;gap:10px;flex-wrap:wrap}
.hd h1{font-size:18px;margin:0}
.tiles{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr) minmax(0,1fr);gap:8px;margin:10px 0 8px}
.tiles.four{grid-template-columns:minmax(0,1.3fr) minmax(0,1.2fr) minmax(0,1.2fr) minmax(0,.8fr)}
.tile{background:var(--card);border:1px solid var(--line);border-radius:9px;padding:8px 11px;display:flex;flex-direction:column;gap:2px;justify-content:space-between;min-width:0}
.tile em{font-style:normal;font-size:11.5px;color:var(--muted)}.tile b{font-size:20px;font-weight:650;line-height:1.15}
.tile b span{font-size:13px;color:var(--muted);font-weight:500}.tile small{font-size:11px;color:var(--muted)}
.tile.warn b{color:var(--warn)}.readyn{cursor:help;border-bottom:1px dotted var(--muted)}
a.tile.scov{color:inherit;text-decoration:none;cursor:pointer}a.tile.scov:hover{border-color:var(--accent)}
.scov .sl{font-size:13px;line-height:1.4}.scov .sl b{font-size:inherit;font-weight:650}
.ssegs{display:flex;gap:2px;height:6px;margin-top:4px}.ssegs i{border-radius:2px;background:var(--idlebg)}
.ssegs i.proven{background:var(--ok)}.ssegs i.progress{background:var(--ready)}
.bbar{position:relative;height:8px;background:var(--idlebg);border-radius:4px;margin-top:5px}
.bbar i{position:absolute;top:0;bottom:0;display:block;border-radius:3px}.bbar .bu{left:0;background:var(--fill)}
.bbar .bp{background:repeating-linear-gradient(135deg,var(--workbg) 0 4px,var(--work) 4px 6px)}
.bbar .bmark{width:2px;top:-3px;bottom:-3px;background:var(--bad);border-radius:0}
.blegend{display:flex;justify-content:space-between;font-size:11px;color:var(--muted);margin-top:3px}
.vchip{font-size:12px;padding:2px 8px;border-radius:999px;white-space:nowrap}.vchip.ok{background:var(--okbg);color:var(--ok)}
.vchip.warn{background:var(--warnbg);color:var(--warn)}.okt{color:var(--ok)}.warnt{color:var(--warn)}
.wb{position:relative;overflow:visible}.wb .mark{position:absolute;top:-2px;bottom:-2px;width:2px;background:var(--warn);display:block}
.wb .mark.stop{background:var(--bad)}.tile.budget .fc{color:var(--ink);font-size:12px}.tile.budget .h5{margin-top:2px}.tile.prog{position:relative;container-type:inline-size}
.prow{display:flex;align-items:baseline;justify-content:space-between;gap:8px}.prow .eta{white-space:nowrap}
@container (max-width: 360px){.pace{display:none}}
.psegs{display:flex;gap:2px;height:6px;margin-top:4px}.pseg{position:relative;background:var(--idlebg);border-radius:2px;overflow:hidden}
.pseg i{position:absolute;inset:0 auto 0 0;background:var(--ok)}.pseg.pv1{background:var(--workbg)}.pseg.pv1 i{background:var(--work)}
.psep{width:3px}.pseg.pun{background:repeating-linear-gradient(135deg,var(--idlebg) 0 3px,var(--line) 3px 5px)}
.unn{font-style:normal;color:var(--muted)}
.v1n{font-style:normal;color:var(--work)}.pright{display:flex;align-items:baseline;gap:10px}.delta{color:var(--ok);white-space:nowrap}.tile.bad b{color:var(--bad)}
.mini{display:block;height:5px;border-radius:3px;background:var(--idlebg);overflow:hidden;margin-top:3px}
.mini span{display:block;height:100%;background:var(--fill)}.mini.full span{background:var(--ok)}
.tile.warn .mini span{background:var(--warn)}.tile.bad .mini span{background:var(--bad)}.rtb{display:grid;grid-template-columns:46px minmax(30px,max-content) minmax(0,1fr) auto auto;align-items:center;gap:6px;margin-top:4px;cursor:help}.rtb b{font-size:16px}.rtb b span{font-size:11px}.rtb .bbar{margin:0;height:8px}.rtb .bbar .mark{z-index:1}.rtb .vchip{font-size:10.5px;padding:1px 6px}.rtb.warn b{color:var(--warn)}.rtb.bad b{color:var(--bad)}.rth{font-size:11px;color:var(--muted);white-space:nowrap}
.hold{margin-top:8px;font-size:12px;color:var(--warn);background:var(--warnbg);padding:5px 9px;border-radius:6px}
@media (max-width:760px){.tiles,.tiles.four{grid-template-columns:repeat(2,minmax(0,1fr))}.tile.prog,.tile.budget,.tile.scov{grid-column:1/-1}}
h2{font-size:15px;margin:14px 0 4px}
.card,.inc,.slice{background:var(--card);border:1px solid var(--line);border-radius:10px}
.card{padding:14px;min-width:0}
.bar{height:8px;background:var(--idlebg);border-radius:6px;overflow:hidden;margin-top:6px}
.bar span{display:block;height:100%;background:var(--fill)}.bar.full span{background:var(--ok)}.barlbl{font-size:12px;color:var(--muted);margin-top:3px}
.chip{font-size:12px;padding:2px 9px;border-radius:999px;white-space:nowrap;background:var(--idlebg);color:var(--idle)}
.chip.done{background:var(--okbg);color:var(--ok)}.chip.work{background:var(--workbg);color:var(--work)}
.chip.warn{background:var(--warnbg);color:var(--warn)}.chip.bad,.chip.unknown{background:var(--badbg);color:var(--bad)}
.chip.ready{background:var(--readybg);color:var(--ready)}
.inc{margin:12px 0}.inc>details>summary{list-style:none;cursor:pointer;padding:14px}
.inc>details>summary::-webkit-details-marker{display:none}.inc>details>*:not(summary){margin:0 14px}
.inc>details[open]{padding-bottom:14px}.ihead{display:flex;gap:12px;align-items:flex-start}
.ihead>div{flex:1;min-width:0}.ihead p{margin:2px 0 0}.iprog{margin-top:8px}
.idesc{color:var(--muted);font-size:13px;margin:2px 14px 10px;line-height:1.45}.idesc b{color:var(--ink);font-weight:600}
.ihead{align-items:center}.ihead h3{margin:0}
.uchip{font-size:11px;padding:1px 7px;border-radius:999px;background:var(--idlebg);color:var(--muted);margin-left:4px;white-space:nowrap}
.uchip.inc{background:var(--workbg);color:var(--work)}
.timeline{margin:12px 0;font-size:12px}.tlrow{display:grid;grid-template-columns:210px 1fr 64px;gap:10px;align-items:center;padding:3px 0}
.tll{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.tlr{text-align:right;color:var(--muted)}
.tlt{position:relative;height:12px;background:repeating-linear-gradient(90deg,transparent 0 calc(100% - 1px),var(--line) 0 100%);border-radius:3px}
.tlrow:not(.axis) .tlt{background:var(--idlebg)}.axis .tlt{background:none;height:14px}
.tick{position:absolute;top:0;transform:translateX(-50%);color:var(--muted);font-size:10.5px}
i.tl{position:absolute;top:0;bottom:0;border-radius:3px;display:block}.lg{margin-right:12px;color:var(--muted)}.tllegend{margin:4px 0 0 220px;font-size:11.5px}
.lg i.tl{position:relative;display:inline-block;width:10px;height:8px;margin-right:4px;vertical-align:middle}
.tl.impl{background:var(--work)}.tl.rev{background:var(--ready)}.tl.mrg{background:var(--fill)}.tl.t2{background:var(--ok)}
.tl.live{animation:pulse 2.4s ease-in-out infinite}
@media (max-width:760px){.tlrow{grid-template-columns:90px 1fr 48px}.tick.n2{display:none}.tllegend{margin-left:0}}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.55}}
@keyframes ring{0%,100%{box-shadow:0 0 0 2px var(--workbg)}50%{box-shadow:0 0 0 5px var(--workbg)}}
.seg.work,.chip.work,.stepper li.cur span{animation:pulse 2.4s ease-in-out infinite}
.stepper li.cur i{animation:ring 2.4s ease-in-out infinite}
@media (prefers-reduced-motion:reduce){.seg.work,.chip.work,.stepper li.cur span,.stepper li.cur i,.tl.live{animation:none}}
.acts{margin-top:8px;font-size:12.5px}.acts em{font-style:normal;color:var(--warn);font-weight:600}
.acts ul{list-style:none;margin:3px 0 0;padding:0}.acts li{padding:2px 0 2px 10px;border-left:2px solid var(--warn);margin:3px 0}
.acts li.urgent{border-color:var(--bad)}.acts li.urgent code{color:var(--bad)}
.segs{display:flex;gap:3px;height:8px;margin-top:4px}.seg{position:relative;border-radius:3px;overflow:hidden;
background:var(--idlebg);min-width:6px}.seg i{position:absolute;inset:0 auto 0 0;display:block}
.seg.done{background:var(--ok)}.seg.work{background:var(--workbg);box-shadow:inset 0 0 0 1px var(--work)}.seg.work i{background:var(--work)}
.seg.warn{background:var(--warnbg);box-shadow:inset 0 0 0 1px var(--warn)}.seg.warn i{background:var(--warn)}
.seg.bad,.seg.unknown{background:var(--badbg);box-shadow:inset 0 0 0 1px var(--bad)}.seg.ready{background:var(--readybg);
box-shadow:inset 0 0 0 1px var(--ready)}.seg.idle{background:var(--idlebg)}
.ino{flex:none;width:30px;height:30px;border-radius:8px;background:var(--workbg);color:var(--work);
display:grid;place-items:center;font-weight:700}
.slices{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:10px}
.slice{padding:12px;min-width:0}.slice header{display:flex;justify-content:space-between;gap:8px;align-items:flex-start}
.stepper{list-style:none;padding:0;margin:12px 0 8px;display:flex}
.stepper li{flex:1;position:relative;text-align:center;font-size:10.5px;color:var(--muted);line-height:1.2}
.stepper li i{display:block;width:9px;height:9px;border-radius:50%;margin:0 auto 5px;background:var(--card);
border:1.5px solid var(--line);position:relative;z-index:1}
.stepper li::before{content:"";position:absolute;top:4px;left:-50%;width:100%;height:1.5px;background:var(--line)}
.stepper li:first-child::before{display:none}.stepper li.done i{background:var(--fill);border-color:var(--fill)}
.stepper li.done::before,.stepper li.cur::before{background:var(--fill)}.stepper li.done{color:var(--ink)}
.stepper li.cur i{background:var(--work);border-color:var(--work);box-shadow:0 0 0 3px var(--workbg)}
.stepper li.cur{color:var(--work);font-weight:600}
.slice.compact{padding:10px 12px}.slice.compact .meta{margin-top:4px}
.meta{font-size:12px;color:var(--muted)}details details summary{cursor:pointer;font-size:12px;color:var(--accent);margin-top:6px}
ul.rows,ul.plan,ul.plain{list-style:none;padding:0;margin:6px 0}ul.rows li{padding:3px 0;font-size:13px;display:flex;gap:6px}
ul.rows li .mk{width:14px;flex:none}ul.rows li.done .mk{color:var(--ok)}ul.rows li.hum .mk{color:var(--warn)}
ul.rows li.todo .mk{color:var(--muted)}ul.plan li{padding:4px 0 4px 12px;border-left:3px solid var(--line);margin:4px 0}
ul.plain li{padding:5px 0;border-bottom:1px solid var(--line);font-size:13px}ul.plain li.urgent code{color:var(--bad)}
.scen{margin:10px 0}.scen summary{cursor:pointer;list-style:none}.scen summary::-webkit-details-marker{display:none}
.v1{display:flex;flex-wrap:wrap;gap:4px 18px;margin:8px 0;font-size:13px}.kv b{font-weight:650}
.scen .v1{margin:10px 0 4px}.stbl{overflow-x:auto;margin-top:10px}.stbl table{width:100%;border-collapse:collapse;font-size:12.5px}
.stbl th,.stbl td{text-align:left;padding:4px 8px 4px 0;border-bottom:1px solid var(--line);vertical-align:top}
.stbl thead th{font-size:11.5px;color:var(--muted);font-weight:500}.stbl tr.sgh th{padding-top:10px;font-size:12px;
color:var(--muted);text-transform:uppercase;letter-spacing:.04em}.stbl tr.later td{color:var(--muted)}
.stbl td:nth-child(3),.stbl td:nth-child(4),.stbl td:nth-child(5){white-space:nowrap}
code.sr{font-size:11px;padding:0 5px;border-radius:4px;background:var(--idlebg);color:var(--muted);white-space:nowrap;cursor:help}
code.sr.on{background:var(--okbg);color:var(--ok)}
summary.fold{display:flex;flex-wrap:wrap;align-items:center;gap:4px 8px;cursor:pointer;list-style:none;min-width:0}
summary.fold::-webkit-details-marker{display:none}summary.fold::before{content:"▸";color:var(--muted);flex:none;width:10px}
details[open]>summary.fold::before{content:"▾"}.scen>details>summary.fold{display:block}.scen>details>summary.fold::before{display:inline-block;margin-right:4px}
.inc.closed{margin:6px 0}.inc.closed>details>summary{padding:8px 14px}.inc.closed .ino{width:22px;height:22px;border-radius:6px;font-size:12px}
.inc.closed .ct{font-weight:600;min-width:0;overflow-wrap:anywhere}.inc.closed summary .muted{font-size:12.5px}
.inc.closed summary a{color:var(--accent)}.inc.closed>details>.iprog{margin:0 14px 8px}
@media (max-width:760px){.stbl th:nth-child(3),.stbl td:nth-child(3),.stbl th:nth-child(6),.stbl td:nth-child(6){display:none}}
.two{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:12px;margin-top:12px}@media (max-width:760px){.two{grid-template-columns:1fr}
.stepper li span{font-size:9px}}
"""

SCEN_ST = {"proven": ("done", "proven", "✓"), "progress": ("ready", "in progress", "◐"),
           "todo": ("idle", "not started", "○"), "thinned": ("idle", "thinned", "–")}


def page(snap: dict, now: dt.datetime, history: list[dict] | None = None) -> str:
    cfg = snap["config"]
    tz = C.zone(cfg.get("SW_TIMEZONE", "UTC"))
    loc = lambda t: t.astimezone(tz)
    hm = lambda t: loc(t).strftime("%H:%M")

    def ts_short(v) -> str:
        t = parse_iso(v)
        return hm(t) if t else ""

    name = snap["name"]
    features, slices = snap["features"], C.slices_of(snap)
    links = snap.get("links") or {}
    frow = {f.get("id"): f for f in features}
    incr, ms = snap["increment"], snap["milestone"]
    try:
        cur_n = int(incr.get("current", "0") or 0)
    except ValueError:
        cur_n = 0
    incs = C.increments(snap)
    titles = {k: v for i in incs for k, v in i["titles"].items()}
    for x in slices:
        titles.setdefault(x["id"], x.get("name") or "")
    open_needs = [r for r in snap["needs"] if r.get("open")]
    head = snap["head"]
    per = C.progress(snap, incs, cur_n)
    total_steps = sum(t for _, _, t, _ in per) or 1.0
    done_steps = sum(d for _, _, _, d in per)
    prog = 100 * done_steps / total_steps
    pc = C.pace(snap, per, now)

    # ---- agent counters per slice (partial by construction) ----
    events, coverage = snap["agent_events"], snap["agent_coverage"]
    eff: dict[str, dict] = {}
    for a in events:
        e = eff.setdefault(a.get("slice") or "other", {"tokens": 0, "tokens_unknown": False, "active_s": 0, "active_unknown": False, "roles": {}})
        for field, value, unknown in (("tokens", a["tokens"], "tokens_unknown"), ("active_s", a["active_s"], "active_unknown")):
            if isinstance(value, int):
                e[field] += value
            else:
                e[unknown] = True
        r = e["roles"].setdefault(a["role"], {"tokens": 0, "tokens_unknown": False})
        if isinstance(a["tokens"], int):
            r["tokens"] += a["tokens"]
        else:
            r["tokens_unknown"] = True

    def agents_txt(sl: list[dict], unit: str) -> str:
        """Agent time and tokens over slices, in words a reader can act on: "no agent runs yet" before any slice
        started, "so far" or "in progress" while one runs, UNKNOWN only where a run ended without counters."""
        run = {x["id"] for x in sl if C.norm_state(x.get("state")) in AGENT_RUNNING}
        ended = {x["id"] for x in sl if x["id"] not in run
                 and (C.STATES.get(C.norm_state(x.get("state")), (-1,))[0] >= 1 or C.stamped(x.get("active")))}
        es = {sid: eff[sid] for sid in run | ended if sid in eff}
        if not run and not ended:
            return "no agent runs yet"

        def part(field, flag, fmt):
            total = sum(e[field] for e in es.values())
            if any(sid not in es or es[sid][flag] for sid in ended):
                return "UNKNOWN"
            if run:
                return f"{fmt(total)} so far" if total else "in progress"
            return fmt(total)
        t_txt, k_txt = part("active_s", "active_unknown", fmt_dur), part("tokens", "tokens_unknown", fmt_tok)
        return "agents in progress" if t_txt == k_txt == "in progress" else f"agents {t_txt} · {k_txt} {unit}"

    def eff_txt(s: dict) -> str:
        sid = s.get("id", "")
        e = eff.get(sid)
        if not e and C.norm_state(s.get("state")) not in AGENT_RUNNING:
            return ""
        roles = "; ".join(f"{k}: {'UNKNOWN' if v['tokens_unknown'] else fmt_tok(v['tokens'])} tok" for k, v in (e or {}).get("roles", {}).items())
        tip = f"{roles + ' · ' if roles else ''}{AGENTS_TIP} {coverage['detail']}"
        return f'<span title="{esc(tip)}">{agents_txt([s], "tok")} · {coverage["state"]}</span>'

    def elapsed(x: dict):
        a = parse_iso(x.get("active", ""))
        b = parse_iso(x.get("green", "")) or parse_iso(x.get("merged", "")) or (now if a else None)
        return (b - a).total_seconds() if a and b else None

    def feature_list(rs) -> str:
        if not rs:
            return '<p class="muted">No ledger rows.</p>'
        out = ['<ul class="rows">']
        for f in rs:
            ok = f.get("passes") is True
            hum = (not ok) and f.get("human_act")
            cls, mark = ("done", "✓") if ok else (("hum", "⏸") if hum else ("todo", "○"))
            kind = f.get("kind")
            kchip = f'<span class="uchip">{esc(kind)}</span>' if kind and kind != "scenario" else ""
            hchip = f' <span class="muted">· {esc(f.get("human_act"))}</span>' if hum else ""
            out.append(f'<li class="{cls}"><span class="mk">{mark}</span><span><code>{esc(f.get("id"))}</code>{kchip} '
                       f'{esc(short(f.get("title", ""), 110))}{hchip}</span></li>')
        out.append("</ul>")
        return "".join(out)

    def timeline(mine: list) -> str:
        spans = []
        for x in mine:
            a = parse_iso(x.get("active", ""))
            if not a:
                continue
            st = C.norm_state(x.get("state"))
            c, r_, m_, g_ = (parse_iso(x.get(k, "")) for k in ("candidate", "review_pass", "merged", "green"))
            live = st in C.LIVE_STATES
            parts = [("impl", a, now if live else (c or r_ or m_ or now), live)]
            if c and not live:
                parts.append(("rev", c, r_ or m_ or now, st in ("review", "in_review")))
            if r_ and m_ and m_ > r_:
                parts.append(("mrg", r_, m_, False))
            if m_ and g_:
                parts.append(("t2", m_, g_, False))
            spans.append((x, [pt for pt in parts if pt[2] > pt[1]]))
        bars_all = [pt for _, ps in spans for pt in ps]
        if not bars_all:
            return ""
        t0, t1 = min(pt[1] for pt in bars_all), max(pt[2] for pt in bars_all)
        pos, ticks = time_axis(t0, t1, tz)
        dm = lambda t: loc(t).strftime("%d.%m %H:%M")
        rows = []
        for x, parts in spans:
            bars = "".join(
                f'<i class="tl {k}{" live" if lv else ""}" style="left:{pos(b):.2f}%;width:{max(pos(e) - pos(b), 0.4):.2f}%" '
                f'title="{esc({"impl": "implementing", "rev": "review", "mrg": "merge", "t2": "T2"}[k])} '
                f'{hm(b)}–{hm(e)} ({fmt_dur((e - b).total_seconds())})"></i>' for k, b, e, lv in parts)
            el = elapsed(x)
            rows.append(f'<div class="tlrow"><span class="tll"><code>{esc(x["id"].replace("slice-", "s"))}</code> '
                        f'{esc(titles.get(x["id"], ""))}</span><span class="tlt">{bars}</span>'
                        f'<span class="tlr">{fmt_dur(el) if el else ""}</span></div>')
        end_lbl = f"now {hm(now)}" if t1 >= now else f"end {hm(t1)}"
        legend = ('<span class="lg"><i class="tl impl"></i>implementing</span><span class="lg"><i class="tl rev"></i>review'
                  '</span><span class="lg"><i class="tl mrg"></i>merge</span><span class="lg"><i class="tl t2"></i>T2</span>')
        return (f'<div class="timeline"><div class="tlrow axis"><span class="tll"></span>'
                f'<span class="tlt">{ticks}</span><span class="tlr" title="scale {dm(t0)} – {dm(t1)}">{esc(end_lbl)}</span></div>'
                + "".join(rows) + f'<div class="tllegend">{legend}</div></div>')

    def acts_html(rs: list) -> str:
        if not rs:
            return ""
        items = "".join(nh_item(r, links, 140, False) for r in rs)
        return f'<div class="acts"><em>Needs you ({len(rs)})</em><ul>{items}</ul></div>'

    def seg_bar(n: int, inc: dict) -> str:
        """One segment per slice, width by ledger rows, colour by state."""
        segs = []
        mine = C.slices_of(snap, n)
        if mine:
            for x in mine:
                rs_, p_, _ = C.rows_of(features, lambda f, sid=x["id"]: f.get("slice") == sid)
                st = x.get("state", "")
                fill = 100 if C.norm_state(st) in ("merged", "green") else (round(100 * p_ / len(rs_)) if rs_ else 0)
                tip = f'{x["id"]} {titles.get(x["id"], "")} · {st} · {p_}/{len(rs_)} rows'
                segs.append((max(len(rs_), 1), C.kind_of(st), fill, tip))
        else:
            for nm in inc["planned"] or ["slices not cut yet"]:
                segs.append((1, "idle", 0, f"proposed: {short(nm, 120)}"))
        return ('<div class="segs">' + "".join(
            f'<span class="seg {kind}" style="flex:{w}" title="{esc(tip)}"><i style="width:{fill}%"></i></span>'
            for w, kind, fill, tip in segs) + "</div>")

    try:
        stall_min = int(cfg.get("SW_STALL_MINUTES", "20") or 20)
    except ValueError:
        stall_min = 20

    def chip(st: str) -> str:
        if C.known(st):
            return f'<span class="chip {C.kind_of(st)}">{esc(st)}</span>'
        return f'<span class="chip unknown" title="state not in the dashboard vocabulary">UNKNOWN {esc(st)}</span>'

    def slice_card(s: dict) -> str:
        sid, st = s.get("id", ""), s.get("state", "")
        reached = C.stage_of(st)
        rs, p, _ = C.rows_of(features, lambda f: f.get("slice") == sid)
        title = titles.get(sid) or s.get("branch", "")
        idle_chip = ""
        t_act, src = snap["activity"].get(sid, (0.0, ""))
        if t_act:
            idle = (now.timestamp() - t_act) / 60
            if idle >= stall_min:
                idle_chip = f'<span class="chip warn" title="no agent, commit or tier-log activity since {idle:.0f} min (last: {esc(src)})">idle {idle:.0f}m</span>'
        hdr = (f'<header><div><code>{esc(sid)}</code> <b>{esc(title)}</b></div>'
               f'<span>{idle_chip} {chip(st)}</span></header>')
        rows_txt = f"{p}/{len(rs)} rows" if rs else "no rows"
        details = f'<details id="d-rows-{esc(sid)}"><summary>{esc(rows_txt)}</summary>{feature_list(rs)}</details>'
        if C.norm_state(st) in ("merged", "green"):
            t2 = ts_short(s.get("green", ""))
            line = f'merged {esc(ts_short(s.get("merged", "")))} · ' + (f"T2 green {esc(t2)}" if t2 else "T2 pending")
            el = elapsed(s)
            line += (f" · took {fmt_dur(el)}" if el else "") + (f" · {eff_txt(s)}" if eff_txt(s) else "")
            return f'<article class="slice compact" id="s-{esc(sid)}">{hdr}<div class="meta">{line}</div>{details}</article>'
        steps, last = [], ""
        for i, (key, label) in enumerate(C.STAGES):
            t = ts_short(s.get(key, ""))
            done = bool(t) or i < reached
            if done and t:
                last = f"{label.lower()} {t}"
            cls = "cur" if i == reached else "done" if done else ""
            steps.append(f'<li class="{cls}" title="{esc(label)} {esc(t)}"><i></i><span>{esc(label)}</span></li>')
        bits = []
        tasks = s.get("tasks", "")
        if C.stamped(tasks):
            bits.append(linkify(short(tasks, 120), links))
        deps = s.get("depends_hard", "")
        if C.stamped(deps) and deps.strip().lower() != "none":
            bits.append(f"after {linkify(short(deps, 60), links)}")
        if s.get("rounds") not in ("", "0", "-", None):
            bits.append(f'rounds {esc(s["rounds"])}')
        el = elapsed(s)
        if el:
            bits.append(f"running {fmt_dur(el)}")
        if eff_txt(s):
            bits.append(eff_txt(s))
        if last:
            bits.append(esc(last))
        return (f'<article class="slice" id="s-{esc(sid)}">{hdr}<ol class="stepper">{"".join(steps)}</ol>'
                f'<div class="meta">{" · ".join(bits)}</div>{details}</article>')

    # ---- user scenarios ----
    scenarios = snap["scenarios"]
    scen_html = scen_tile = ""
    if scenarios:
        by_ms = any(s.get("milestone") for s in scenarios)
        key = "milestone" if by_ms else "release"
        groups = sorted({str(s.get(key) or "") for s in scenarios}, key=lambda g: (re.sub(r"\D", "", g) == "", int(re.sub(r"\D", "", g) or 0), g))
        cur_group = (ms.get("current") if by_ms and ms.get("current") in groups else None) or ("MVP" if "MVP" in groups else (groups[0] if groups else ""))
        rel_n = {g: sum(1 for s in scenarios if str(s.get(key) or "") == g) for g in groups}
        cur_s = [s for s in scenarios if str(s.get(key) or "") == cur_group]
        cnt = {k: sum(1 for s in cur_s if C.scenario_status(s, frow) == k) for k in SCEN_ST}
        cov = "".join(f'<span class="seg {SCEN_ST[k][0]}" style="flex:{cnt[k]}" title="{esc(cur_group)} {SCEN_ST[k][1]}: {cnt[k]}">'
                      f'<i style="width:{100 if k == "proven" else 0}%"></i></span>' for k in SCEN_ST if cnt[k])
        order = {g: i for i, g in enumerate(groups)}
        trs, last_stage = [], None
        for s in sorted(scenarios, key=lambda s: (str(s.get("stage", "")), order.get(str(s.get(key) or ""), 99),
                                                   int(re.sub(r"\D", "", str(s.get("id", "")))[:9] or 0), str(s.get("id", "")))):
            if s.get("stage") != last_stage:
                last_stage = s.get("stage")
                trs.append(f'<tr class="sgh"><th colspan="6">{esc(last_stage)}</th></tr>')
            st_k = C.scenario_status(s, frow)
            inc_v = s.get("increment")
            ids = s.get("proves") or []
            proving = " ".join(
                f'<code class="sr{" on" if frow.get(rid, {}).get("passes") is True else ""}" '
                f'title="{esc(rid)}: {esc(frow.get(rid, {}).get("title", "unknown row"))} · '
                f'{"proven" if frow.get(rid, {}).get("passes") is True else "not proven yet"}">{esc(rid)}</code>' for rid in ids
            ) or '<span class="muted">no row yet</span>'
            who = ", ".join(s.get("roles") or []) + (" · " + ", ".join(s.get("segments") or s.get("groups") or []) if (s.get("segments") or s.get("groups")) else "")
            trs.append(f'<tr class="{"" if str(s.get(key) or "") == cur_group else "later"}"><td><code>{esc(s.get("id"))}</code></td>'
                       f'<td title="{esc(who)}">{esc(s.get("title", ""))}</td><td>{esc(s.get(key, ""))}</td>'
                       f'<td>{esc(inc_v) if inc_v is not None else "<span class=muted>later</span>"}</td>'
                       f'<td><span class="chip {SCEN_ST[st_k][0]}">{SCEN_ST[st_k][1]}</span></td><td>{proving}</td></tr>')
        counts = (f'<b class="okt">{cnt["proven"]}</b> proven · <b>{cnt["progress"]}</b> in progress · '
                  f'<b>{cnt["todo"]}</b> not started <span class="muted">({len(cur_s)})</span>')
        scen_tile = (f'<a class="tile scov" href="#d-scenarios" title="Open the User scenarios panel">'
                     f'<em>User scenarios</em><span class="sl">{esc(cur_group)} scenarios: {counts}</span>'
                     '<span class="ssegs">' + "".join(f'<i class="{k}" style="flex:{cnt[k]}" title="{esc(cur_group)} {SCEN_ST[k][1]}: {cnt[k]}"></i>'
                                                      for k in ("proven", "progress", "todo") if cnt[k]) + '</span></a>')
        scen_html = (
            '<section class="card scen"><details id="d-scenarios"><summary class="fold">'
            f'<b>User scenarios</b> — {esc(cur_group)}: {counts}</summary>'
            '<div class="v1">' + "".join(f'<span class="kv"><b>{rel_n[g]}</b> {esc(g or "unassigned")}</span>' for g in groups) + '</div>'
            f'<div class="segs">{cov}</div><div class="barlbl">A scenario is proven when every row in its proves list passes; '
            'in progress when some do; not started when none do or it has no row yet. Hover a title for roles and segments.</div>'
            f'<div class="stbl"><table><thead><tr><th>ID</th><th>Scenario</th><th>{"Milestone" if by_ms else "Release"}</th><th>Inc</th>'
            f'<th>Status</th><th>Proving rows</th></tr></thead><tbody>{"".join(trs)}</tbody></table></div></details></section>')

    # ---- increments ----
    inc_html = []
    for inc in incs:
        n = inc["n"]
        rs, p, h = C.rows_of(features, lambda f, n=n: C.row_inc(f) == n)
        mine = C.slices_of(snap, n)
        ms_chip = f'<span class="uchip inc">{esc(inc["milestone"])}</span>' if inc.get("milestone") else ""
        ttl = inc["title"] or f"Increment {n}"
        if inc.get("no_section"):
            ms_chip += (f'<span class="uchip" title="known from {esc(", ".join(inc.get("sources", [])))}; '
                        f'write a ## Increment {n}: title section in BACKLOG.md">no BACKLOG section</span>')
        if inc["before"]:
            inc_html.append(
                f'<section class="inc closed"><details id="d-inc-{n}"><summary class="fold">'
                f'<span class="ino">{n}</span><b class="ct">{esc(short(inc["title"], 140))}</b>{ms_chip}<span class="chip done">closed</span>'
                f'<span class="muted">before adoption · {esc(short(inc.get("state_text", ""), 80))}</span></summary>'
                f'<p class="idesc"><b>Evidence.</b> {esc(inc["demo"]) or "not recorded"}</p></details></section>')
            continue
        state_lbl = incr.get("state", "") if n == cur_n else ("done" if rs and p == len(rs) else "next" if n == cur_n + 1 else "planned")
        kind = {"started": "work", "running": "work", "building": "work", "done": "done", "next": "ready", "closed": "done"}.get(state_lbl, "idle")
        body = []
        if mine:
            body.append(timeline(mine))
            body.append('<div class="slices">' + "".join(slice_card(s) for s in mine) + "</div>")
            loose = [f for f in rs if not f.get("slice") or f.get("slice") not in {s["id"] for s in mine}]
            if loose:
                body.append(f"<h4>Rows without a slice</h4>{feature_list(loose)}")
        else:
            if inc["planned"]:
                body.append('<h4>Proposed slices</h4><ul class="plan">' + "".join(f"<li>{esc(short(x, 160))}</li>" for x in inc["planned"]) + "</ul>")
            else:
                body.append('<h4>Proposed slices</h4><p class="muted uncut">slices not cut yet</p>')
            if inc.get("no_section"):
                body.append(f'<p class="muted">Known from {esc(", ".join(inc.get("sources", [])))}; BACKLOG.md has no '
                            f'<code>## Increment {n}:</code> section.</p>')
            body.append(f"<h4>Ledger rows</h4>{feature_list(rs)}")
        hum_needs = [r for r in open_needs if n in inc_set(r.get("increment", ""))]
        if mine:
            t0 = parse_iso(incr.get("started_at", ""))
            seg_lbl = (f"slices merged {sum(1 for x in mine if C.norm_state(x.get('state')) in ('merged', 'green'))} / {len(mine)}"
                       + (f" · elapsed {fmt_dur((now - t0).total_seconds())}" if t0 and n == cur_n else "")
                       + f' · <span title="{esc(AGENTS_TIP)}">{agents_txt(mine, "fresh tokens (partial)")}</span>')
        else:
            seg_lbl = f"{len(inc['planned'])} proposed slices" if inc["planned"] else "slices not cut yet"
        eta = pc["inc_eta"].get(n, "")
        iprog = (f'<div class="iprog">{seg_bar(n, inc)}<div class="barlbl">ledger rows {p} / {len(rs)} · {seg_lbl}'
                 + (f' · {esc(eta)}' if eta and eta != "done" else "") + '</div>'
                 + (f'<span class="muted">{h} wait on a human act · </span>' if h else "")
                 + f'{acts_html(hum_needs)}</div>')
        demo_body = f'<p class="idesc"><b>Exit demo.</b> {esc(inc["demo"]) or "not written yet"}</p>{"".join(body)}'
        retro = f"increment-{n}.md"
        has_retro = retro in snap["retros"]
        if inc.get("closed") or (n < cur_n and ((rs and p == len(rs)) or has_retro)):
            mts = sorted(t for t in (parse_iso(x.get("merged", "")) for x in mine) if t)
            mrange = ""
            if mts:
                a_, b_ = loc(mts[0]).strftime("%d.%m %H:%M"), loc(mts[-1]).strftime("%d.%m %H:%M")
                mrange = f" · merged {a_}" + (f" – {b_}" if b_ != a_ else "")
            retro_a = f' · <a href="retros/{retro}">retro</a>' if has_retro else ""
            inc_html.append(
                f'<section class="inc closed"><details id="d-inc-{n}"><summary class="fold">'
                f'<span class="ino">{n}</span><b class="ct">{esc(ttl)}</b>{ms_chip}<span class="chip done">closed</span>'
                f'<span class="muted">{p} / {len(rs)} rows pass{esc(mrange)}{retro_a}</span></summary>'
                f'{iprog}{demo_body}</details></section>')
            continue
        inc_html.append(
            f'<section class="inc {"open" if n == cur_n else ""}"><details id="d-inc-{n}" {"open" if n == cur_n else ""}>'
            f'<summary><div class="ihead"><span class="ino">{n}</span><div><h3>{esc(ttl)}{ms_chip}</h3></div>'
            f'<span class="chip {kind}">{esc(state_lbl or "planned")}</span></div>{iprog}'
            f'</summary>{demo_body}</details></section>')

    # ---- progress tile ----
    before = [i for i in incs if i["before"]]
    avg = total_steps / max(len(per), 1)
    pv1 = ""
    before_txt = ""
    if before:
        b_steps = avg * len(before)
        b_tip = (f"Increments {before[0]['n']} to {before[-1]['n']}, closed before this project adopted the method "
                 f"(MILESTONES.md); shown for scale at the average backlog increment size and not counted in the percentage.")
        pv1 = (f'<span class="pseg pv1" style="flex:{b_steps:.2f}" title="{esc(b_tip)}"><i style="width:100%"></i></span>'
               '<span class="psep"></span>')
        before_txt = (f'<small><i class="v1n" title="{esc(b_tip)}">■ before adoption: increments {before[0]["n"]}–{before[-1]["n"]}, '
                      'not counted</i></small>')
    prog_segs = pv1 + "".join(
        f'<span class="pseg" style="flex:{t}" title="increment {n} {esc(ttl)}: {d:.1f}/{t:g} slice-equivalents">'
        f'<i style="width:{100 * d / t:.0f}%"></i></span>' for n, ttl, t, d in per)
    uns = C.unsized(snap, incs)
    u_ns = ", ".join(str(i["n"]) for i in uns)
    unsized_txt = ""
    if uns:
        u_tip = (f"Increments {u_ns} have neither slice rows nor proposed slices, so their size is unknown: they are left out "
                 "of the percentage, neither done nor remaining, until plan-increment or prepare writes their slices; "
                 "shown hatched at the average increment size for scale.")
        prog_segs += "".join(f'<span class="pseg pun" style="flex:{avg:.2f}" title="increment {i["n"]} '
                             f'{esc(i["title"])}: not sized, not counted"></span>' for i in uns)
        unsized_txt = (f'<small><i class="unn" title="{esc(u_tip)}">▨ not sized yet: increment{"s" if len(uns) > 1 else ""} '
                       f'{esc(u_ns)}, not counted</i></small>')
    vocab = ", ".join(f"{int(100 * c)}% {s}" for s, (_, _, c) in C.STATES.items() if c)
    prog_tip = ("Backlog progress in slice-equivalents: every slice of every increment counts 1 (from the slice table, or the "
                f"increment's proposed slices before it has rows); a slice earns credit by state ({vocab}; merged earns 100% once "
                "T2 is green). An increment with neither slice rows nor proposed slices is not sized: it is left out of the "
                "percentage, neither done nor remaining, and shown hatched"
                + (f" (now: {u_ns})" if uns else "") + ". Increments: " + "; ".join(f"{n}: {d:.1f}/{t:g}" for n, _, t, d in per))
    dl = C.delta(history or [], prog, now, tz)
    spark = ""
    if dl:
        spark = (f'<small class="delta" title="Progress gained since {esc(dl["when"])}. Recorded points: {esc(dl["points"])}">'
                 f'{"▲" if dl["delta"] >= 0.05 else "•"} +{max(dl["delta"], 0):.1f}%<span class="pace"> since {esc(dl["when"])}</span></small>')
    eta_html = (f'<small class="eta" title="Pace = slice-equivalents finished since the first slice was ready, per wall-clock hour; '
                f'later increments have bigger slices and human gates, so treat it as optimistic">{esc(pc["eta"])}'
                f'<span class="pace"> at today&#x27;s pace</span></small>') if pc["eta"] else ""
    ms_lbl = f'{ms.get("current", "")} {ms.get("state", "")} · ' if ms.get("current") else ""
    prog_tile = (f'<div class="tile prog" title="{esc(prog_tip)}"><em>Backlog progress · {esc(ms_lbl)}increment {cur_n} {esc(incr.get("state", ""))}</em>'
                 f'<div class="prow"><b>{prog:.0f}<span>%{" of sized" if uns else ""} · {done_steps:.1f}/{total_steps:g} slices</span></b>'
                 f'<span class="pright">{spark}{eta_html}</span></div><div class="psegs">{prog_segs}</div>{before_txt}{unsized_txt}</div>')

    # ---- budget tile: one compact row per subscription, details in the tooltip ----
    dual = cfg.get("SW_PROFILE") == "dual"
    roles = {"claude": "coordinator and reviewers", "codex": "Codex writers"} if dual else {}
    try:
        max_age = dt.timedelta(seconds=int(cfg.get("SW_READING_MAX_AGE", "5400") or 5400))
    except ValueError:
        max_age = dt.timedelta(seconds=5400)

    def runtime_row(rt: str, usage: dict) -> str:
        short = rt.capitalize() if rt else "Weekly"
        label = f"{short} · {roles[rt]}" if rt in roles else short
        bd = C.budget(snap, per, now, usage, rt)
        hold, stop = bd["hold"], bd["stop"]
        if not bd["known"]:
            where = f"no {rt} reading in metrics/usage*.jsonl" if rt else "no usage reading in metrics/usage.jsonl"
            return (f'<div class="rtb warn" title="{esc(label)}: {esc(where)}"><span class="rtl">{esc(short)}</span><b>—</b>'
                    f'<i class="bbar wb"></i><small class="rth"></small><span class="vchip warn">UNKNOWN · no reading</span></div>')
        used, f5, fc = bd["used"], bd["five"], bd["fc"]
        age = now - bd["at"] if bd["at"] else None
        stale = age is None or age > max_age
        age_txt = ("no time" if age is None else f"{int(age.total_seconds() // 3600)} h old" if age >= dt.timedelta(hours=2)
                   else f"{int(age.total_seconds() // 60)} min old")
        reset_txt = loc(bd["reset"] + dt.timedelta(seconds=30)).strftime("%a %H:%M") if bd["reset"] else "—"
        tip = "\n".join([label, f"weekly {used:.0f}% used · resets {reset_txt}",
                          *([f'5h {int(f5)}% · ↻{ts_short(usage.get("five_hour_reset"))}'] if isinstance(f5, (int, float)) else []),
                          f"dispatch hold {hold}% · stop {stop}%", f"reading {age_txt}" + (" (stale)" if stale else ""), *bd["lines"]]
                         + ([f"sized increments only; {u_ns} not sized, not counted"] if uns and fc else []))
        proj = ""
        hours = (f'{fc["hours_left"]:.0f} h · ' if fc and fc["hours_left"] > 0 else "")
        side = (f'<small class="rth" title="hours of work to the stop line at this week\'s burn; weekly reset">'
                f'{hours}↻{esc(reset_txt)}</small>')
        if fc:
            end = min(fc["end"], 100)
            proj = (f'<i class="bp" style="left:{min(used, 100):.1f}%;width:{max(end - min(used, 100), 0):.1f}%" '
                    f'title="backlog projection: ends at ≈{fc["end"]:.0f}% of the week ({"fits" if fc["fits"] else "over the stop line"})"></i>')
        marks = (f'<i class="mark" style="left:{hold}%" title="dispatch hold {hold}%"></i>'
                 f'<i class="mark stop" style="left:{min(stop, 100)}%" title="stop line {stop}%"></i>')
        chip = f'<span class="vchip warn">stale · {esc(age_txt)}</span>' if stale else ""
        return (f'<div class="rtb {bd["kind"]}" title="{esc(tip)}"><span class="rtl">{esc(short)}</span>'
                f'<b>{int(used)}<span>%</span></b>'
                f'<i class="bbar wb"><i class="bu" style="width:{min(used, 100):.1f}%"></i>{proj}{marks}</i>{side}{chip}</div>')

    rows_html = "".join(runtime_row(rt, u) for rt, u in C.budget_runtimes(snap))
    budget_tile = f'<div class="tile budget"><em>Weekly budget · hover for details</em>{rows_html}</div>'

    # ---- money tile ----
    mo = C.money(snap)
    money_tile = ""
    if mo:
        cap_txt = f'{mo["cap"]:g}' if mo["cap"] else "no cap"
        pctm = 100 * mo["spent"] / mo["cap"] if mo["cap"] else 100
        money_tile = (f'<div class="tile money {mo["kind"]}" title="metrics/money.jsonl, {mo["entries"]} entries; cap SW_MONEY_CAP">'
                      f'<em>Money · {esc(mo["currency"])}</em>'
                      f'<b>{mo["left"]:.2f}<span> left of {esc(cap_txt)}</span></b>'
                      f'<i class="mini"><span style="width:{min(pctm, 100):.1f}%"></span></i>'
                      f'<small>{mo["spent"]:.2f} spent and exposed'
                      + (f' · also {esc(", ".join(mo["other"]))} entries, not converted' if mo["other"] else "") + '</small></div>')

    # ---- header line: could start now, head, updated ----
    rn = C.ready_now(snap)
    cap_txt = f'WRITERS {rn["writers"]}/{rn["cap"] or "?"}'
    ready_html = (f'<span class="readyn" title="{esc(chr(10).join(rn["ready"]) or "no slice can start now")}&#10;{esc(cap_txt)}">'
                  f'could start now: {len(rn["ready"])}</span> · ')
    head_code = (f'<code title="{esc(head)}">{esc(head.split(" ")[0])}</code> · ' if head else "")
    unknown = C.unknown_states(snap)
    unknown_html = (f'<div class="hold" title="add them to the vocabulary in dashboard/compute.py upstream">'
                    f'Slice states outside the vocabulary, rendered UNKNOWN: {esc(", ".join(unknown))}</div>') if unknown else ""
    unparsed = snap.get("backlog_unparsed") or []
    nosec = [str(i["n"]) for i in incs if i.get("no_section")]
    backlog_html = ((f'<div class="hold" title="the dashboard reads only ## Increment N: title headings; the increments under '
                     f'these are not read from BACKLOG.md">BACKLOG.md headings the dashboard cannot read: '
                     f'{esc("; ".join(unparsed))}. Write one <code>## Increment N: title</code> section per increment.</div>')
                    if unparsed else "")
    backlog_html += ((f'<div class="hold" title="known from MILESTONES.md, FEATURES.json or NEEDS-HUMAN.md; rendered from what '
                      f'those files say">Increments without a BACKLOG.md section: {esc(", ".join(nosec))}</div>') if nosec else "")
    holds_html = "".join(f'<div class="hold" title="{esc(h.get("resume_when", ""))}">⏸ {esc(short(h["reason"], 200))}'
                         + (f' <span class="muted">· {esc(short(h.get("resume_when", ""), 120))}</span>' if h.get("resume_when") else "")
                         + '</div>' for h in snap["holds"])

    # ---- the owner's view: inbox, veto clocks, questions, milestones, contracts, log ----
    needs_html = "".join(nh_item(r, links, 120, True) for r in open_needs) or '<li class="muted">nothing open</li>'
    clocks = C.veto_clocks(snap, now, tz)
    clocks_html = "".join(
        f'<li title="{esc(d["title"])}"><code>{esc(d["id"])}</code> <span class="chip {"warn" if d["left"] <= 1 else "ready"}">'
        f'{d["left"]} d left</span> {esc(short(d["title"], 110))} <span class="muted">· class {esc(d["class"])} · veto by {esc(d["veto_by"])}</span></li>'
        for d in clocks) or '<li class="muted">no default inside its veto window</li>'
    qs = C.open_questions(snap)
    qs_html = "".join(
        f'<li title="default at due: {esc(d["default"])}"><code>{esc(d["id"])}</code> {esc(short(d["title"], 110))}'
        f'<span class="muted"> · due {esc(short(d["due"], 30))}</span></li>' for d in qs)
    rows_by_ms = {}
    for f in features:
        rows_by_ms.setdefault(f.get("milestone") or "", []).append(f)
    ms_items = []
    for m in snap["milestones"]:
        rs_m = rows_by_ms.get(m["id"], [])
        p_m = sum(1 for f in rs_m if f.get("passes") is True)
        gates_open = sum(1 for g in m["gates"] if g.get("status", "").strip().lower() not in ("closed", "waived", "done") and g.get("gate rows (FEATURES.json ids)", "").strip())
        st = m["state"].split(" ")[0].strip("(),").lower()
        kind = {"building": "work", "accepting": "ready", "releasing": "ready", "operating": "done", "closed": "done"}.get(st, "idle")
        cur = " ◂" if m["id"] == ms.get("current") else ""
        ms_items.append(f'<li><code>{esc(m["id"])}</code> <span class="chip {kind}">{esc(st or "planned")}</span> {esc(short(m["title"], 90))}{cur}'
                        f'<span class="muted"> · {p_m} / {len(rs_m)} rows pass' + (f' · {gates_open} gate families open' if gates_open else "") + '</span></li>')
    contracts_html = "".join(
        f'<li><code>{esc(c.get("id"))}</code> <span class="chip {"done" if c.get("state") == "frozen" else "idle"}">'
        f'{esc(c.get("state"))}</span> <span class="muted">{esc(c.get("sha", ""))}</span></li>' for c in snap["contracts"]) or '<li class="muted">none</li>'
    queued = snap["queued"]
    progress_html = "".join(f'<li>{esc(heading_local(p, tz))}</li>' for p in snap["progress"]) or '<li class="muted">no entries</li>'

    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "project"
    tiles_cls = "tiles four" if money_tile else "tiles"
    return unlink_missing(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="30">
<title>{esc(name)} progress</title><style>{CSS}</style></head><body><main>
<header class="hd"><div class="hrow"><h1>{esc(name)}</h1>
<span class="muted">{ready_html}{head_code}updated {esc(hm(now))}</span></div>
<div class="{tiles_cls}">
{prog_tile}
{scen_tile}
{budget_tile}
{money_tile}
</div>
{unknown_html}{backlog_html}{holds_html}
</header>
{scen_html}
<h2>Increments</h2>{''.join(inc_html) or '<p class="muted">No increments in BACKLOG.md yet.</p>'}
<div class="two">
<div class="card"><h4>Needs a human ({len(open_needs)} open)</h4><ul class="plain">{needs_html}</ul></div>
<div class="card"><h4>Veto clocks ({len(clocks)} open)</h4><ul class="plain">{clocks_html}</ul>
{f'<h4>Open questions ({len(qs)})</h4><ul class="plain">{qs_html}</ul>' if qs else ''}</div>
</div>
<div class="two">
<div class="card"><h4>Milestones</h4><ul class="plain">{''.join(ms_items) or '<li class="muted">none in MILESTONES.md</li>'}</ul>
<h4>Contracts</h4><ul class="plain">{contracts_html}</ul></div>
<div class="card">{f'<h4>Queued</h4><ul class="plain">{"".join(f"<li>{esc(short(q, 200))}</li>" for q in queued)}</ul>' if queued else ''}
<h4>Latest log entries</h4><ul class="plain">{progress_html}</ul></div>
</div></main>
<script>/* keep each <details id> open or closed across the auto-refresh, per viewer; defaults stand when storage is blocked */
(function(){{var K="sw-dash:{slug}:open:";document.querySelectorAll("details[id]").forEach(function(d){{
try{{var v=localStorage.getItem(K+d.id);if(v==="1")d.open=true;else if(v==="0")d.open=false;}}catch(e){{}}
d.addEventListener("toggle",function(){{try{{localStorage.setItem(K+d.id,d.open?"1":"0");}}catch(e){{}}}});}});
var t=document.querySelector("a.tile.scov"),p=document.getElementById("d-scenarios");
if(t&&p)t.addEventListener("click",function(ev){{ev.preventDefault();p.open=true;p.scrollIntoView({{behavior:"smooth",block:"start"}});}});}})();
</script></body></html>""")


def heading_local(h: str, tz: dt.tzinfo) -> str:
    """'2026-10-15 13:40Z, coordinator (...)' with the time shown in the display zone."""
    m = re.match(r"(\d{4}-\d{2}-\d{2})[ T](\d{2}):(\d{2})Z(.*)$", h)
    if not m:
        return h
    t = dt.datetime.fromisoformat(f"{m.group(1)}T{m.group(2)}:{m.group(3)}:00+00:00").astimezone(tz)
    return t.strftime("%Y-%m-%d %H:%M") + m.group(4)
