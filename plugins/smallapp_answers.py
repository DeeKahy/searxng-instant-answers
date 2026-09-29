# pylint: disable=missing-module-docstring,too-many-lines
"""Instant answers for search.smallapp.cc.

One plugin, many small handlers.  Each handler gets the (stripped) query and
returns an :py:class:`InstantAnswer` or ``None``; the first hit wins.  Handlers
are pure Python + stdlib (weather is the one exception: it calls Open-Meteo).

Answers render through ``answer/instant.html`` and are styled/animated by
``sxng-extras.{css,js}``.  Anything interactive (re-roll, timers, copy, the
password slider) runs client-side, so the server only renders the first state.

Handlers marked ``local=True`` are *tools* whose query is obviously not a web
search ("roll 2d6", "base64 decode …", a pasted JWT).  For those the engines
are skipped entirely: the answer is instant, and the query — which may contain
something private — is never sent to Google & co.
"""

from __future__ import annotations

import base64
import binascii
import calendar
import concurrent.futures
import datetime as dt
import html
import ipaddress
import json
import math
import random
import re
import secrets
import socket
import string
import time
import unicodedata
import urllib.parse
import uuid
from http import HTTPStatus

import typing as t

from markupsafe import Markup, escape

from searx.plugins import Plugin, PluginInfo
from searx.result_types import EngineResults
from searx.result_types.answer import BaseAnswer

if t.TYPE_CHECKING:
    from searx.extended_types import SXNG_Request
    from searx.plugins import PluginCfg
    from searx.search import SearchWithPlugins


# --------------------------------------------------------------------------
# answer type
# --------------------------------------------------------------------------


class InstantAnswer(BaseAnswer, kw_only=True):
    """A card in the answers area.  ``body`` is trusted HTML built here (every
    user-supplied string goes through :py:func:`e`)."""

    template: str = "answer/instant.html"
    kind: str = ""
    icon: str = ""
    title: str = ""
    value: str = ""
    sub: str = ""
    body: str = ""
    rows: list[list[str]] = []
    copy: str = ""
    source: str = ""

    def __hash__(self):
        return hash((self.kind, self.title, self.value, self.body))


COPY_ICON = '<svg class="ia-ico" viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V6a2 2 0 0 1 2-2h8"/></svg>'


def e(s: t.Any) -> str:
    return str(escape(str(s)))


def rows_html(rows: list[tuple[str, t.Any]], copy: bool = True) -> str:
    out = ['<dl class="ia-kv">']
    for k, v in rows:
        v = str(v)
        btn = f'<button class="ia-copy" data-copy="{e(v)}" title="Copy">{COPY_ICON}</button>' if copy and v else ""
        out.append(f"<dt>{e(k)}</dt><dd><span>{e(v)}</span>{btn}</dd>")
    out.append("</dl>")
    return "".join(out)


def chips(items: list[str], cls: str = "") -> str:
    return "".join(f'<button class="ia-chip {cls}" data-copy="{e(i)}">{e(i)}</button>' for i in items)


def search_link(q: str, label: str | None = None) -> str:
    return f'<a class="ia-chip ia-try" href="./search?q={urllib.parse.quote(q)}">{e(label or q)}</a>'


# --------------------------------------------------------------------------
# registry
# --------------------------------------------------------------------------


class Handler(t.NamedTuple):
    fn: t.Callable[[str, str], InstantAnswer | None]
    local: bool


HANDLERS: list[Handler] = []
EXAMPLES: dict[str, list[str]] = {}


def handler(section: str, examples: list[str], local: bool = False):
    def deco(fn):
        HANDLERS.append(Handler(fn, local))
        EXAMPLES.setdefault(section, []).extend(examples)
        return fn

    return deco


RNG = random.SystemRandom()
NUM = r"-?\d+(?:[.,]\d+)?"


def num(s: str) -> float:
    return float(s.replace(",", "."))


def fmt(x: float, digits: int = 6) -> str:
    if abs(x - round(x)) < 1e-9 and abs(x) < 1e15:
        return f"{int(round(x)):,}".replace(",", " ")
    return f"{x:,.{digits}f}".rstrip("0").rstrip(".").replace(",", " ")


# ==========================================================================
# fun & random
# ==========================================================================

DICE_RE = re.compile(
    r"(?:(?P<verb>roll|throw|toss|slå|kast|rul)\s+)?(?:(?:a|an|one|en|et)\s+)?"
    r"(?:(?P<n>\d{1,2})\s*)?(?:d(?P<d>\d{1,4})|(?P<word>dice|die|terninger|terning))"
    r"\s*(?P<mod>[+-]\s*\d{1,4})?"
)


def dice_html(values: list[int], sides: int) -> str:
    out = []
    for v in values:
        if sides == 6:
            pips = "".join("<i></i>" for _ in range(v))
            out.append(f'<span class="ia-die d6" data-v="{v}">{pips}</span>')
        else:
            out.append(f'<span class="ia-die dn" data-v="{v}"><b>{v}</b><small>d{sides}</small></span>')
    return "".join(out)


@handler("Fun & random", ["roll 2d6+3", "roll d20", "roll dice"], local=True)
def h_dice(q, ql):
    if ql in ("roll", "rul", "kast"):
        n, sides, mod = 1, 6, 0
    else:
        m = DICE_RE.fullmatch(ql)
        if not m:
            return None
        n = int(m["n"] or 1)
        sides = int(m["d"] or 6)
        mod = int(m["mod"].replace(" ", "")) if m["mod"] else 0
        # a bare "d3" is d3.js, not a die: without a verb/count only accept real dice
        if m["d"] and not m["verb"] and not m["n"] and sides not in (4, 6, 8, 10, 12, 20, 100):
            return None
    if not (1 <= n <= 50 and 2 <= sides <= 1000):
        return None
    values = [RNG.randint(1, sides) for _ in range(n)]
    total = sum(values) + mod
    spec = f"{n}d{sides}" + (f"{mod:+d}" if mod else "")
    body = (
        f'<div class="ia-dice" data-n="{n}" data-sides="{sides}" data-mod="{mod}">{dice_html(values, sides)}</div>'
        f'<div class="ia-actions"><button class="ia-btn" data-ia="dice">🎲 Roll again</button></div>'
    )
    sub = "" if n == 1 and not mod else " + ".join(map(str, values)) + (f" {mod:+d}".replace("+", "+ ").replace("-", "− ") if mod else "")
    return InstantAnswer(kind="dice", icon="🎲", title=f"Roll {spec}", value=str(total), sub=sub, body=body)


@handler("Fun & random", ["flip a coin", "heads or tails", "plat eller krone"], local=True)
def h_coin(q, ql):
    if not re.fullmatch(
        r"(?:(?:flip|toss)\s+(?:a\s+)?coin|coin\s*(?:flip|toss)?|heads\s+or\s+tails|tails\s+or\s+heads|"
        r"plat\s+eller\s+krone|krone\s+eller\s+plat|slå\s+plat\s+og\s+krone)\??",
        ql,
    ):
        return None
    heads = RNG.random() < 0.5
    dk = "plat" in ql or "krone" in ql
    label = ("Krone" if heads else "Plat") if dk else ("Heads" if heads else "Tails")
    body = (
        f'<div class="ia-coin-stage"><div class="ia-coin {"heads" if heads else "tails"}" data-dk="{int(dk)}">'
        f'<span class="f">{"K" if dk else "H"}</span><span class="b">{"P" if dk else "T"}</span></div></div>'
        f'<div class="ia-actions"><button class="ia-btn" data-ia="coin">🪙 Flip again</button></div>'
    )
    return InstantAnswer(kind="coin", icon="🪙", title="Coin flip", value=label, body=body)


@handler("Fun & random", ["random number 1-100", "pick a number between 1 and 6"], local=True)
def h_number(q, ql):
    m = re.fullmatch(
        r"(?:random|pick|choose|generate|rng|tilfældigt)\s+(?:a\s+)?(?:number|int|integer|tal)?"
        r"(?:\s+(?:between|from|mellem|fra)?\s*(-?\d{1,12})\s*(?:-|–|to|and|til|og|\.\.)\s*(-?\d{1,12}))?",
        ql,
    )
    if not m or not (m[1] or re.search(r"number|int|tal|rng", ql)):
        return None
    lo, hi = (int(m[1]), int(m[2])) if m[1] else (1, 100)
    if lo > hi:
        lo, hi = hi, lo
    v = RNG.randint(lo, hi)
    body = (
        f'<div class="ia-actions" data-lo="{lo}" data-hi="{hi}">'
        f'<button class="ia-btn" data-ia="number">🔁 Again</button></div>'
    )
    return InstantAnswer(kind="number", icon="🔢", title=f"Random number {lo}–{hi}", value=str(v), body=body, copy=str(v))


def split_options(s: str) -> list[str]:
    s = s.strip().rstrip("?")
    parts = re.split(r"\s*(?:,|\||;|\s+or\s+|\s+eller\s+|\s+vs\.?\s+)\s*", s)
    return [p for p in (x.strip() for x in parts) if p]


@handler("Fun & random", ["pick pizza, sushi or tacos", "shuffle alice, bob, carol"], local=True)
def h_pick(q, ql):
    m = re.fullmatch(r"(pick|choose|decide|vælg|shuffle|bland)\s+(?:between\s+|from\s+|mellem\s+)?(.+)", q, re.I)
    if not m or re.match(r"(?:a\s+)?(?:random\s+)?(?:number|int|tal)\b", m[2], re.I):
        return None
    opts = split_options(m[2])
    if len(opts) < 2 or len(opts) > 100:
        return None
    data = e(json.dumps(opts))
    if m[1].lower() in ("shuffle", "bland"):
        RNG.shuffle(opts)
        items = "".join(f"<li>{e(o)}</li>" for o in opts)
        body = (
            f'<ol class="ia-shuffle">{items}</ol>'
            f'<div class="ia-actions" data-opts="{data}"><button class="ia-btn" data-ia="shuffle">🔀 Shuffle again</button></div>'
        )
        return InstantAnswer(kind="shuffle", icon="🔀", title=f"Shuffled {len(opts)} items", body=body, copy="\n".join(opts))
    choice = RNG.choice(opts)
    others = "".join(f"<span>{e(o)}</span>" for o in opts)
    body = (
        f'<div class="ia-options">{others}</div>'
        f'<div class="ia-actions" data-opts="{data}"><button class="ia-btn" data-ia="pick">🎯 Pick again</button></div>'
    )
    return InstantAnswer(kind="pick", icon="🎯", title=f"Picked from {len(opts)} options", value=choice, body=body)


EIGHTBALL = [
    "It is certain.", "It is decidedly so.", "Without a doubt.", "Yes — definitely.", "You may rely on it.",
    "As I see it, yes.", "Most likely.", "Outlook good.", "Yes.", "Signs point to yes.",
    "Reply hazy, try again.", "Ask again later.", "Better not tell you now.", "Cannot predict now.",
    "Concentrate and ask again.", "Don't count on it.", "My reply is no.", "My sources say no.",
    "Outlook not so good.", "Very doubtful.",
]


@handler("Fun & random", ["8ball will it rain tomorrow?", "yes or no"], local=True)
def h_8ball(q, ql):
    if re.fullmatch(r"(?:yes\s+or\s+no|ja\s+eller\s+nej)\??", ql):
        yes = RNG.random() < 0.5
        dk = ql.startswith("ja")
        v = ("Ja" if yes else "Nej") if dk else ("Yes" if yes else "No")
        body = '<div class="ia-actions"><button class="ia-btn" data-ia="yesno">🔁 Ask again</button></div>'
        return InstantAnswer(kind="yesno", icon="🤔", title="Yes or no", value=v, body=body)
    m = re.fullmatch(r"(?:magic\s+)?8[\s-]?ball\b[\s:,]*(.*)", q, re.I)
    if not m:
        return None
    body = (
        f'<div class="ia-8ball"><div class="ia-8ball-window"><span>{e(RNG.choice(EIGHTBALL))}</span></div></div>'
        f'<div class="ia-actions" data-opts="{e(json.dumps(EIGHTBALL))}"><button class="ia-btn" data-ia="8ball">🎱 Shake</button></div>'
    )
    return InstantAnswer(kind="8ball", icon="🎱", title=m[1] or "Magic 8-ball", body=body)


@handler("Fun & random", ["rock paper scissors"], local=True)
def h_rps(q, ql):
    if not re.fullmatch(r"rock\W*paper\W*(?:or\s+|and\s+)?scissors?|sten\W*saks\W*(?:eller\s+|og\s+)?papir|rps", ql):
        return None
    body = (
        '<div class="ia-rps"><button data-rps="0">🪨<small>Rock</small></button>'
        '<button data-rps="1">📄<small>Paper</small></button>'
        '<button data-rps="2">✂️<small>Scissors</small></button></div>'
        '<div class="ia-rps-out" aria-live="polite">Pick one — I have already decided.</div>'
    )
    return InstantAnswer(kind="rps", icon="✊", title="Rock, paper, scissors", body=body)


# ==========================================================================
# generators
# ==========================================================================

PW_SYMBOLS = "!@#$%^&*-_=+?"


def make_password(n: int, symbols: bool = True) -> str:
    alphabet = string.ascii_letters + string.digits + (PW_SYMBOLS if symbols else "")
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(n))
        if (
            any(c.islower() for c in pw)
            and any(c.isupper() for c in pw)
            and any(c.isdigit() for c in pw)
            and (not symbols or n < 8 or any(c in PW_SYMBOLS for c in pw))
        ):
            return pw


@handler("Generators", ["password 24", "uuid", "lorem ipsum 2"], local=True)
def h_password(q, ql):
    m = re.fullmatch(
        r"(?:generate\s+(?:a\s+)?|random\s+|strong\s+|new\s+)?(?:password|passwd|pwgen|adgangskode|kodeord)"
        r"(?:\s+generator)?(?:\s+(\d{1,3}))?(?:\s*(?:chars?|characters?|long|tegn))?",
        ql,
    )
    if not m:
        return None
    n = max(8, min(128, int(m[1] or 20)))
    pw = make_password(n)
    bits = n * math.log2(len(string.ascii_letters + string.digits + PW_SYMBOLS))
    body = (
        f'<div class="ia-pw"><code class="ia-pw-out">{e(pw)}</code>'
        f'<button class="ia-copy big" data-copy-from=".ia-pw-out" title="Copy">{COPY_ICON} Copy</button></div>'
        f'<div class="ia-pw-opts"><label>Length <input type="range" min="8" max="64" value="{min(n, 64)}" class="ia-pw-len">'
        f'<output>{n}</output></label>'
        f'<label><input type="checkbox" class="ia-pw-sym" checked> Symbols</label>'
        f'<button class="ia-btn" data-ia="password">🔁 New</button></div>'
        f'<div class="ia-note">Generated with a CSPRNG; regenerated ones never leave your browser. '
        f'≈{int(bits)} bits of entropy.</div>'
    )
    return InstantAnswer(kind="password", icon="🔑", title="Password generator", body=body)


@handler("Generators", [], local=True)
def h_uuid(q, ql):
    if not re.fullmatch(r"(?:generate\s+|new\s+|random\s+)?(?:uuid|guid)(?:\s*v?4)?|uuid\s*v?7|uuidv7", ql):
        return None
    if "7" in ql:
        ms = int(time.time() * 1000)
        raw = ms.to_bytes(6, "big") + secrets.token_bytes(10)
        b = bytearray(raw)
        b[6] = (b[6] & 0x0F) | 0x70
        b[8] = (b[8] & 0x3F) | 0x80
        u, ver = str(uuid.UUID(bytes=bytes(b))), "v7"
    else:
        u, ver = str(uuid.uuid4()), "v4"
    body = (
        f'<div class="ia-pw"><code class="ia-uuid-out">{u}</code>'
        f'<button class="ia-copy big" data-copy-from=".ia-uuid-out">{COPY_ICON} Copy</button></div>'
        f'<div class="ia-actions"><button class="ia-btn" data-ia="uuid" data-ver="{ver}">🔁 New</button></div>'
    )
    return InstantAnswer(kind="uuid", icon="🆔", title=f"UUID {ver}", body=body)


LOREM = (
    "lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor incididunt ut labore et dolore "
    "magna aliqua ut enim ad minim veniam quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo "
    "consequat duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur "
    "excepteur sint occaecat cupidatat non proident sunt in culpa qui officia deserunt mollit anim id est laborum"
).split()


def lorem_sentence() -> str:
    w = [RNG.choice(LOREM) for _ in range(RNG.randint(7, 16))]
    s = " ".join(w)
    return s[0].upper() + s[1:] + "."


@handler("Generators", [], local=True)
def h_lorem(q, ql):
    m = re.fullmatch(r"lorem(?:\s+ipsum)?(?:\s+(\d{1,2}))?(?:\s*(paragraphs?|p|words?|w|sentences?|s))?", ql)
    if not m:
        return None
    n = int(m[1] or 3)
    unit = (m[2] or "p")[0]
    if unit == "w":
        text = " ".join(["Lorem", "ipsum"] + [RNG.choice(LOREM) for _ in range(max(0, n - 2))][: max(0, n - 2)])
        paras = [text[: len(text)] + "."]
    elif unit == "s":
        paras = [" ".join(lorem_sentence() for _ in range(n))]
    else:
        paras = [" ".join(lorem_sentence() for _ in range(RNG.randint(4, 7))) for _ in range(min(n, 20))]
        paras[0] = "Lorem ipsum dolor sit amet, " + paras[0][0].lower() + paras[0][1:]
    body = "".join(f"<p>{e(p)}</p>" for p in paras)
    return InstantAnswer(kind="lorem", icon="📝", title="Lorem ipsum", body=f'<div class="ia-lorem">{body}</div>', copy="\n\n".join(paras))


@handler("Generators", ["qr https://search.smallapp.cc"], local=True)
def h_qr(q, ql):
    m = re.fullmatch(r"(?:qr|qr\s*code|qrcode)\s+(.+)", q, re.I | re.S)
    if not m:
        return None
    try:
        import segno  # pylint: disable=import-outside-toplevel
    except ImportError:
        return None
    data = m[1].strip()
    qr = segno.make(data, error="m", micro=False)
    svg = qr.svg_inline(scale=6, border=2, dark="#000", light="#fff")
    body = f'<div class="ia-qr">{svg}</div><div class="ia-note">{e(data)}</div>'
    return InstantAnswer(kind="qr", icon="▦", title="QR code", body=body, copy=data)


# ==========================================================================
# timers
# ==========================================================================

UNIT_SECONDS = [
    (r"h|hr|hrs|hours?|t|timer?|time", 3600),
    (r"m|min|mins|minutes?|minut|minutter", 60),
    (r"s|sec|secs|seconds?|sek|sekund|sekunder", 1),
]


def parse_duration(s: str) -> int | None:
    s = s.strip().lower()
    if not s:
        return None
    m = re.fullmatch(r"(?:(\d{1,2}):)?(\d{1,3}):(\d{2})", s)
    if m:
        return int(m[1] or 0) * 3600 + int(m[2]) * 60 + int(m[3])
    if re.fullmatch(r"\d+(?:[.,]\d+)?", s):
        return int(num(s) * 60)
    total, pos = 0.0, 0
    tok = re.compile(r"\s*(\d+(?:[.,]\d+)?)\s*([a-zæøå]+)\s*(?:and|og|,)?")
    while pos < len(s):
        m = tok.match(s, pos)
        if not m:
            return None
        for pat, mult in UNIT_SECONDS:
            if re.fullmatch(pat, m[2]):
                total += num(m[1]) * mult
                break
        else:
            return None
        pos = m.end()
    return int(total) or None


def hms(sec: int) -> str:
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


@handler("Timers & time", ["timer 5 min", "25 minute timer", "pomodoro", "stopwatch"], local=True)
def h_timer(q, ql):
    if re.fullmatch(r"stop\s*watch|stopur|stopwatch", ql):
        body = (
            '<div class="ia-clock" data-mode="stopwatch" data-secs="0"><span class="ia-clock-face">00:00.0</span></div>'
            '<div class="ia-actions"><button class="ia-btn" data-ia="start">▶ Start</button>'
            '<button class="ia-btn ghost" data-ia="lap">⏱ Lap</button>'
            '<button class="ia-btn ghost" data-ia="reset">↺ Reset</button></div><ol class="ia-laps"></ol>'
        )
        return InstantAnswer(kind="clock", icon="⏱️", title="Stopwatch", body=body)
    secs = None
    if ql in ("pomodoro", "pomodoro timer"):
        secs, title = 25 * 60, "Pomodoro · 25 min focus"
    else:
        m = re.fullmatch(r"(?:set\s+(?:a\s+)?)?(?:timer|countdown|nedtælling|æggeur)(?:\s+(?:for|på|of)?\s*(.+))?", ql) or re.fullmatch(
            r"(?:set\s+(?:a\s+)?)?(.+?)[\s-]*(?:timer|countdown|nedtælling)", ql
        )
        if not m:
            return None
        spec = m[1] or "5 min"
        spec = re.sub(r"(\d)\s*-\s*(?=[a-z])", r"\1 ", spec)
        secs = parse_duration(spec)
        title = "Timer"
    if not secs or secs > 7 * 86400:
        return None
    presets = "".join(
        f'<button class="ia-chip" data-ia="preset" data-secs="{s}">{lbl}</button>'
        for lbl, s in (("1m", 60), ("3m", 180), ("5m", 300), ("10m", 600), ("15m", 900), ("25m", 1500), ("1h", 3600))
    )
    body = (
        f'<div class="ia-clock" data-mode="timer" data-secs="{secs}">'
        f'<svg class="ia-ring" viewBox="0 0 120 120"><circle cx="60" cy="60" r="54"/><circle class="p" cx="60" cy="60" r="54"/></svg>'
        f'<span class="ia-clock-face">{hms(secs)}</span></div>'
        f'<div class="ia-actions"><button class="ia-btn" data-ia="start">▶ Start</button>'
        f'<button class="ia-btn ghost" data-ia="reset">↺ Reset</button></div>'
        f'<div class="ia-presets">{presets}</div>'
    )
    return InstantAnswer(kind="clock", icon="⏲️", title=title, body=body)


# ==========================================================================
# dates
# ==========================================================================

MONTHS = {
    m.lower(): i
    for i in range(1, 13)
    for m in (calendar.month_name[i], calendar.month_abbr[i])
} | {
    "januar": 1, "februar": 2, "marts": 3, "maj": 5, "juni": 6, "juli": 7, "oktober": 10, "okt": 10,
    "sept": 9,
}


def easter(year: int) -> dt.date:
    a, b, c = year % 19, year // 100, year % 100
    d, ee = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * ee + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return dt.date(year, month, day + 1)


def dk_holidays(year: int) -> list[tuple[str, dt.date]]:
    es = easter(year)
    days = [
        ("Nytårsdag · New Year's Day", dt.date(year, 1, 1)),
        ("Skærtorsdag · Maundy Thursday", es - dt.timedelta(days=3)),
        ("Langfredag · Good Friday", es - dt.timedelta(days=2)),
        ("Påskedag · Easter Sunday", es),
        ("2. påskedag · Easter Monday", es + dt.timedelta(days=1)),
    ]
    if year < 2024:
        days.append(("Store bededag · Great Prayer Day", es + dt.timedelta(days=26)))
    days += [
        ("Kristi himmelfartsdag · Ascension", es + dt.timedelta(days=39)),
        ("Pinsedag · Whit Sunday", es + dt.timedelta(days=49)),
        ("2. pinsedag · Whit Monday", es + dt.timedelta(days=50)),
        ("Grundlovsdag · Constitution Day¹", dt.date(year, 6, 5)),
        ("Juleaften · Christmas Eve¹", dt.date(year, 12, 24)),
        ("Juledag · Christmas Day", dt.date(year, 12, 25)),
        ("2. juledag · Boxing Day", dt.date(year, 12, 26)),
        ("Nytårsaften · New Year's Eve¹", dt.date(year, 12, 31)),
    ]
    return sorted(days, key=lambda x: x[1])


def named_date(name: str, today: dt.date) -> tuple[str, dt.date] | None:
    """'christmas' → next Christmas (this year if still ahead)."""
    n = re.sub(r"[’'`]", "", name.strip().lower()).rstrip("?! ")
    n = re.sub(r"^(?:the\s+)?(?:next\s+)?", "", n)
    table: dict[str, tuple[str, t.Callable[[int], dt.date]]] = {}

    def add(keys, label, fn):
        for k in keys:
            table[k] = (label, fn)

    add(["christmas", "xmas", "christmas day"], "Christmas Day", lambda y: dt.date(y, 12, 25))
    add(["jul", "juleaften", "christmas eve"], "Juleaften", lambda y: dt.date(y, 12, 24))
    add(["new year", "new years", "new years day", "nytår", "nytårsdag"], "New Year", lambda y: dt.date(y, 1, 1))
    add(["new years eve", "nytårsaften", "nye"], "New Year's Eve", lambda y: dt.date(y, 12, 31))
    add(["halloween"], "Halloween", lambda y: dt.date(y, 10, 31))
    add(["valentines", "valentines day", "valentinsdag"], "Valentine's Day", lambda y: dt.date(y, 2, 14))
    add(["easter", "påske", "påskedag"], "Easter Sunday", easter)
    add(["midsummer", "sankthans", "sankt hans", "skt hans"], "Sankt Hans aften", lambda y: dt.date(y, 6, 23))
    add(["grundlovsdag", "constitution day"], "Grundlovsdag", lambda y: dt.date(y, 6, 5))
    add(["fastelavn"], "Fastelavn", lambda y: easter(y) - dt.timedelta(days=49))
    add(["summer", "sommer"], "Summer solstice", lambda y: dt.date(y, 6, 21))
    add(["winter", "vinter"], "Winter solstice", lambda y: dt.date(y, 12, 21))
    add(["weekend", "friday", "fredag"], "Friday", lambda y: None)  # type: ignore
    if n not in table:
        return None
    label, fn = table[n]
    if label == "Friday":
        return "the weekend (Saturday)", today + dt.timedelta(days=(5 - today.weekday()) % 7 or 7)
    d = fn(today.year)
    if d < today:
        d = fn(today.year + 1)
    return label, d


def parse_date(s: str, today: dt.date, future: bool = False) -> dt.date | None:
    s = s.strip().lower().rstrip("?.! ")
    s = re.sub(r"^(?:the\s+|on\s+|d\.\s*|den\s+)", "", s)
    if s in ("today", "now", "i dag", "idag"):
        return today
    if s in ("tomorrow", "i morgen", "imorgen"):
        return today + dt.timedelta(days=1)
    if s in ("yesterday", "i går", "igår"):
        return today - dt.timedelta(days=1)
    nd = named_date(s, today)
    if nd:
        return nd[1]
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    try:
        if m:
            return dt.date(int(m[1]), int(m[2]), int(m[3]))
        m = re.fullmatch(r"(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})", s)  # European day-first
        if m:
            y = int(m[3]) + (2000 if len(m[3]) == 2 else 0)
            return dt.date(y, int(m[2]), int(m[1]))
        m = re.fullmatch(r"(\d{1,2})[./](\d{1,2})\.?", s)
        year_given = False
        if m:
            d = dt.date(today.year, int(m[2]), int(m[1]))
        else:
            s2 = re.sub(r"(\d)(?:st|nd|rd|th)\b", r"\1", s).replace(",", " ")
            m = re.fullmatch(r"(\d{1,2})\.?\s+([a-zæøå]+)\.?(?:\s+(\d{4}))?", s2) or None
            if m:
                day, mon, yr = int(m[1]), m[2], m[3]
            else:
                m = re.fullmatch(r"([a-zæøå]+)\.?\s+(\d{1,2})(?:\s+(\d{4}))?", s2)
                if not m:
                    return None
                mon, day, yr = m[1], int(m[2]), m[3]
            if mon not in MONTHS:
                return None
            year_given = bool(yr)
            d = dt.date(int(yr) if yr else today.year, MONTHS[mon], day)
        if future and not year_given and d < today:
            d = d.replace(year=d.year + 1)
        return d
    except ValueError:
        return None


def date_long(d: dt.date) -> str:
    return f"{calendar.day_name[d.weekday()]}, {d.day} {calendar.month_name[d.month]} {d.year}"


def rel_days(n: int) -> str:
    if n == 0:
        return "today"
    if n == 1:
        return "tomorrow"
    if n == -1:
        return "yesterday"
    return f"in {n:,} days" if n > 0 else f"{-n:,} days ago"


def today_local() -> dt.date:
    return dt.datetime.now().date()


@handler("Dates & calendar", ["days until christmas", "dage til juleaften", "days between 1/1/2026 and 24/12/2026"])
def h_until(q, ql):
    m = re.fullmatch(
        r"(?:how\s+many\s+)?(?:days?|sleeps|weeks)\s+(?:left\s+)?(?:until|till|til|to|before)\s+(.+)|"
        r"how\s+long\s+(?:until|till|to)\s+(.+)|countdown\s+(?:to|until)\s+(.+)|"
        r"(?:hvor\s+mange\s+)?dage\s+(?:er\s+der\s+)?(?:til|indtil)\s+(.+)|when\s+is\s+(.+)",
        ql,
    )
    today = today_local()
    if m:
        target = next(g for g in m.groups() if g)
        nd = named_date(target, today)
        label, d = nd if nd else (None, parse_date(target, today, future=True))
        if not d:
            return None
        label = label or date_long(d)
        n = (d - today).days
        weeks, rest = divmod(abs(n), 7)
        body = (
            f'<div class="ia-countdown" data-target="{d.isoformat()}T00:00:00"></div>'
            + rows_html([("Date", date_long(d)), ("Weeks", f"{weeks} weeks, {rest} days"), ("ISO week", d.isocalendar().week)], copy=False)
        )
        return InstantAnswer(kind="date", icon="📅", title=f"Until {label}", value=f"{n:,} days" if n != 1 else "1 day", sub=rel_days(n), body=body)
    m = re.fullmatch(
        r"(?:days?|dage)\s+(?:between|from|mellem|fra)\s+(.+?)\s+(?:and|to|until|og|til)\s+(.+)", ql
    )
    if m:
        a, b = parse_date(m[1], today), parse_date(m[2], today)
        if not a or not b:
            return None
        n = (b - a).days
        wd = sum(1 for i in range(min(abs(n), 36600)) if (min(a, b) + dt.timedelta(days=i)).weekday() < 5)
        body = rows_html([("From", date_long(a)), ("To", date_long(b)), ("Weeks", f"{abs(n) // 7} weeks, {abs(n) % 7} days"), ("Weekdays (Mon–Fri)", f"{wd:,}")], copy=False)
        return InstantAnswer(kind="date", icon="📅", title="Days between", value=f"{n:,} days", body=body)
    return None


@handler("Dates & calendar", ["today + 90 days", "100 days ago", "what day is 24/12/2026"])
def h_datemath(q, ql):
    today = today_local()
    m1 = re.fullmatch(
        r"(?:(.+?)\s*([+-])\s*|in\s+)(\d{1,5})\s*(days?|d|weeks?|w|months?|years?|y|dage|uger|måneder|år)(?:\s+from\s+(?:now|today))?", ql
    )
    m2 = re.fullmatch(r"(\d{1,5})\s*(days?|weeks?|months?|years?|dage|uger|måneder|år)\s+(ago|from\s+(?:now|today)|siden)", ql)
    m = m1 or m2
    if m:
        if m1:
            base_s, sign, n, unit = m1[1], m1[2] or "+", int(m1[3]), m1[4]
            base = parse_date(base_s, today) if base_s else today
        else:
            n, unit = int(m2[1]), m2[2]
            base, sign = today, "-" if m2[3] in ("ago", "siden") else "+"
        if not base:
            return None
        k = n if sign == "+" else -n
        u = unit[0]
        try:
            if u in "dD":
                d = base + dt.timedelta(days=k)
            elif u in "wu":
                d = base + dt.timedelta(weeks=k)
            elif u == "m":
                mm = base.month - 1 + k
                y, mo = base.year + mm // 12, mm % 12 + 1
                d = dt.date(y, mo, min(base.day, calendar.monthrange(y, mo)[1]))
            else:
                y = base.year + k
                d = base.replace(year=y, day=min(base.day, calendar.monthrange(y, base.month)[1]))
        except (ValueError, OverflowError):
            return None
        body = rows_html([("ISO", d.isoformat()), ("Week", d.isocalendar().week), ("From today", rel_days((d - today).days))])
        return InstantAnswer(kind="date", icon="📅", title=f"{date_long(base) if base != today else 'Today'} {sign} {n} {unit}", value=date_long(d), body=body)
    m = re.fullmatch(r"(?:what\s+(?:day|weekday)\s+(?:of\s+the\s+week\s+)?(?:is|was|will\s+be|falls\s+on)|weekday|ugedag|hvilken\s+dag\s+er)\s+(.+)", ql)
    if m:
        d = parse_date(m[1], today)
        if not d:
            return None
        return InstantAnswer(kind="date", icon="📅", title=m[1].strip("? "), value=calendar.day_name[d.weekday()], sub=f"{date_long(d)} · week {d.isocalendar().week} · {rel_days((d - today).days)}")
    return None


@handler("Dates & calendar", ["week", "uge 42", "today", "is 2028 a leap year"])
def h_week(q, ql):
    today = today_local()
    if re.fullmatch(
        r"(?:what(?:'s|\s+is)?\s+(?:the\s+)?(?:current\s+)?)?(?:week(?:\s+(?:number|no\.?|nr\.?))?|ugenummer|ugenr|uge(?:nummer)?)"
        r"(?:\s+(?:is\s+it|today|now|this\s+week|i\s+dag|er\s+det))*\??|hvilken\s+uge\s+er\s+det\??|what\s+week\s+is\s+it\??|current\s+week",
        ql,
    ):
        iso = today.isocalendar()
        mon = today - dt.timedelta(days=today.weekday())
        return InstantAnswer(
            kind="date", icon="🗓️", title=f"Week number · {iso.year}", value=f"Week {iso.week}",
            sub=f"{mon:%a %d %b} – {mon + dt.timedelta(days=6):%a %d %b %Y}", body=calendar_html(today),
        )
    m = re.fullmatch(r"(?:week|uge)\s+(\d{1,2})(?:\s+(\d{4}))?", ql)
    if m:
        y = int(m[2] or today.year)
        try:
            mon = dt.date.fromisocalendar(y, int(m[1]), 1)
        except ValueError:
            return None
        return InstantAnswer(kind="date", icon="🗓️", title=f"Week {int(m[1])}, {y}", value=f"{mon:%d %b} – {mon + dt.timedelta(days=6):%d %b %Y}", sub=f"Monday {mon.isoformat()} · {rel_days((mon - today).days)}", body=calendar_html(mon))
    m = re.fullmatch(r"(?:what\s+)?week\s+(?:is|was|of)\s+(.+)", ql)
    if m:
        d = parse_date(m[1], today)
        if d:
            return InstantAnswer(kind="date", icon="🗓️", title=date_long(d), value=f"Week {d.isocalendar().week}", sub=f"ISO {d.isocalendar().year}-W{d.isocalendar().week:02d}")
    if re.fullmatch(r"(?:what(?:'s|\s+is)\s+)?(?:the\s+)?(?:today(?:'s)?(?:\s+date)?|date(?:\s+today)?|dags\s+dato|dato|i\s+dag)\??", ql):
        doy = today.timetuple().tm_yday
        ylen = 366 if calendar.isleap(today.year) else 365
        body = (
            f'<div class="ia-progress"><i style="width:{doy / ylen * 100:.1f}%"></i></div>'
            + rows_html([("ISO", today.isoformat()), ("Week", today.isocalendar().week), ("Day of year", f"{doy} / {ylen}"), ("Days left", ylen - doy)])
            + calendar_html(today)
        )
        return InstantAnswer(kind="date", icon="📅", title="Today", value=date_long(today), body=body)
    m = re.fullmatch(r"(?:is\s+(\d{4})\s+a\s+leap\s*year|leap\s*years?(?:\s+(\d{4}))?|er\s+(\d{4})\s+(?:et\s+)?skudår|skudår(?:\s+(\d{4}))?)\??", ql)
    if m:
        y = int(next((g for g in m.groups() if g), today.year))
        leap = calendar.isleap(y)
        nxt = next(x for x in range(y + (0 if not leap else 1), y + 9) if calendar.isleap(x))
        return InstantAnswer(kind="date", icon="📅", title=f"Is {y} a leap year?", value="Yes" if leap else "No", sub=f"{366 if leap else 365} days · next leap year: {nxt}")
    return None


def calendar_html(focus: dt.date) -> str:
    today = today_local()
    cal = calendar.Calendar(firstweekday=0)
    out = [f'<table class="ia-cal"><caption>{calendar.month_name[focus.month]} {focus.year}</caption><tr><th>wk</th>']
    out += [f"<th>{d}</th>" for d in ("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")]
    out.append("</tr>")
    for week in cal.monthdatescalendar(focus.year, focus.month):
        out.append(f'<tr><td class="wk">{week[0].isocalendar().week}</td>')
        for d in week:
            cls = []
            if d.month != focus.month:
                cls.append("o")
            if d == today:
                cls.append("t")
            if d.isocalendar().week == focus.isocalendar().week and d.year == focus.year or d.isocalendar()[:2] == focus.isocalendar()[:2]:
                cls.append("w")
            out.append(f'<td class="{" ".join(cls)}">{d.day}</td>')
        out.append("</tr>")
    out.append("</table>")
    return "".join(out)


@handler("Dates & calendar", ["helligdage 2027", "easter 2027"])
def h_holidays(q, ql):
    today = today_local()
    m = re.fullmatch(
        r"(?:(?:danish|danske|dk)\s+)?(?:public\s+|bank\s+)?(?:holidays|helligdage|fridage)(?:\s+(?:in\s+)?(?:denmark|dk|danmark|i\s+danmark))?(?:\s+(\d{4}))?", ql
    )
    if m:
        y = int(m[1] or today.year)
        if not 1900 <= y <= 2200:
            return None
        rows = []
        nxt = None
        for name, d in dk_holidays(y):
            past = d < today
            if not past and nxt is None:
                nxt = d
            rows.append(
                f'<tr class="{"past" if past else ""}{" next" if d == nxt else ""}"><td>{e(name)}</td>'
                f"<td>{calendar.day_abbr[d.weekday()]} {d.day} {calendar.month_abbr[d.month]}</td>"
                f'<td class="r">{e(rel_days((d - today).days)) if not past else ""}</td></tr>'
            )
        body = f'<table class="ia-table">{"".join(rows)}</table><div class="ia-note">¹ Not an official public holiday, but most workplaces close.</div>'
        return InstantAnswer(kind="date", icon="🇩🇰", title=f"Danish public holidays {y}", body=body)
    m = re.fullmatch(r"(?:when\s+is\s+)?(?:easter|påske)(?:\s+(\d{4}))?\??", ql)
    if m:
        y = int(m[1] or today.year)
        es = easter(y)
        if not m[1] and es < today:
            es = easter(y + 1)
        body = rows_html([("Palm Sunday", date_long(es - dt.timedelta(days=7))), ("Good Friday", date_long(es - dt.timedelta(days=2))), ("Easter Monday", date_long(es + dt.timedelta(days=1)))], copy=False)
        return InstantAnswer(kind="date", icon="🐣", title=f"Easter {es.year}", value=date_long(es), sub=rel_days((es - today).days), body=body)
    return None


@handler("Dates & calendar", ["age 1995-04-12"])
def h_age(q, ql):
    m = re.fullmatch(r"(?:age|alder|how\s+old\s+am\s+i|how\s+old\s+is\s+someone)\s+(?:if\s+)?(?:born\s+)?(?:on\s+|in\s+|født\s+)?(.+)|born\s+(?:on\s+|in\s+)?(.+)", ql)
    if not m:
        return None
    today = today_local()
    b = parse_date(m[1] or m[2], today)
    if not b or b > today:
        return None
    years = today.year - b.year - ((today.month, today.day) < (b.month, b.day))
    try:
        nb = b.replace(year=today.year)
    except ValueError:
        nb = dt.date(today.year, 3, 1)
    if nb < today:
        nb = nb.replace(year=today.year + 1) if not (b.month == 2 and b.day == 29) else dt.date(today.year + 1, 3, 1)
    days = (today - b).days
    body = rows_html([("Born", date_long(b)), ("Days alive", f"{days:,}"), ("Weeks", f"{days // 7:,}"), ("Next birthday", f"{date_long(nb)} ({rel_days((nb - today).days)})")], copy=False)
    return InstantAnswer(kind="date", icon="🎂", title="Age", value=f"{years} years", body=body)


@handler("Timers & time", ["unix 1767225600", "timestamp"])
def h_unix(q, ql):
    m = re.fullmatch(r"(?:unix|epoch|timestamp|unix\s*time(?:stamp)?|posix\s*time)(?:\s+(?:now|of|for)?\s*(.+))?|(1\d{9}(?:\d{3})?)", ql)
    if not m:
        return None
    arg = (m[1] or m[2] or "").strip()
    if not arg:
        now = int(time.time())
        body = (
            f'<div class="ia-live-unix" data-live="unix">{now}</div>'
            + rows_html([("Milliseconds", "…"), ("ISO 8601 UTC", dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"))])
        )
        return InstantAnswer(kind="unix", icon="⏱️", title="Current Unix time", body=body)
    if re.fullmatch(r"\d{9,13}", arg):
        ts = int(arg)
        ms = len(arg) == 13
        if ms:
            ts /= 1000
        try:
            u = dt.datetime.fromtimestamp(ts, dt.UTC)
        except (OverflowError, ValueError, OSError):
            return None
        local = dt.datetime.fromtimestamp(ts).astimezone()
        body = rows_html([("UTC", u.isoformat().replace("+00:00", "Z")), ("Local (" + local.strftime("%Z") + ")", local.strftime("%Y-%m-%d %H:%M:%S")), ("Relative", rel_days((u.date() - dt.datetime.now(dt.UTC).date()).days)), ("Unit", "milliseconds" if ms else "seconds")])
        return InstantAnswer(kind="unix", icon="⏱️", title=f"Unix {arg}", value=u.strftime("%a %d %b %Y, %H:%M:%S UTC"), body=body)
    d = parse_date(arg, today_local())
    if d:
        ts = int(calendar.timegm(d.timetuple()))
        return InstantAnswer(kind="unix", icon="⏱️", title=f"Unix time of {date_long(d)} 00:00 UTC", value=str(ts), copy=str(ts))
    return None


def moon_phase(when: dt.datetime) -> float:
    """Phase 0..1 (0 = new moon), from a mean synodic month anchored on the
    2000-01-06 18:14 UTC new moon; good to a few hours."""
    ref = dt.datetime(2000, 1, 6, 18, 14, tzinfo=dt.UTC)
    syn = 29.530588853
    return (((when - ref).total_seconds() / 86400) % syn) / syn


@handler("Timers & time", ["moon phase"])
def h_moon(q, ql):
    if not re.fullmatch(r"(?:what(?:'s|\s+is)\s+(?:the\s+)?)?(?:moon(?:\s*phase)?|lunar\s+phase|månefase|månen|next\s+full\s+moon|full\s+moon|fuldmåne|new\s+moon|nymåne)(?:\s+(?:today|tonight|now|i\s+dag|i\s+aften))?\??", ql):
        return None
    now = dt.datetime.now(dt.UTC)
    p = moon_phase(now)
    syn = 29.530588853
    names = ["New moon", "Waxing crescent", "First quarter", "Waxing gibbous", "Full moon", "Waning gibbous", "Last quarter", "Waning crescent"]
    emoji = "🌑🌒🌓🌔🌕🌖🌗🌘"
    idx = int((p * 8) + 0.5) % 8
    illum = (1 - math.cos(2 * math.pi * p)) / 2
    to_full = ((0.5 - p) % 1) * syn
    to_new = ((1 - p) % 1) * syn
    # SVG moon: lit part is an ellipse-bounded region
    r = 50
    k = math.cos(2 * math.pi * p)  # 1 new .. -1 full
    rx = abs(k) * r
    waxing = p < 0.5
    sweep_outer = 1 if waxing else 0
    sweep_inner = (0 if k > 0 else 1) if waxing else (1 if k > 0 else 0)
    path = f"M60 10 A{r} {r} 0 0 {sweep_outer} 60 110 A{rx:.2f} {r} 0 0 {sweep_inner} 60 10Z"
    svg = f'<svg class="ia-moon" viewBox="0 0 120 120"><circle cx="60" cy="60" r="50" class="dark"/><path d="{path}" class="lit"/></svg>'
    body = f'<div class="ia-moon-wrap">{svg}</div>' + rows_html(
        [("Illumination", f"{illum * 100:.0f}%"), ("Moon age", f"{p * syn:.1f} days"), ("Next full moon", f"{(now + dt.timedelta(days=to_full)):%a %d %b} ({to_full:.1f} days)"), ("Next new moon", f"{(now + dt.timedelta(days=to_new)):%a %d %b} ({to_new:.1f} days)")],
        copy=False,
    )
    return InstantAnswer(kind="moon", icon=emoji[idx], title="Moon phase", value=names[idx], body=body)


# ==========================================================================
# maths
# ==========================================================================


@handler("Maths & money", ["15% of 80", "20 is what percent of 80", "80 + 25%", "change from 80 to 100"])
def h_percent(q, ql):
    s = ql.replace("procent", "percent").replace("pct", "percent")
    m = re.fullmatch(rf"(?:what\s+is\s+)?({NUM})\s*(?:%|percent)\s+(?:of|af)\s+({NUM})\??", s)
    if m:
        p, x = num(m[1]), num(m[2])
        return InstantAnswer(kind="math", icon="％", title=f"{fmt(p)}% of {fmt(x)}", value=fmt(p / 100 * x), copy=fmt(p / 100 * x))
    m = re.fullmatch(rf"({NUM})\s+is\s+what\s+(?:percent(?:age)?|%)\s+of\s+({NUM})\??", s) or re.fullmatch(
        rf"what\s+(?:percent(?:age)?|%)\s+(?:is|of)\s+({NUM})\s+(?:of|is|out\s+of)\s+({NUM})\??", s
    ) or re.fullmatch(rf"({NUM})\s+(?:out\s+of|of|af|ud\s+af)\s+({NUM})\s+(?:in|as|i)?\s*(?:percent|%)", s)
    if m:
        a, b = num(m[1]), num(m[2])
        if b == 0:
            return None
        v = a / b * 100
        return InstantAnswer(kind="math", icon="％", title=f"{fmt(a)} of {fmt(b)}", value=f"{fmt(v, 2)}%", copy=fmt(v, 4))
    m = re.fullmatch(rf"({NUM})\s*([+-])\s*({NUM})\s*%", s)
    if m:
        a, p = num(m[1]), num(m[3])
        v = a * (1 + p / 100) if m[2] == "+" else a * (1 - p / 100)
        return InstantAnswer(kind="math", icon="％", title=f"{fmt(a)} {m[2]} {fmt(p)}%", value=fmt(v, 2), sub=f"{'+' if m[2] == '+' else '−'}{fmt(abs(v - a), 2)}", copy=fmt(v, 4))
    m = re.fullmatch(rf"(?:percent(?:age)?\s+)?(?:change|increase|decrease|difference|ændring)\s+(?:from\s+|fra\s+)?({NUM})\s+(?:to|til|->|→)\s+({NUM})", s)
    if m:
        a, b = num(m[1]), num(m[2])
        if a == 0:
            return None
        v = (b - a) / abs(a) * 100
        return InstantAnswer(kind="math", icon="📈" if v >= 0 else "📉", title=f"Change {fmt(a)} → {fmt(b)}", value=f"{'+' if v >= 0 else ''}{fmt(v, 2)}%", sub=f"difference {fmt(b - a, 2)}")
    return None


@handler("Maths & money", ["tip 18% on 640", "split 1250 between 4"])
def h_tip(q, ql):
    m = re.fullmatch(rf"(?:tip|drikkepenge)\s+(?:(\d{{1,2}})\s*%\s+(?:on|of|for|af|på)\s+)?({NUM})(?:\s+(?:split\s+)?(?:between|by|for|among|mellem|på)\s+(\d{{1,2}})(?:\s+(?:people|persons|ways|personer))?)?", ql)
    if m:
        amount, people = num(m[2]), int(m[3] or 1)
        pcts = [int(m[1])] if m[1] else [10, 15, 18, 20, 25]
        rows = "".join(
            f"<tr><td>{p}%</td><td class='r'>{fmt(amount * p / 100, 2)}</td><td class='r'><b>{fmt(amount * (1 + p / 100), 2)}</b></td>"
            + (f"<td class='r'>{fmt(amount * (1 + p / 100) / people, 2)}</td>" if people > 1 else "")
            + "</tr>"
            for p in pcts
        )
        head = "<tr><th>Tip</th><th class='r'>Tip</th><th class='r'>Total</th>" + ("<th class='r'>Per person</th>" if people > 1 else "") + "</tr>"
        return InstantAnswer(kind="math", icon="💁", title=f"Tip on {fmt(amount, 2)}" + (f" · {people} people" if people > 1 else ""), body=f'<table class="ia-table">{head}{rows}</table>')
    m = re.fullmatch(rf"(?:split|del)\s+({NUM})\s+(?:between|by|among|in|for|into|mellem|på|i)\s+(\d{{1,3}})(?:\s+(?:people|persons|ways|parts|personer|dele))?", ql)
    if m:
        amount, n = num(m[1]), int(m[2])
        if n < 1:
            return None
        return InstantAnswer(kind="math", icon="➗", title=f"{fmt(amount, 2)} split {n} ways", value=fmt(amount / n, 2), sub="each", copy=fmt(amount / n, 2))
    return None


BASES = {"hex": 16, "hexadecimal": 16, "binary": 2, "bin": 2, "octal": 8, "oct": 8, "decimal": 10, "dec": 10}


def parse_int(s: str) -> int | None:
    s = s.strip().lower().replace("_", "")
    try:
        if s.startswith(("0x", "-0x")):
            return int(s, 16)
        if s.startswith(("0b", "-0b")):
            return int(s, 2)
        if s.startswith(("0o", "-0o")):
            return int(s, 8)
        if re.fullmatch(r"-?\d+", s):
            return int(s)
    except ValueError:
        pass
    return None


def to_base(n: int, b: int) -> str:
    if n == 0:
        return "0"
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    neg, n = n < 0, abs(n)
    out = ""
    while n:
        n, r = divmod(n, b)
        out = digits[r] + out
    return ("-" if neg else "") + out


@handler("Developer", ["0xff", "255 in binary", "1011 from binary", "2026 in roman", "roman MMXXVI"])
def h_bases(q, ql):
    m = re.fullmatch(r"(-?0x[0-9a-f_]+|-?0b[01_]+|-?0o[0-7_]+)", ql) or re.fullmatch(
        r"(-?(?:0x|0b|0o)?[0-9a-f_]+)\s+(?:in|to|as|into|til|i)\s+(hex(?:adecimal)?|bin(?:ary)?|oct(?:al)?|dec(?:imal)?|base\s*\d{1,2})", ql
    )
    src_base = 10
    if not m:
        m2 = re.fullmatch(r"([0-9a-z_]+)\s+from\s+(hex(?:adecimal)?|bin(?:ary)?|oct(?:al)?|base\s*\d{1,2})(?:\s+to\s+decimal)?", ql)
        if not m2:
            return None
        src_base = int(re.sub(r"\D", "", m2[2])) if m2[2].startswith("base") else BASES[m2[2]]
        try:
            n = int(m2[1].replace("_", ""), src_base)
        except ValueError:
            return None
        target = None
    else:
        n = parse_int(m[1])
        if n is None:
            return None
        target = m[2] if m.lastindex and m.lastindex >= 2 else None
    if abs(n) > 2**256:
        return None
    rows = [("Decimal", str(n)), ("Hex", ("-" if n < 0 else "") + "0x" + to_base(abs(n), 16)), ("Binary", ("-" if n < 0 else "") + "0b" + to_base(abs(n), 2)), ("Octal", ("-" if n < 0 else "") + "0o" + to_base(abs(n), 8))]
    if 0 <= n < 2**32 and n > 255:
        rows.append(("Bytes (BE)", " ".join(f"{b:02x}" for b in n.to_bytes((n.bit_length() + 7) // 8, "big"))))
    if 32 <= n < 0x110000:
        try:
            rows.append(("Character", f"{chr(n)}  ({unicodedata.name(chr(n))})"))
        except ValueError:
            pass
    value = ""
    if target:
        b = int(re.sub(r"\D", "", target)) if target.startswith("base") else BASES[target]
        if not 2 <= b <= 36:
            return None
        value = to_base(n, b)
        if b not in (2, 8, 10, 16):
            rows.insert(0, (f"Base {b}", value))
    return InstantAnswer(kind="bases", icon="🔢", title=(m[1] if m else f"{m2[1]} (base {src_base})") if not target else f"{m[1]} → {target}", value=value, body=rows_html(rows), copy=value)


ROMAN = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]


def to_roman(n: int) -> str:
    out = ""
    for v, s in ROMAN:
        while n >= v:
            out, n = out + s, n - v
    return out


def from_roman(s: str) -> int | None:
    s = s.upper()
    if not re.fullmatch(r"M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})", s) or not s:
        return None
    vals = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    total = 0
    for i, c in enumerate(s):
        v = vals[c]
        total += -v if i + 1 < len(s) and vals[s[i + 1]] > v else v
    return total


@handler("Developer", [])
def h_roman(q, ql):
    m = re.fullmatch(r"(\d{1,4})\s+(?:in|to|as|til|i)\s+roman(?:\s+numerals?)?|roman(?:\s+numerals?)?\s+(?:for\s+|of\s+)?(\d{1,4}|[ivxlcdm]+)|([ivxlcdm]+)\s+(?:in|to|as)\s+(?:decimal|numbers?|arabic)", ql)
    if not m:
        return None
    arg = m[1] or m[2] or m[3]
    if arg.isdigit():
        n = int(arg)
        if not 1 <= n <= 3999:
            return None
        r = to_roman(n)
        return InstantAnswer(kind="roman", icon="🏛️", title=f"{n} in Roman numerals", value=r, copy=r)
    n = from_roman(arg)
    if n is None:
        return None
    return InstantAnswer(kind="roman", icon="🏛️", title=f"{arg.upper()} in decimal", value=str(n), copy=str(n))


# ==========================================================================
# text & encoding
# ==========================================================================


def text_card(title: str, out: str, icon: str = "🔤", note: str = "") -> InstantAnswer:
    body = f'<pre class="ia-out">{e(out)}</pre>' + (f'<div class="ia-note">{e(note)}</div>' if note else "")
    return InstantAnswer(kind="text", icon=icon, title=title, body=body, copy=out)


@handler("Text & encoding", ["base64 hello world", "base64 decode aGVsbG8=", "url encode a b&c", "rot13 hello"], local=True)
def h_encode(q, ql):
    m = re.fullmatch(r"(?:base64|b64)\s+(encode|decode|enc|dec|-d|-e)?\s*(.+)|(?:(encode|decode)\s+(?:to\s+|from\s+)?)(?:base64|b64)\s+(.+)", q, re.I | re.S)
    if m:
        op = (m[1] or m[3] or "encode").lower()
        s = m[2] if m[2] is not None else m[4]
        if op.startswith(("dec", "-d")):
            try:
                raw = base64.b64decode(s.strip() + "=" * (-len(s.strip()) % 4), altchars=b"-_" if re.search(r"[-_]", s) else None, validate=False)
                out = raw.decode("utf-8")
            except (binascii.Error, UnicodeDecodeError, ValueError):
                return text_card("Base64 decode", "(not valid Base64 / not UTF-8 text)", "🔓")
            return text_card("Base64 decoded", out, "🔓")
        return text_card("Base64 encoded", base64.b64encode(s.encode()).decode(), "🔒")
    m = re.fullmatch(r"url\s*(encode|decode|escape|unescape)\s+(.+)|(?:percent|uri)\s*(encode|decode)\s+(.+)", q, re.I | re.S)
    if m:
        op, s = (m[1] or m[3]).lower(), (m[2] or m[4])
        out = urllib.parse.unquote_plus(s) if op in ("decode", "unescape") else urllib.parse.quote(s, safe="")
        return text_card(f"URL {op}d", out, "🔗")
    m = re.fullmatch(r"html\s*(encode|decode|escape|unescape)\s+(.+)", q, re.I | re.S)
    if m:
        out = html.unescape(m[2]) if m[1].lower() in ("decode", "unescape") else html.escape(m[2])
        return text_card(f"HTML {m[1].lower()}d", out, "🏷️")
    m = re.fullmatch(r"rot\s*13\s+(.+)", q, re.I | re.S)
    if m:
        import codecs  # pylint: disable=import-outside-toplevel

        return text_card("ROT13", codecs.encode(m[1], "rot13"), "🔄")
    m = re.fullmatch(r"(?:reverse|flip)\s+(?:text|string|tekst)\s+(.+)", q, re.I | re.S)
    if m:
        return text_card("Reversed", m[1][::-1], "🔄")
    m = re.fullmatch(r"(upper\s*case|lower\s*case|title\s*case|snake\s*case|camel\s*case|kebab\s*case|pascal\s*case|constant\s*case|slug(?:ify)?)\s*:?\s+(.+)", q, re.I | re.S)
    if m:
        kind, s = re.sub(r"\s", "", m[1].lower()), m[2]
        words = re.findall(r"[A-Za-zÀ-ÿ0-9]+", re.sub(r"([a-z])([A-Z])", r"\1 \2", s))
        out = {
            "uppercase": s.upper(), "lowercase": s.lower(), "titlecase": s.title(),
            "snakecase": "_".join(w.lower() for w in words), "kebabcase": "-".join(w.lower() for w in words),
            "slug": "-".join(w.lower() for w in words), "slugify": "-".join(w.lower() for w in words),
            "camelcase": (words[0].lower() + "".join(w.capitalize() for w in words[1:])) if words else "",
            "pascalcase": "".join(w.capitalize() for w in words), "constantcase": "_".join(w.upper() for w in words),
        }[kind]
        return text_card(m[1].strip().capitalize(), out, "🔠")
    return None


@handler("Text & encoding", ["count words the quick brown fox"], local=True)
def h_count(q, ql):
    m = re.fullmatch(r"(?:count(?:\s+(?:words|chars|characters|letters))?|(?:word|character|char|letter)\s+count|tæl(?:\s+ord)?)\s*:?\s+(.+)", q, re.I | re.S)
    if not m:
        return None
    s = m[1]
    words = len(re.findall(r"\S+", s))
    body = rows_html(
        [("Characters", len(s)), ("Without spaces", len(re.sub(r"\s", "", s))), ("Words", words), ("Sentences", len(re.findall(r"[.!?]+(?:\s|$)", s)) or (1 if s.strip() else 0)), ("UTF-8 bytes", len(s.encode())), ("Reading time", f"~{max(1, round(words / 230))} min")],
        copy=False,
    )
    return InstantAnswer(kind="text", icon="🔡", title="Text statistics", value=f"{len(s)} chars · {words} words", body=body)


MORSE = dict(zip(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.,?'!/()&:;=+-_\"$@ÆØÅ",
    ".- -... -.-. -.. . ..-. --. .... .. .--- -.- .-.. -- -. --- .--. --.- .-. ... - ..- ...- .-- -..- -.-- --.. "
    "----- .---- ..--- ...-- ....- ..... -.... --... ---.. ----. .-.-.- --..-- ..--.. .----. -.-.-- -..-. -.--. -.--.- "
    ".-... ---... -.-.-. -...- .-.-. -....- ..--.- .-..-. ...-..- .--.-. .-.- ---. .--.-".split(),
))
MORSE_REV = {v: k for k, v in MORSE.items()}


@handler("Text & encoding", ["morse sos help", "morse ... --- ..."], local=True)
def h_morse(q, ql):
    m = re.fullmatch(r"morse(?:\s*code)?\s*:?\s+(.+)", q, re.I | re.S)
    if not m:
        return None
    s = m[1].strip()
    if re.fullmatch(r"[.\-·•_−/|\s]+", s):
        s = s.replace("·", ".").replace("•", ".").replace("_", "-").replace("−", "-")
        words = re.split(r"\s*[/|]\s*|\s{3,}", s)
        out = " ".join("".join(MORSE_REV.get(c, "?") for c in w.split()) for w in words)
        return text_card("Morse → text", out, "📡")
    out = " / ".join(" ".join(MORSE[c] for c in w.upper() if c in MORSE) for w in s.split())
    body = f'<pre class="ia-out ia-morse">{e(out)}</pre><div class="ia-actions"><button class="ia-btn" data-ia="morse-play" data-morse="{e(out)}">🔊 Play</button></div>'
    return InstantAnswer(kind="text", icon="📡", title="Text → Morse", body=body, copy=out)


@handler("Text & encoding", ["unicode ☃", "U+1F600", "emoji cat"])
def h_unicode(q, ql):
    m = re.fullmatch(r"(?:u\+|unicode\s+u\+|codepoint\s+)([0-9a-f]{2,6})", ql)
    chars = None
    if m:
        try:
            chars = chr(int(m[1], 16))
        except (ValueError, OverflowError):
            return None
    else:
        m = re.fullmatch(r"(?:unicode|char|character|charinfo|what\s+(?:character|emoji)\s+is)\s+(.+)", q, re.I)
        if m and len(m[1]) <= 12:
            chars = m[1]
    if chars is None:
        return None
    rows = []
    for c in chars[:12]:
        cp = ord(c)
        try:
            name = unicodedata.name(c)
        except ValueError:
            name = "(unnamed)"
        rows.append(
            f'<tr><td class="ia-glyph"><button data-copy="{e(c)}">{e(c)}</button></td><td>U+{cp:04X}</td><td>{e(name.title())}</td>'
            f"<td><code>{' '.join(f'{b:02X}' for b in c.encode())}</code></td><td><code>&amp;#{cp};</code></td></tr>"
        )
    head = "<tr><th></th><th>Code point</th><th>Name</th><th>UTF-8</th><th>HTML</th></tr>"
    return InstantAnswer(kind="unicode", icon="🔣", title="Unicode", body=f'<div class="ia-scroll"><table class="ia-table">{head}{"".join(rows)}</table></div>')


_EMOJI_INDEX: list[tuple[str, str]] = []


def emoji_index() -> list[tuple[str, str]]:
    if not _EMOJI_INDEX:
        ranges = [(0x1F300, 0x1F5FF), (0x1F600, 0x1F64F), (0x1F680, 0x1F6FF), (0x1F900, 0x1F9FF), (0x1FA70, 0x1FAFF), (0x2600, 0x26FF), (0x2700, 0x27BF), (0x1F1E6, 0x1F1FF)]
        for a, b in ranges:
            for cp in range(a, b + 1):
                try:
                    _EMOJI_INDEX.append((chr(cp), unicodedata.name(chr(cp)).lower()))
                except ValueError:
                    pass
    return _EMOJI_INDEX


@handler("Text & encoding", [])
def h_emoji(q, ql):
    m = re.fullmatch(r"(?:emoji|emojis|emoticon|smiley)\s+(?:for\s+)?([a-z][a-z \-]{1,40})", ql)
    if not m:
        return None
    words = m[1].split()
    hits = [c for c, name in emoji_index() if all(re.search(rf"\b{re.escape(w)}", name) for w in words)][:64]
    if not hits:
        return None
    grid = "".join(f'<button data-copy="{c}" title="{e(unicodedata.name(c).title())}">{c}</button>' for c in hits)
    return InstantAnswer(kind="emoji", icon="😀", title=f"Emoji: {m[1]}", body=f'<div class="ia-emoji">{grid}</div><div class="ia-note">Click to copy.</div>')


# ==========================================================================
# developer
# ==========================================================================


@handler("Developer", ["json {\"a\":[1,2]}"], local=True)
def h_json(q, ql):
    m = re.fullmatch(r"(?:json\s+)?([\[{].*[\]}])", q, re.S)
    if not m or not (ql.startswith("json") or (len(q) > 10 and q.count('"') >= 2)):
        return None
    try:
        obj = json.loads(m[1])
    except ValueError as exc:
        return text_card("JSON · invalid", str(exc), "⚠️")
    return text_card("JSON · formatted", json.dumps(obj, indent=2, ensure_ascii=False), "🧩")


@handler("Developer", [], local=True)
def h_jwt(q, ql):
    m = re.fullmatch(r"(?:jwt\s+)?(eyJ[\w-]+)\.(eyJ[\w-]+)\.([\w-]*)", q.strip())
    if not m:
        return None

    def dec(part):
        return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))

    try:
        header, payload = dec(m[1]), dec(m[2])
    except (ValueError, binascii.Error):
        return None
    rows = []
    for k in ("iat", "nbf", "exp"):
        if isinstance(payload.get(k), (int, float)):
            rows.append((k, dt.datetime.fromtimestamp(payload[k], dt.UTC).strftime("%Y-%m-%d %H:%M:%S UTC")))
    expired = isinstance(payload.get("exp"), (int, float)) and payload["exp"] < time.time()
    body = (
        f'<div class="ia-cols"><div><h5>Header</h5><pre class="ia-out">{e(json.dumps(header, indent=2))}</pre></div>'
        f'<div><h5>Payload</h5><pre class="ia-out">{e(json.dumps(payload, indent=2, ensure_ascii=False))}</pre></div></div>'
        + rows_html(rows, copy=False)
        + '<div class="ia-note">Decoded only — the signature is <b>not</b> verified. This query was not sent to any search engine.</div>'
    )
    return InstantAnswer(kind="jwt", icon="🎫", title="JWT" + (" · expired" if expired else ""), body=body)


@handler("Developer", ["192.168.8.0/22", "2001:db8::/48"], local=True)
def h_subnet(q, ql):
    m = re.fullmatch(r"(?:subnet|cidr|ipcalc|netmask)?\s*([0-9a-f:.]+/[0-9.]{1,15})", ql)
    return h_ip(m[1]) if m else None


@handler("Developer", ["10.0.0.7"])
def h_ipaddr(q, ql):
    m = re.fullmatch(r"(?:ip|ip\s+address|ipv[46])?\s*([0-9a-f:.]+)", ql)
    return h_ip(m[1]) if m else None


def h_ip(s: str) -> InstantAnswer | None:
    if not re.search(r"\d", s) or ("." not in s and ":" not in s) or s.split("/")[0].count(".") not in (0, 3):
        return None
    try:
        if "/" in s:
            iface = ipaddress.ip_interface(s)
            net = iface.network
        else:
            addr = ipaddress.ip_address(s)
            iface, net = None, None
    except ValueError:
        return None
    if net is None:
        kind = "private" if addr.is_private else "loopback" if addr.is_loopback else "multicast" if addr.is_multicast else "reserved" if addr.is_reserved else "global / public"
        rows = [("Version", f"IPv{addr.version}"), ("Scope", kind), ("Integer", int(addr)), ("Reverse DNS", addr.reverse_pointer)]
        if addr.version == 4:
            rows.append(("Binary", ".".join(f"{int(o):08b}" for o in str(addr).split("."))))
            rows.append(("Hex", "0x" + addr.packed.hex()))
            rows.append(("IPv4-mapped IPv6", f"::ffff:{addr}"))
        else:
            rows.append(("Expanded", addr.exploded))
        return InstantAnswer(kind="ip", icon="🌐", title=f"IP address {addr}", body=rows_html(rows))
    rows = [("Network", f"{net.network_address}/{net.prefixlen}")]
    if net.version == 4:
        hosts = net.num_addresses - 2 if net.prefixlen < 31 else net.num_addresses
        first = net.network_address + (1 if net.prefixlen < 31 else 0)
        last = net.broadcast_address - (1 if net.prefixlen < 31 else 0)
        rows += [("Netmask", net.netmask), ("Wildcard", net.hostmask), ("Broadcast", net.broadcast_address), ("Host range", f"{first} – {last}"), ("Usable hosts", f"{hosts:,}")]
    else:
        rows += [("Range", f"{net.network_address} – {net.broadcast_address}"), ("Addresses", f"2^{128 - net.prefixlen}" if net.prefixlen < 64 else f"{net.num_addresses:,}")]
    rows.append(("Scope", "private" if net.is_private else "public"))
    if str(iface.ip) != str(net.network_address):
        rows.insert(0, ("Address", str(iface.ip)))
    bits = net.prefixlen
    total = 32 if net.version == 4 else 128
    bar = f'<div class="ia-bits" title="{bits} network bits, {total - bits} host bits"><i style="width:{bits / total * 100:.1f}%"></i><span>{bits} network</span><span>{total - bits} host</span></div>'
    return InstantAnswer(kind="ip", icon="🧮", title=f"Subnet {s}", body=bar + rows_html(rows))


EXTRA_HTTP = {
    444: ("No Response", "nginx: connection closed without a response."),
    499: ("Client Closed Request", "nginx: the client hung up before the server answered."),
    520: ("Web Server Returned an Unknown Error", "Cloudflare: the origin returned something unexpected."),
    521: ("Web Server Is Down", "Cloudflare: the origin refused the connection."),
    522: ("Connection Timed Out", "Cloudflare: TCP to the origin timed out."),
    523: ("Origin Is Unreachable", "Cloudflare: could not route to the origin."),
    524: ("A Timeout Occurred", "Cloudflare: connected, but the origin did not reply in time."),
    525: ("SSL Handshake Failed", "Cloudflare: TLS handshake with the origin failed."),
    526: ("Invalid SSL Certificate", "Cloudflare: the origin certificate is invalid."),
}


@handler("Developer", ["http 418", "status 503", "chmod 755", "port 5432"])
def h_http(q, ql):
    m = re.fullmatch(r"(?:http\s+(?:status\s+)?(?:code\s+)?|status\s+(?:code\s+)?|error\s+(?:code\s+)?)([1-5]\d\d)|([1-5]\d\d)\s+(?:http|status|error)(?:\s+(?:code|status|error))*", ql)
    if not m:
        return None
    code = int(m[1] or m[2])
    try:
        st = HTTPStatus(code)
        phrase, desc = st.phrase, st.description
    except ValueError:
        if code not in EXTRA_HTTP:
            return None
        phrase, desc = EXTRA_HTTP[code]
    cls = {1: "Informational", 2: "Success", 3: "Redirection", 4: "Client error", 5: "Server error"}[code // 100]
    return InstantAnswer(
        kind=f"http c{code // 100}", icon="🌐", title=f"HTTP {code} · {cls}", value=f"{code} {phrase}", sub=desc,
        url=f"https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/{code}" if code < 600 and code not in EXTRA_HTTP else "",
    )


def perm_str(o: int) -> str:
    return "".join(("r" if o & 4 else "-") + ("w" if o & 2 else "-") + ("x" if o & 1 else "-") for o in [o])


@handler("Developer", [])
def h_chmod(q, ql):
    m = re.fullmatch(r"chmod\s+([0-7]{3,4}|[rwxstST-]{9,10})|([0-7]{3,4})\s+permissions?", ql)
    if not m:
        return None
    s = m[1] or m[2]
    if s.isdigit():
        octal = s[-3:]
        special = int(s[0]) if len(s) == 4 else 0
        sym = "".join(perm_str(int(c)) for c in octal)
    else:
        sym = s[-9:]
        if not re.fullmatch(r"[r-][w-][xsS-][r-][w-][xsS-][r-][w-][xtT-]", sym):
            return None
        special = (4 if sym[2] in "sS" else 0) | (2 if sym[5] in "sS" else 0) | (1 if sym[8] in "tT" else 0)
        octal = "".join(str((4 if sym[i] == "r" else 0) + (2 if sym[i + 1] == "w" else 0) + (1 if sym[i + 2] in "xst" else 0)) for i in (0, 3, 6))
        sym = sym.replace("s", "x").replace("S", "-").replace("t", "x").replace("T", "-")
    grid = ["<tr><th></th><th>Read</th><th>Write</th><th>Exec</th></tr>"]
    for who, i in (("Owner", 0), ("Group", 1), ("Others", 2)):
        d = int(octal[i])
        grid.append(f"<tr><td>{who}</td>" + "".join(f'<td class="c">{"✅" if d & bit else "·"}</td>' for bit in (4, 2, 1)) + "</tr>")
    full = (str(special) if special else "") + octal
    body = f'<table class="ia-table ia-perm">{"".join(grid)}</table>' + rows_html([("Octal", full), ("Symbolic", "-" + sym), ("Command", f"chmod {full} file")])
    return InstantAnswer(kind="chmod", icon="🔐", title="File permissions", value=f"{full} · {sym}", body=body)


PORTS = {
    20: "FTP data", 21: "FTP control", 22: "SSH / SFTP / SCP", 23: "Telnet", 25: "SMTP", 53: "DNS", 67: "DHCP server", 68: "DHCP client",
    69: "TFTP", 80: "HTTP", 110: "POP3", 123: "NTP", 137: "NetBIOS name", 139: "NetBIOS session / SMB", 143: "IMAP", 161: "SNMP",
    179: "BGP", 389: "LDAP", 443: "HTTPS (and HTTP/3 over UDP)", 445: "SMB / CIFS", 465: "SMTP over TLS (submissions)",
    514: "Syslog", 587: "SMTP submission (STARTTLS)", 631: "IPP / CUPS", 636: "LDAPS", 853: "DNS over TLS",
    873: "rsync", 993: "IMAPS", 995: "POP3S", 1080: "SOCKS proxy", 1194: "OpenVPN", 1433: "Microsoft SQL Server",
    1883: "MQTT", 2049: "NFS", 2375: "Docker API (plain)", 2376: "Docker API (TLS)", 3000: "Dev servers / Grafana / AdGuard Home",
    3306: "MySQL / MariaDB", 3389: "RDP", 3478: "STUN / TURN", 4242: "", 5000: "Flask / Docker registry / UPnP",
    5173: "Vite dev server", 5353: "mDNS", 5432: "PostgreSQL", 5672: "AMQP / RabbitMQ", 5900: "VNC", 6379: "Redis / Valkey",
    6443: "Kubernetes API", 8006: "Proxmox VE web UI", 8080: "HTTP alternate / proxies", 8123: "Home Assistant",
    8443: "HTTPS alternate", 8883: "MQTT over TLS", 9000: "PHP-FPM / Portainer / MinIO", 9090: "Prometheus",
    9100: "Prometheus node exporter / raw printing", 9200: "Elasticsearch", 9987: "TeamSpeak voice (UDP)",
    10022: "TeamSpeak ServerQuery (SSH)", 11434: "Ollama", 25565: "Minecraft Java", 19132: "Minecraft Bedrock (UDP)",
    27017: "MongoDB", 30033: "TeamSpeak file transfer", 32400: "Plex", 51820: "WireGuard (UDP)",
}


@handler("Developer", [])
def h_port(q, ql):
    m = re.fullmatch(r"(?:(?:tcp|udp)\s+)?port\s+(\d{1,5})|(\d{1,5})\s+port|what\s+(?:is|runs\s+on)\s+port\s+(\d{1,5})\??", ql)
    if not m:
        return None
    p = int(m[1] or m[2] or m[3])
    if not 0 < p < 65536:
        return None
    names = []
    for proto in ("tcp", "udp"):
        try:
            names.append(f"{socket.getservbyport(p, proto)}/{proto}")
        except OSError:
            pass
    desc = PORTS.get(p) or (names[0].split("/")[0] if names else "")
    rng = "well-known (0–1023)" if p < 1024 else "registered (1024–49151)" if p < 49152 else "dynamic / ephemeral"
    if not desc and not names:
        desc = "No common service"
    return InstantAnswer(kind="port", icon="🔌", title=f"Port {p}", value=desc, sub=" · ".join(names + [rng]))


# ==========================================================================
# colour
# ==========================================================================


def hex_to_rgb(h: str) -> tuple[int, int, int, float]:
    h = h.lstrip("#")
    if len(h) in (3, 4):
        h = "".join(c * 2 for c in h)
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    a = int(h[6:8], 16) / 255 if len(h) == 8 else 1.0
    return r, g, b, a


def rgb_to_hsl(r, g, b):
    import colorsys  # pylint: disable=import-outside-toplevel

    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    return round(h * 360), round(s * 100), round(l * 100)


def hsl_to_rgb(h, s, l):
    import colorsys  # pylint: disable=import-outside-toplevel

    r, g, b = colorsys.hls_to_rgb(h / 360, l / 100, s / 100)
    return round(r * 255), round(g * 255), round(b * 255)


def lum(r, g, b):
    def ch(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(l1, l2):
    a, b = max(l1, l2), min(l1, l2)
    return (a + 0.05) / (b + 0.05)


@handler("Colour", ["#ff7a59", "rgb(30, 144, 255)", "hsl(280 60% 55%)"], local=True)
def h_color(q, ql):
    s = ql.replace(" ", "")
    m = re.fullmatch(r"(?:colou?r|hex)?:?#([0-9a-f]{3}|[0-9a-f]{4}|[0-9a-f]{6}|[0-9a-f]{8})", s) or re.fullmatch(r"(?:colou?r|hex):?([0-9a-f]{6}|[0-9a-f]{3})", s)
    a = 1.0
    if m:
        r, g, b, a = hex_to_rgb(m[1])
    else:
        m = re.fullmatch(r"rgba?\((\d{1,3})[,/]?(\d{1,3})[,/]?(\d{1,3})(?:[,/]([\d.]+%?))?\)", re.sub(r"\s+", ",", ql.strip()).replace(",,", ",").replace("(,", "(").replace(",)", ")"))
        if m:
            r, g, b = (min(255, int(x)) for x in m.group(1, 2, 3))
            if m[4]:
                a = float(m[4].rstrip("%")) / (100 if m[4].endswith("%") else 1)
        else:
            m = re.fullmatch(r"hsla?\((\d{1,3})(?:deg)?[, ]+(\d{1,3})%?[, ]+(\d{1,3})%?(?:[,/ ]+([\d.]+))?\)", re.sub(r"\s*([(),/])\s*", r"\1", ql.strip()))
            if not m:
                return None
            r, g, b = hsl_to_rgb(int(m[1]) % 360, min(100, int(m[2])), min(100, int(m[3])))
    hexv = f"#{r:02x}{g:02x}{b:02x}"
    h, sat, li = rgb_to_hsl(r, g, b)
    k = 1 - max(r, g, b) / 255
    cmyk = "0%, 0%, 0%, 100%" if k == 1 else ", ".join(f"{round((1 - c / 255 - k) / (1 - k) * 100)}%" for c in (r, g, b)) + f", {round(k * 100)}%"
    L = lum(r, g, b)
    cw, cb = contrast(L, 1.0), contrast(L, 0.0)

    def grade(c):
        return "AAA" if c >= 7 else "AA" if c >= 4.5 else "AA large" if c >= 3 else "fail"

    shades = []
    for l2 in (95, 85, 72, 60, li, 40, 30, 20, 10):
        rr, gg, bb = hsl_to_rgb(h, sat, l2)
        hx = f"#{rr:02x}{gg:02x}{bb:02x}"
        shades.append(f'<button style="background:{hx}" data-copy="{hx}" title="{hx}" class="{"cur" if l2 == li else ""}"></button>')
    harmony = []
    for name, dh in (("Complement", 180), ("Triad", 120), ("Triad", 240), ("Analogous", 30), ("Analogous", -30)):
        rr, gg, bb = hsl_to_rgb((h + dh) % 360, sat, li)
        hx = f"#{rr:02x}{gg:02x}{bb:02x}"
        harmony.append(f'<button style="background:{hx}" data-copy="{hx}" title="{name} {hx}"></button>')
    fg = "#000" if cb > cw else "#fff"
    body = (
        f'<div class="ia-swatch" style="background:{hexv};color:{fg}" data-copy="{hexv}"><b>{hexv.upper()}</b><span>Aa · click to copy</span></div>'
        f'<div class="ia-shades"><small>Shades</small>{"".join(shades)}</div>'
        f'<div class="ia-shades"><small>Harmony</small>{"".join(harmony)}</div>'
        + rows_html(
            [("HEX", hexv.upper()), ("RGB", f"rgb({r}, {g}, {b}" + (f" / {a:.2f})" if a < 1 else ")")), ("HSL", f"hsl({h} {sat}% {li}%)"), ("CMYK", cmyk),
             ("On white", f"{cw:.2f}:1 · {grade(cw)}"), ("On black", f"{cb:.2f}:1 · {grade(cb)}")]
        )
    )
    return InstantAnswer(kind="color", icon="🎨", title="Colour", body=body)


# ==========================================================================
# weather (Open-Meteo, no key)
# ==========================================================================

WMO = {
    0: ("Clear", "☀️", "🌙"), 1: ("Mainly clear", "🌤️", "🌙"), 2: ("Partly cloudy", "⛅", "☁️"), 3: ("Overcast", "☁️", "☁️"),
    45: ("Fog", "🌫️", "🌫️"), 48: ("Rime fog", "🌫️", "🌫️"), 51: ("Light drizzle", "🌦️", "🌧️"), 53: ("Drizzle", "🌦️", "🌧️"),
    55: ("Heavy drizzle", "🌧️", "🌧️"), 56: ("Freezing drizzle", "🌧️", "🌧️"), 57: ("Freezing drizzle", "🌧️", "🌧️"),
    61: ("Light rain", "🌦️", "🌧️"), 63: ("Rain", "🌧️", "🌧️"), 65: ("Heavy rain", "🌧️", "🌧️"), 66: ("Freezing rain", "🌧️", "🌧️"),
    67: ("Freezing rain", "🌧️", "🌧️"), 71: ("Light snow", "🌨️", "🌨️"), 73: ("Snow", "🌨️", "🌨️"), 75: ("Heavy snow", "❄️", "❄️"),
    77: ("Snow grains", "🌨️", "🌨️"), 80: ("Showers", "🌦️", "🌧️"), 81: ("Showers", "🌧️", "🌧️"), 82: ("Violent showers", "⛈️", "⛈️"),
    85: ("Snow showers", "🌨️", "🌨️"), 86: ("Snow showers", "❄️", "❄️"), 95: ("Thunderstorm", "⛈️", "⛈️"),
    96: ("Thunderstorm, hail", "⛈️", "⛈️"), 99: ("Thunderstorm, hail", "⛈️", "⛈️"),
}
DEFAULT_PLACE = "Copenhagen"
_WX_CACHE: dict[str, tuple[float, t.Any]] = {}
_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="ia-weather")

WEATHER_RE = re.compile(
    r"(?:(?:what(?:'s|\s+is)\s+the\s+)?(?:weather|forecast|temperature|vejret|vejr|vejrudsigt(?:en)?|sunrise|sunset|solopgang|solnedgang)"
    r"(?:\s+(?:like\s+)?(?:today|tomorrow|now|i\s+dag|i\s+morgen))?(?:\s+(?:in|for|at|i|på|near)\s+|\s+)(?P<a>[^\d].*?)|"
    r"(?P<b>[^\d].*?)\s+(?:weather|forecast|vejr|vejret|vejrudsigt))(?:\s+(?:today|tomorrow|now|i\s+dag|i\s+morgen))?\??"
)


def _http_json(url: str) -> t.Any:
    from searx import network  # pylint: disable=import-outside-toplevel

    now = time.time()
    hit = _WX_CACHE.get(url)
    if hit and now - hit[0] < 600:
        return hit[1]
    resp = network.get(url, timeout=4)
    if resp.status_code != 200:
        raise ValueError(f"HTTP {resp.status_code}")
    data = resp.json()
    if len(_WX_CACHE) > 500:
        _WX_CACHE.clear()
    _WX_CACHE[url] = (now, data)
    return data


def weather_place(ql: str) -> str | None:
    ql = re.sub(r"^(?:what(?:'s|\s+is)\s+)?(?:the\s+)?", "", ql)
    if ql in ("weather", "forecast", "vejret", "vejr", "vejrudsigt", "vejrudsigten", "sunrise", "sunset", "weather today", "vejret i dag"):
        return DEFAULT_PLACE
    m = WEATHER_RE.fullmatch(ql)
    if not m:
        return None
    place = (m["a"] or m["b"] or "").strip(" ?,")
    if not place or len(place) > 60 or re.search(r"\b(app|channel|api|widget|report|station|radar|underground|com|dk|network|forecast)\b", place):
        return None
    return place


def fetch_weather(place: str) -> InstantAnswer | None:
    geo = _http_json(
        "https://geocoding-api.open-meteo.com/v1/search?" + urllib.parse.urlencode({"name": place, "count": 1, "language": "en", "format": "json"})
    )
    if not geo.get("results"):
        return None
    g = geo["results"][0]
    params = {
        "latitude": g["latitude"], "longitude": g["longitude"], "timezone": "auto", "forecast_days": 7, "wind_speed_unit": "ms",
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,wind_gusts_10m,wind_direction_10m,is_day,precipitation",
        "hourly": "temperature_2m,precipitation_probability,precipitation",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,sunrise,sunset,precipitation_probability_max,precipitation_sum,uv_index_max",
    }
    wx = _http_json("https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(params))
    cur, daily, hourly = wx["current"], wx["daily"], wx["hourly"]
    desc, day_icon, night_icon = WMO.get(cur["weather_code"], ("—", "🌡️", "🌡️"))
    icon = day_icon if cur.get("is_day", 1) else night_icon
    compass = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][round(cur["wind_direction_10m"] / 45) % 8]
    where = ", ".join(x for x in (g.get("name"), g.get("admin1") if g.get("admin1") != g.get("name") else None, g.get("country")) if x)

    # next 24 h: temperature line + rain-probability bars
    now_idx = next((i for i, tm in enumerate(hourly["time"]) if tm >= cur["time"][:13]), 0)
    temps = hourly["temperature_2m"][now_idx:now_idx + 25]
    probs = hourly["precipitation_probability"][now_idx:now_idx + 25]
    times = hourly["time"][now_idx:now_idx + 25]
    spark = ""
    if len(temps) > 2:
        lo, hi = min(temps), max(temps)
        span = (hi - lo) or 1
        W, H = 600, 110
        xs = [i * W / (len(temps) - 1) for i in range(len(temps))]
        ys = [18 + (1 - (v - lo) / span) * (H - 50) for v in temps]
        line = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
        area = f"0,{H - 22} " + line + f" {W},{H - 22}"
        bars = "".join(
            f'<rect x="{x - 6:.1f}" y="{H - 22 - (p or 0) * 0.3:.1f}" width="12" height="{(p or 0) * 0.3:.1f}" class="rain"><title>{p}% rain</title></rect>'
            for x, p in zip(xs, probs) if p
        )
        labels = "".join(
            f'<text x="{x:.1f}" y="{y - 7:.1f}" class="t">{round(v)}°</text><text x="{x:.1f}" y="{H - 6}" class="h">{tm[11:13]}</text>'
            for i, (x, y, v, tm) in enumerate(zip(xs, ys, temps, times)) if i % 3 == 0
        )
        spark = (
            f'<svg class="ia-wx-spark" viewBox="-12 0 624 {H}" preserveAspectRatio="none">'
            f'<polygon points="{area}" class="area"/>{bars}<polyline points="{line}" class="line"/>{labels}</svg>'
        )
    tmin, tmax = min(daily["temperature_2m_min"]), max(daily["temperature_2m_max"])
    rng = (tmax - tmin) or 1
    days = []
    for i, day in enumerate(daily["time"]):
        d = dt.date.fromisoformat(day)
        _, di, _ = WMO.get(daily["weather_code"][i], ("", "🌡️", ""))
        lo, hi = daily["temperature_2m_min"][i], daily["temperature_2m_max"][i]
        pp = daily["precipitation_probability_max"][i]
        days.append(
            f'<div class="ia-wx-day"><b>{"Today" if i == 0 else calendar.day_abbr[d.weekday()]}</b><span class="i">{di}</span>'
            f'<span class="bar"><i style="left:{(lo - tmin) / rng * 100:.0f}%;right:{(tmax - hi) / rng * 100:.0f}%"></i></span>'
            f'<span class="hl"><b>{round(hi)}°</b> {round(lo)}°</span><small>{"💧" + str(pp) + "%" if pp else "&nbsp;"}</small></div>'
        )
    sr, ss = daily["sunrise"][0][11:16], daily["sunset"][0][11:16]
    body = (
        f'<div class="ia-wx-now"><span class="ia-wx-icon">{icon}</span><span class="ia-wx-temp">{round(cur["temperature_2m"])}°</span>'
        f'<div class="ia-wx-meta"><b>{e(desc)}</b><span>Feels like {round(cur["apparent_temperature"])}° · H {round(daily["temperature_2m_max"][0])}° L {round(daily["temperature_2m_min"][0])}°</span>'
        f'<span>💨 {cur["wind_speed_10m"]:.0f} m/s {compass} (gusts {cur["wind_gusts_10m"]:.0f}) · 💧 {cur["relative_humidity_2m"]}% · ☔ {daily["precipitation_sum"][0]:.1f} mm</span>'
        f'<span>🌅 {sr} · 🌇 {ss} · UV {daily["uv_index_max"][0]:.0f}</span></div></div>'
        f'{spark}<div class="ia-wx-days">{"".join(days)}</div>'
    )
    return InstantAnswer(
        kind="weather", icon="🌦️", title=where, body=body, source="Open-Meteo",
        url=f"https://open-meteo.com/en/docs#latitude={g['latitude']}&longitude={g['longitude']}",
    )


# ==========================================================================
# world clock (geocoded via Open-Meteo, time zone math is local)
# ==========================================================================

HOME_TZ = "Europe/Copenhagen"
TIME_RE = re.compile(
    r"(?:what(?:'s|\s+is)\s+the\s+)?(?:current\s+|local\s+)?(?:time|clock|klokken|tid(?:en)?)\s+(?:is\s+it\s+)?(?:right\s+now\s+)?(?:in|at|i|på)\s+(.+?)\??|"
    r"what\s+time\s+is\s+it\s+(?:in|at)\s+(.+?)\??|hvad\s+er\s+klokken\s+i\s+(.+?)\??|(.+?)\s+(?:local|current)\s+time|time\s+(.+)"
)


def time_place(ql: str) -> tuple[str, bool] | None:
    """(place, strict) — strict for the loose "time <x>" form, which only
    counts when <x> geocodes to a real city (so "time magazine" stays a search)."""
    if re.fullmatch(r"(?:what\s+)?time(?:\s+is\s+it)?(?:\s+now)?\??|clock|klokken|hvad\s+er\s+klokken\??|what(?:'s|\s+is)\s+the\s+time\??", ql):
        return "", False
    m = TIME_RE.fullmatch(ql)
    if not m:
        return None
    place = next(g for g in m.groups() if g).strip(" ?")
    if len(place) > 50 or re.search(r"\b(?:zone|zones|management|machine|travel|lapse|series|complexity|limit|table|traveler)\b", place):
        return None
    return place, bool(m.group(5))


def clock_card(tzname: str, where: str) -> InstantAnswer:
    from zoneinfo import ZoneInfo  # pylint: disable=import-outside-toplevel

    tz = ZoneInfo(tzname)
    now = dt.datetime.now(tz)
    home = dt.datetime.now(ZoneInfo(HOME_TZ))
    off = now.utcoffset() or dt.timedelta()
    diff = (off - (home.utcoffset() or dt.timedelta())).total_seconds() / 3600
    sign = "+" if off >= dt.timedelta() else "−"
    offs = f"UTC{sign}{abs(int(off.total_seconds() // 3600)):d}" + (f":{int(abs(off.total_seconds()) % 3600 // 60):02d}" if off.total_seconds() % 3600 else "")
    rel = "same time as Copenhagen" if diff == 0 else f"{fmt(abs(diff), 2)} h {'ahead of' if diff > 0 else 'behind'} Copenhagen"
    hour = now.hour + now.minute / 60
    body = (
        f'<div class="ia-worldclock" data-tz="{e(tzname)}"><span class="ia-clock-face ia-live-time">{now:%H:%M:%S}</span>'
        f'<span class="ia-daynight" style="--h:{hour:.2f}">{"☀️" if 7 <= now.hour < 19 else "🌙"}</span></div>'
        + rows_html([("Date", date_long(now.date())), ("Time zone", f"{tzname.replace('_', ' ')} · {now:%Z} · {offs}"), ("Compared", rel)], copy=False)
    )
    return InstantAnswer(kind="worldclock", icon="🕰️", title=where, body=body)


def fetch_clock(place: str, strict: bool = False) -> InstantAnswer | None:
    if not place:
        return clock_card(HOME_TZ, "Copenhagen, Denmark")
    geo = _http_json(
        "https://geocoding-api.open-meteo.com/v1/search?" + urllib.parse.urlencode({"name": place, "count": 1, "language": "en", "format": "json"})
    )
    if not geo.get("results") or not geo["results"][0].get("timezone"):
        return None
    g = geo["results"][0]
    if strict and (g.get("population") or 0) < 50000:
        return None
    where = ", ".join(x for x in (g.get("name"), g.get("country")) if x)
    return clock_card(g["timezone"], where)


def my_ip_card(request: "SXNG_Request") -> InstantAnswer:
    ip = request.remote_addr or "?"
    try:
        addr = ipaddress.ip_address(ip)
        ver = f"IPv{addr.version}"
    except ValueError:
        ver = ""
    body = rows_html([("Version", ver), ("User agent", str(request.user_agent))])
    return InstantAnswer(kind="ip", icon="📍", title="Your public IP address", value=ip, body=body, copy=ip)


MY_IP_RE = re.compile(r"(?:what(?:'s|\s+is)\s+)?(?:my\s+)?(?:public\s+)?ip(?:\s+address)?\??|whats\s+my\s+ip\??|min\s+ip(?:\s*adresse)?|hvad\s+er\s+min\s+ip\??|user[\s-]?agent|my\s+user[\s-]?agent")


# ==========================================================================
# site ranking management card ("sites")
# ==========================================================================


# answered by the smallapp_sites plugin (it needs the request cookie)
EXAMPLES["Your search"] = ["sites", "help"]
EXAMPLES["Timers & time"] += ["time in tokyo"]
EXAMPLES["Developer"] += ["what is my ip"]


def help_card() -> InstantAnswer:
    parts = []
    for section, ex in EXAMPLES.items():
        if not ex:
            continue
        parts.append(f'<div class="ia-help-sec"><h5>{e(section)}</h5><div>{"".join(search_link(x) for x in ex)}</div></div>')
    parts.append(
        '<div class="ia-help-sec"><h5>Built in</h5><div>'
        + "".join(search_link(x) for x in ("2^10 * 3", "10 km to miles", "100 usd to dkk", "sha256 hello", "random color"))
        + "</div></div>"
    )
    return InstantAnswer(kind="help", icon="✨", title="Instant answers — things you can type", body='<div class="ia-help">' + "".join(parts) + "</div>")


# --------------------------------------------------------------------------
# plugin
# --------------------------------------------------------------------------


class SXNGPlugin(Plugin):
    """Instant answers: dice, coins, timers, weather, dates, colours, dev tools …"""

    id = "smallapp_answers"

    def __init__(self, plg_cfg: "PluginCfg") -> None:
        super().__init__(plg_cfg)
        self.info = PluginInfo(
            id=self.id,
            name="Instant answers",
            description=(
                "Dice, coins, timers, weather, week numbers, holidays, colours, subnets, HTTP codes, "
                "encoders and more — search “help” for the full list. Pure tools (dice, encoders, a pasted JWT …) "
                "are answered locally without asking any search engine."
            ),
            examples=["roll 2d6", "weather aarhus", "timer 5 min", "help"],
            preference_section="query",
        )

    def _compute(self, search: "SearchWithPlugins") -> tuple[InstantAnswer | None, bool]:
        q = search.search_query.query.strip()
        if not q or len(q) > 2000 or search.search_query.pageno > 1:
            return None, False
        ql = re.sub(r"\s+", " ", q.lower())
        if ql in ("help", "instant answers", "tricks", "!help", "hjælp", "what can you do"):
            return help_card(), False
        for h in HANDLERS:
            try:
                ans = h.fn(q, ql)
            except Exception:  # pylint: disable=broad-except
                self.log.exception("handler %s failed", h.fn.__name__)
                continue
            if ans is not None:
                return ans, h.local
        return None, False

    def pre_search(self, request: "SXNG_Request", search: "SearchWithPlugins") -> bool:
        ans, local = self._compute(search)
        search._ia_answer = ans  # pylint: disable=protected-access
        search._ia_future = None  # pylint: disable=protected-access
        if ans is None and search.search_query.pageno == 1:
            ql = re.sub(r"\s+", " ", search.search_query.query.strip().lower())
            if MY_IP_RE.fullmatch(ql):
                search._ia_answer = my_ip_card(request)  # pylint: disable=protected-access
                return True
            # network-backed answers: fetch while the engines run, joined in post_search
            tp = time_place(ql)
            if tp is not None:
                search._ia_future = _POOL.submit(fetch_clock, *tp)  # pylint: disable=protected-access
            else:
                place = weather_place(ql)
                if place:
                    search._ia_future = _POOL.submit(fetch_weather, place)  # pylint: disable=protected-access
        return not local

    def post_search(self, request: "SXNG_Request", search: "SearchWithPlugins") -> EngineResults:
        results = EngineResults()
        ans = getattr(search, "_ia_answer", None)
        fut = getattr(search, "_ia_future", None)
        if fut is not None:
            try:
                ans = fut.result(timeout=5)
            except Exception as exc:  # pylint: disable=broad-except
                self.log.warning("lookup failed: %s", exc)
        if ans is not None:
            results.add(ans)
        return results
