# pylint: disable=missing-module-docstring
"""Per-browser site ranking for search.smallapp.cc (Kagi-style "personalize").

Every result gets a small menu (added by ``sxng-extras.js``) to **boost**,
**lower** or **block** its domain.  The choices live in one cookie on the
user's own browser — nothing is stored server-side, and each browser/person
keeps their own list:

    sx_sites = "github.com!b~pinterest.com!x~quora.com!l"

Modes: ``b`` boost (ranked like a top hit from every engine), ``l`` lower
(sinks below everything else), ``x`` block (removed), ``n`` neutral (only
used to switch off one of the built-in :py:data:`DEFAULTS`).

A rule for ``example.com`` also covers its subdomains; ``pinterest.*`` covers
every TLD.  Searching ``sites`` shows (and edits) the current list.
"""

from __future__ import annotations

import re
import typing as t
import urllib.parse

from markupsafe import escape

from searx.plugins import Plugin, PluginInfo
from searx.result_types import EngineResults
from searx.result_types._base import LegacyResult, MainResult

from searx.plugins.smallapp_answers import InstantAnswer

if t.TYPE_CHECKING:
    from searx.extended_types import SXNG_Request
    from searx.plugins import PluginCfg
    from searx.result_types import Result
    from searx.search import SearchWithPlugins

COOKIE = "sx_sites"
MODES = {"b": "boost", "l": "lower", "x": "block", "n": "neutral"}

# Applied for everyone unless their cookie says otherwise for that domain.
DEFAULTS: dict[str, str] = {
    "pinterest.*": "l",  # image-pin walls that match everything and link nowhere useful
}

SITES_QUERIES = ("sites", "my sites", "site rankings", "site ranking", "blocked sites", "mine sider")

DOMAIN_RE = re.compile(r"^(?:\*\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)*(?:\.\*)?$")


def parse_cookie(raw: str | None) -> dict[str, str]:
    rules: dict[str, str] = {}
    if not raw:
        return rules
    raw = urllib.parse.unquote(raw)
    for item in raw.split("~")[:500]:
        dom, _, mode = item.rpartition("!")
        dom = dom.strip().lower().removeprefix("www.")
        if mode in MODES and DOMAIN_RE.match(dom) and len(dom) <= 253:
            rules[dom] = mode
    return rules


def match(host: str, rule: str) -> bool:
    host = host.lower().split(":")[0]
    if rule.endswith(".*"):
        base = rule[:-2]
        labels = host.split(".")
        # "pinterest.*" → pinterest.com, pinterest.co.uk, dk.pinterest.com …
        for i, lab in enumerate(labels):
            if ".".join(labels[i:i + base.count(".") + 1]) == base and 1 <= len(labels) - (i + base.count(".") + 1) <= 2:
                return True
        return False
    return host == rule or host.endswith("." + rule)


def rules_for(request: "SXNG_Request") -> dict[str, str]:
    rules = dict(DEFAULTS)
    rules.update(parse_cookie(request.cookies.get(COOKIE)))
    return {d: m for d, m in rules.items() if m != "n"}


class SXNGPlugin(Plugin):
    """Boost, lower or block sites — per browser, stored in a cookie."""

    id = "smallapp_sites"

    def __init__(self, plg_cfg: "PluginCfg") -> None:
        super().__init__(plg_cfg)
        self.info = PluginInfo(
            id=self.id,
            name="Personal site ranking",
            description=(
                "Use the ⋯ menu on any result to boost, lower or block that site. "
                "Your list lives in a cookie in this browser only; search “sites” to review it."
            ),
            examples=["sites"],
            preference_section="general",
        )

    def on_result(self, request: "SXNG_Request", search: "SearchWithPlugins", result: "Result") -> bool:
        if not isinstance(result, (MainResult, LegacyResult)) or not result.parsed_url:
            return True
        rules = getattr(search, "_sx_rules", None)
        if rules is None:
            rules = search._sx_rules = rules_for(request)  # pylint: disable=protected-access
        if not rules:
            return True
        host = result.parsed_url.netloc
        best = None
        # the most specific (longest) matching rule wins: blog.example.com over example.com
        for dom, mode in rules.items():
            if match(host, dom) and (best is None or len(dom) > len(best[0])):
                best = (dom, mode)
        if best is None:
            return True
        if best[1] == "x":
            return False
        result.priority = "high" if best[1] == "b" else "low"
        return True

    def pre_search(self, request: "SXNG_Request", search: "SearchWithPlugins") -> bool:
        # the management card needs no web results
        return search.search_query.query.strip().lower() not in SITES_QUERIES

    def post_search(self, request: "SXNG_Request", search: "SearchWithPlugins") -> EngineResults:
        results = EngineResults()
        # Upstream's "high" priority scores a result as if it were #1 at each
        # engine that found it, so a boosted site found by one engine only ties
        # an ordinary top hit. Score grows with len(positions)², so three extra
        # #1 positions make a boost reliably win. Runs before the container is
        # closed (= scored); only this plugin sets "high" (hostnames is unused).
        for res in getattr(search.result_container, "main_results_map", {}).values():
            if getattr(res, "priority", "") == "high":
                res["positions"].extend([1, 1, 1])
        q = search.search_query.query.strip().lower()
        if search.search_query.pageno > 1 or q not in SITES_QUERIES:
            return results
        user = parse_cookie(request.cookies.get(COOKIE))
        rows = []
        merged = dict(DEFAULTS) | user
        for dom in sorted(merged, key=lambda d: ("bxln".index(merged[d]), d)):
            mode = merged[dom]
            default = dom in DEFAULTS and dom not in user
            e = escape(dom)
            rows.append(
                f'<tr data-dom="{e}"><td class="dom">{e}{" <small>(default)</small>" if default else ""}</td>'
                f'<td><span class="ia-mode m-{mode}">{MODES[mode]}</span></td>'
                f'<td class="r"><div class="ia-seg">'
                + "".join(
                    f'<button data-site-set="{m}" class="{"on" if m == mode else ""}" title="{MODES[m]}">{lbl}</button>'
                    for m, lbl in (("b", "▲"), ("l", "▼"), ("x", "⊘"))
                )
                + '<button data-site-set="" title="Forget">✕</button></div></td></tr>'
            )
        table = f'<table class="ia-table ia-sites">{"".join(rows)}</table>' if rows else '<p class="ia-note">No rules yet.</p>'
        body = (
            table
            + '<form class="ia-site-add"><input name="dom" placeholder="example.com or pinterest.*" autocomplete="off" spellcheck="false">'
            '<select name="mode"><option value="b">▲ Boost</option><option value="l">▼ Lower</option><option value="x">⊘ Block</option></select>'
            '<button class="ia-btn">Add</button></form>'
            '<div class="ia-note">Stored only in this browser (cookie <code>sx_sites</code>). '
            "Tip: every result has a ⋯ menu for one-click boosting/blocking. Changes apply to your next search.</div>"
        )
        results.add(InstantAnswer(kind="sites", icon="⭐", title="Your site rankings", body=body))
        return results
