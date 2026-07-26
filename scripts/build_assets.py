#!/usr/bin/env python3
"""Regenerate the profile README's SVG assets.

Everything the profile shows is drawn here, so the page has no dependency on
third-party card services (which go down: github-readme-stats has been
returning 503 DEPLOYMENT_PAUSED and github-profile-trophy 402 for months).

    python3 scripts/build_assets.py

Requires the `gh` CLI, authenticated. Writes into assets/.

Two variants of every panel, light and dark, chosen by the README through
prefers-color-scheme. The panels draw on a TRANSPARENT background on purpose:
a panel carrying its own fill sits as a slab of the wrong colour for half the
readers, which is the whole reason this is themed rather than one dark artwork.

Visual language: no fill, hairline rules, graph-paper grid, corner register
marks, one amber signal colour, monospace-led type. Deliberately no radial
gradient blooms, no violet-to-cyan wash and no abstract node constellation --
that trio is the house style of machine-generated "tech" pages.

Calendar note: contributionsCollection returns only PUBLIC contributions
unless "Include private contributions on my profile" is enabled in GitHub
profile settings. That setting is ON as of 2026-07-26 (total went 217 -> 751,
restrictedContributionsCount 533). If it is ever switched off the totals here
drop silently -- restrictedContributionsCount reads 0 rather than flagging a
gap.
"""

from __future__ import annotations

import json
import re
import subprocess
import urllib.request
from datetime import date
from pathlib import Path
from typing import NamedTuple

USER = "KaichenQu"
ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"


class Theme(NamedTuple):
    name: str
    bg_lum: float  # relative luminance of the page behind the panel
    grid: str
    rule: str
    rule_f: str
    text: str
    muted: str
    faint: str
    accent: str
    accent_d: str
    chip: str
    icon_contrast: float
    levels: tuple[str, str, str, str, str]


DARK = Theme(
    name="dark",
    bg_lum=0.006,  # GitHub dark canvas #0d1117
    grid="#1B1B21",
    rule="#2A2A33",
    rule_f="#17171C",
    text="#E8E8EA",
    muted="#8A8A93",
    faint="#5C5C65",
    accent="#FFB224",
    accent_d="#9A6A18",
    chip="#141418",
    # 3:1 leaves the near-black brands (Express, Next.js, OpenAI, Kafka) muddy
    # beside the fully saturated marks around them; on white nothing is at risk
    icon_contrast=5.5,
    levels=("#191920", "#4A3411", "#8A5E14", "#C78C1A", "#FFB224"),
)

LIGHT = Theme(
    name="light",
    bg_lum=1.0,  # GitHub light canvas #ffffff
    grid="#E6E6EC",
    rule="#D3D3DB",
    rule_f="#F0F0F4",
    text="#0E0E13",
    muted="#4A4A55",
    faint="#8B8B96",
    accent="#B45309",
    accent_d="#8A6412",
    chip="#FAFAFB",
    icon_contrast=3.0,
    levels=("#EDEDF1", "#FADFA9", "#EFAA42", "#CE7C0B", "#9C5300"),
)

MONO = (
    "ui-monospace,'SFMono-Regular','SF Mono',Menlo,Consolas,'Liberation Mono',monospace"
)
SANS = "system-ui,-apple-system,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif"

SI = "https://cdn.jsdelivr.net/npm/simple-icons@15/icons/{}.svg"
DEVICON = (
    "https://cdn.jsdelivr.net/gh/devicons/devicon@master/icons/{0}/{0}-original.svg"
)
DEVICON_WORDMARK = (
    "https://cdn.jsdelivr.net/gh/devicons/devicon@master/icons/{0}/"
    "{0}-original-wordmark.svg"
)


def esc(s: str) -> str:
    """Escape for both XML text nodes and attribute values."""
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "profile-build"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode()


# ── colour ────────────────────────────────────────────────────────────────────
def _lin(c: float) -> float:
    c /= 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(rgb: tuple[float, ...]) -> float:
    r, g, b = (_lin(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: float, b: float) -> float:
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def legible(color: str, bg_lum: float, target: float = 3.0) -> str:
    """Nudge a brand colour until it clears `target` contrast on the page.

    Lets the STACK table state each tool's real brand colour once instead of
    carrying a hand-tuned variant per theme. Kafka's near-black and
    JavaScript's yellow are each invisible on exactly one of the two
    backgrounds, and hand-maintained per-theme overrides drift.
    """
    h = color.lstrip("#")
    rgb = tuple(float(int(h[i : i + 2], 16)) for i in (0, 2, 4))
    if contrast(luminance(rgb), bg_lum) >= target:
        return color
    darken = bg_lum > 0.5
    for i in range(1, 25):
        f = i / 24
        out = (
            tuple(c * (1 - f) for c in rgb)
            if darken
            else tuple(c + (255 - c) * f for c in rgb)
        )
        if contrast(luminance(out), bg_lum) >= target:
            return "#{:02X}{:02X}{:02X}".format(*(round(c) for c in out))
    return "#000000" if darken else "#FFFFFF"


# ── icon sourcing ─────────────────────────────────────────────────────────────
_ICONS: dict[str, tuple[list[str], float, float]] = {}


def icon_paths(slug: str) -> tuple[list[str], float, float]:
    """Return an icon's path `d` strings plus its source viewBox width/height.

    simple-icons is the preferred source (square 24x24, single path). AWS is not
    in simple-icons for trademark reasons, so it falls back to devicon, whose
    only AWS asset is a wide wordmark -- hence the caller scales by viewBox
    rather than assuming 24x24. Cached: both themes draw the same glyphs.
    """
    if slug in _ICONS:
        return _ICONS[slug]

    svg = None
    for url in (SI.format(slug), DEVICON.format(slug), DEVICON_WORDMARK.format(slug)):
        try:
            svg = fetch(url)
            break
        except Exception:
            continue
    if svg is None:
        raise RuntimeError(f"no icon found for {slug!r}")

    vb = re.search(r'viewBox="([\d.\s-]+)"', svg)
    if vb:
        _, _, vw, vh = (float(v) for v in vb.group(1).split())
    else:
        vw = vh = 24.0
    _ICONS[slug] = (re.findall(r'\sd="([^"]+)"', svg), vw, vh)
    return _ICONS[slug]


# (label, simple-icons slug, real brand colour). The colour is the brand's own
# value -- legible() adjusts it per theme, so no entry needs a light/dark
# variant. Icons keep their brand identity on purpose: they are the content,
# and only the chrome around them is monochrome.
STACK = [
    (
        "Languages",
        [
            ("Java", "openjdk", "#E76F00"),
            ("Python", "python", "#3776AB"),
            ("Go", "go", "#00ADD8"),
            ("TypeScript", "typescript", "#3178C6"),
            ("JavaScript", "javascript", "#F7DF1E"),
            ("Bash", "gnubash", "#4EAA25"),
        ],
    ),
    (
        "Backend",
        [
            ("Spring Boot", "springboot", "#6DB33F"),
            ("FastAPI", "fastapi", "#009688"),
            ("Django", "django", "#092E20"),
            ("Express", "express", "#000000"),
            ("Node.js", "nodedotjs", "#5FA04E"),
            ("GraphQL", "graphql", "#E10098"),
        ],
    ),
    (
        "Data",
        [
            ("PostgreSQL", "postgresql", "#4169E1"),
            ("MySQL", "mysql", "#4479A1"),
            ("MongoDB", "mongodb", "#47A248"),
            ("Redis", "redis", "#FF4438"),
            ("Kafka", "apachekafka", "#231F20"),
            ("Elasticsearch", "elasticsearch", "#00BFB3"),
        ],
    ),
    (
        "Cloud & infra",
        [
            ("GCP", "googlecloud", "#4285F4"),
            ("AWS", "amazonwebservices", "#FF9900"),
            ("Docker", "docker", "#2496ED"),
            ("Kubernetes", "kubernetes", "#326CE5"),
            ("Terraform", "terraform", "#7B42BC"),
            ("CI/CD", "githubactions", "#2088FF"),
        ],
    ),
    (
        "Frontend",
        [
            ("React", "react", "#61DAFB"),
            ("Next.js", "nextdotjs", "#000000"),
            ("Tailwind", "tailwindcss", "#06B6D4"),
            ("Redux", "redux", "#764ABC"),
            ("Vite", "vite", "#646CFF"),
        ],
    ),
    (
        "AI",
        [
            ("Anthropic", "anthropic", "#D97757"),
            ("OpenAI", "openai", "#000000"),
            ("LangChain", "langchain", "#1C3C3C"),
        ],
    ),
]


# ── shared panel chrome ───────────────────────────────────────────────────────
def defs(t: Theme) -> str:
    """Graph-paper grid: a fine 10px module with a heavier line every 50px."""
    return (
        "<defs>"
        '<pattern id="fine" width="10" height="10" patternUnits="userSpaceOnUse">'
        f'<path d="M10 0H0V10" fill="none" stroke="{t.rule_f}" stroke-width="0.5"/>'
        "</pattern>"
        '<pattern id="coarse" width="50" height="50" patternUnits="userSpaceOnUse">'
        '<rect width="50" height="50" fill="url(#fine)"/>'
        f'<path d="M50 0H0V50" fill="none" stroke="{t.grid}" stroke-width="1"/>'
        "</pattern>"
        "</defs>"
    )


def panel(t: Theme, w: float, h: float) -> list[str]:
    """Graph paper + hairline border + corner register marks, and no fill.

    No background rect: the panel inherits the page, which is what stops it
    reading as a slab pasted onto the README.
    """
    inset, arm = 16, 7
    marks = [
        f'<path d="M{cx - arm} {cy}H{cx + arm}M{cx} {cy - arm}V{cy + arm}" '
        f'stroke="{t.rule}" stroke-width="1"/>'
        for cx, cy in (
            (inset, inset),
            (w - inset, inset),
            (inset, h - inset),
            (w - inset, h - inset),
        )
    ]
    return [
        defs(t),
        f'<rect width="{w}" height="{h}" rx="6" fill="url(#coarse)"/>',
        f'<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="6" '
        f'fill="none" stroke="{t.rule}"/>',
        *marks,
    ]


def heading(t: Theme, x: float, y: float, title: str, kicker: str) -> list[str]:
    return [
        f'<text x="{x}" y="{y}" font-family="{MONO}" font-size="11" '
        f'fill="{t.accent}" letter-spacing="3">{esc(kicker)}</text>',
        f'<text x="{x}" y="{y + 26}" font-family="{SANS}" font-size="19" '
        f'font-weight="600" fill="{t.text}">{esc(title)}</text>',
    ]


def write(t: Theme, stem: str, body: str) -> None:
    (ASSETS / f"{stem}-{t.name}.svg").write_text(body)


# ── contribution calendar ─────────────────────────────────────────────────────
def calendar() -> dict:
    q = """
    query($login:String!) {
      user(login:$login) {
        contributionsCollection {
          contributionCalendar {
            totalContributions
            weeks { firstDay contributionDays { date contributionCount weekday } }
          }
        }
      }
    }"""
    out = subprocess.run(
        ["gh", "api", "graphql", "-f", f"query={q}", "-F", f"login={USER}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return json.loads(out)["data"]["user"]["contributionsCollection"][
        "contributionCalendar"
    ]


def level_of(count: int, thresholds: list[int]) -> int:
    for i, th in enumerate(thresholds):
        if count <= th:
            return i
    return 4


def longest_streak(days: list[dict]) -> int:
    """Longest run of consecutive days with at least one contribution."""
    longest = run = 0
    for d in days:
        run = run + 1 if d["contributionCount"] > 0 else 0
        longest = max(longest, run)
    return longest


def build_contributions(t: Theme, cal: dict) -> None:
    weeks = cal["weeks"]
    days = [d for w in weeks for d in w["contributionDays"]]
    total = cal["totalContributions"]

    # Quantiles over every active DAY, not over the distinct counts. Ranking
    # distinct values instead buries the shape of a bursty year: it pushes most
    # days into the dimmest band and strands one alone at the top.
    counts = sorted(d["contributionCount"] for d in days if d["contributionCount"] > 0)
    if counts:
        q = [
            counts[min(len(counts) - 1, int(len(counts) * f))]
            for f in (0.0, 0.4, 0.7, 0.9)
        ]
        thresholds = [0, q[1], q[2], q[3]]
    else:
        thresholds = [0, 1, 2, 3]

    active = sum(1 for d in days if d["contributionCount"] > 0)
    busiest = max(days, key=lambda d: d["contributionCount"])
    longest = longest_streak(days)

    CELL, GAP = 12, 4
    STEP = CELL + GAP
    PAD_L, PAD_T = 116, 116
    W = PAD_L + len(weeks) * STEP + 34
    H = PAD_T + 7 * STEP + 96

    o: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" role="img" '
        f'aria-label="GitHub contribution calendar: {total} contributions '
        f'in the last year">',
        f"<title>{total} contributions in the last year</title>",
        *panel(t, W, H),
        *heading(t, 34, 46, "Contribution calendar", "COMMIT LOG"),
        f'<text x="{W - 34}" y="50" text-anchor="end" font-family="{MONO}" '
        f'font-size="33" font-weight="700" fill="{t.accent}">{total}</text>',
        f'<text x="{W - 34}" y="70" text-anchor="end" font-family="{MONO}" '
        f'font-size="10" fill="{t.faint}" letter-spacing="2">'
        f"{days[0]['date']} / {days[-1]['date']}</text>",
        f'<line x1="34" y1="88" x2="{W - 34}" y2="88" stroke="{t.rule}"/>',
    ]

    for wd, name in ((1, "MON"), (3, "WED"), (5, "FRI")):
        y = PAD_T + wd * STEP + CELL - 2
        o.append(
            f'<text x="{PAD_L - 14}" y="{y}" text-anchor="end" font-family="{MONO}" '
            f'font-size="9.5" fill="{t.faint}" letter-spacing="1">{name}</text>'
        )

    # month ruler. The window starts mid-month, so week 0 and week 1 can both be
    # "first week of a month" -- hold a minimum gap or the two labels collide.
    seen: set[str] = set()
    last_x = -999.0
    for wi, w in enumerate(weeks):
        m = date.fromisoformat(w["firstDay"]).strftime("%b").upper()
        x = PAD_L + wi * STEP
        if m not in seen and wi < len(weeks) - 1 and x - last_x >= 46:
            seen.add(m)
            last_x = x
            o.append(
                f'<path d="M{x} {PAD_T - 12}v5" stroke="{t.rule}"/>'
                f'<text x="{x}" y="{PAD_T - 18}" font-family="{MONO}" '
                f'font-size="9.5" fill="{t.faint}" letter-spacing="1">{m}</text>'
            )

    for wi, w in enumerate(weeks):
        for d in w["contributionDays"]:
            n = d["contributionCount"]
            lv = level_of(n, thresholds) if n else 0
            o.append(
                f'<rect x="{PAD_L + wi * STEP}" y="{PAD_T + d["weekday"] * STEP}" '
                f'width="{CELL}" height="{CELL}" rx="1.5" fill="{t.levels[lv]}">'
                f"<title>{d['date']} &#183; {n}</title></rect>"
            )

    # legend, naming the band each tone stands for. A bare Less-to-More ramp
    # says nothing about whether a lit cell means one commit or eighteen.
    ly = PAD_T + 7 * STEP + 28
    bands = ["0"]
    for n in range(1, 4):
        lo, hi = thresholds[n - 1] + 1, thresholds[n]
        bands.append(str(lo) if lo >= hi else f"{lo}-{hi}")
    bands.append(f"{thresholds[3] + 1}+")

    for n, c in enumerate(t.levels):
        cx = PAD_L + n * 42
        o.append(
            f'<rect x="{cx}" y="{ly}" width="{CELL}" height="{CELL}" rx="1.5" '
            f'fill="{c}"/>'
            f'<text x="{cx + CELL / 2}" y="{ly + 25}" text-anchor="middle" '
            f'font-family="{MONO}" font-size="9" fill="{t.faint}">{bands[n]}</text>'
        )
    o.append(
        f'<text x="{PAD_L - 14}" y="{ly + 10}" text-anchor="end" font-family="{MONO}" '
        f'font-size="9.5" fill="{t.faint}" letter-spacing="1">PER DAY</text>'
    )

    sx = W - 34
    for label, value in reversed(
        [
            ("ACTIVE DAYS", str(active)),
            ("LONGEST RUN", f"{longest}d"),
            ("PEAK DAY", str(busiest["contributionCount"])),
        ]
    ):
        o.append(
            f'<text x="{sx}" y="{ly + 2}" text-anchor="end" font-family="{MONO}" '
            f'font-size="17" font-weight="700" fill="{t.text}">{value}</text>'
            f'<text x="{sx}" y="{ly + 20}" text-anchor="end" font-family="{MONO}" '
            f'font-size="9" fill="{t.faint}" letter-spacing="1.4">{label}</text>'
        )
        sx -= 128

    o.append("</svg>")
    write(t, "contributions", "".join(o))
    if t is DARK:
        print(f"  contributions      {total} total · {active} active days")


# ── hero ──────────────────────────────────────────────────────────────────────
# A drawing title block: label column, value column, hairline ruled. Every row
# is a fact stated elsewhere in the profile -- nothing invented to fill a grid.
TITLE_BLOCK = [
    ("ROLE", "Backend / distributed systems"),
    ("FOCUS", "Agentic AI, cloud infrastructure"),
    ("EDU", "M.S. Computer Science, Northeastern"),
    ("LOC", "Fremont, CA · 37.55°N 121.99°W"),
]

NAME = "KELSON QU"
# Monospace advance is ~0.6em across the stack in MONO, which is what lets the
# caret be placed by arithmetic instead of by eye.
MONO_ADVANCE = 0.6


def build_hero(t: Theme) -> None:
    W, H = 1000, 296
    size, base = 50, 150
    caret_x = 50 + len(NAME) * size * MONO_ADVANCE + 20

    o: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" role="img" '
        f'aria-label="Kelson Qu. Role: backend and distributed systems. Focus: '
        f"agentic AI and cloud infrastructure. Education: M.S. Computer Science, "
        f'Northeastern. Location: Fremont, CA.">',
        "<title>Kelson Qu</title>",
        *panel(t, W, H),
        f'<text x="52" y="76" font-family="{MONO}" font-size="10.5" '
        f'fill="{t.faint}" letter-spacing="3.4">GITHUB.COM / KAICHENQU</text>',
        # name set in mono caps: the default move here is a huge grotesk, and
        # mono commits to the instrument language the rest of the panel speaks
        f'<text x="50" y="{base}" font-family="{MONO}" font-size="{size}" '
        f'font-weight="700" fill="{t.text}">{NAME}</text>',
        f'<rect class="caret" x="{caret_x:.0f}" y="{base - 37}" width="22" '
        f'height="39" fill="{t.accent}"/>',
        f'<rect x="50" y="170" width="86" height="2" fill="{t.accent}"/>',
        f'<text x="50" y="198" font-family="{MONO}" font-size="12" '
        f'fill="{t.faint}" letter-spacing="0.4">'
        f"Ship fast. Scale further. Break nothing.</text>",
    ]

    bx, bw, rowh, y0 = 520, 430, 30, 56
    lx = bx + 84
    o.append(
        f'<path d="M{bx} {y0}V{y0 + len(TITLE_BLOCK) * rowh}'
        f'M{lx} {y0}V{y0 + len(TITLE_BLOCK) * rowh}" stroke="{t.rule}"/>'
    )
    for n, (label, value) in enumerate(TITLE_BLOCK):
        top = y0 + n * rowh
        o.append(
            f'<line x1="{bx}" y1="{top}" x2="{bx + bw}" y2="{top}" '
            f'stroke="{t.rule}"/>'
            f'<text x="{bx + 12}" y="{top + 19}" font-family="{MONO}" '
            f'font-size="9.5" fill="{t.accent_d}" letter-spacing="1.4">{label}</text>'
            f'<text x="{lx + 12}" y="{top + 19}" font-family="{MONO}" '
            f'font-size="11" fill="{t.muted}">{esc(value)}</text>'
        )
    bottom = y0 + len(TITLE_BLOCK) * rowh
    o.append(
        f'<line x1="{bx}" y1="{bottom}" x2="{bx + bw}" y2="{bottom}" '
        f'stroke="{t.rule}"/>'
    )
    o.append(f'<line x1="50" y1="220" x2="{W - 50}" y2="220" stroke="{t.rule}"/>')

    # scale bar along the bottom edge, with a slow amber index travelling it
    ty, x0, x1 = 250, 50, W - 50
    for x in range(x0, x1 + 1, 12):
        o.append(
            f'<path d="M{x} {ty}v{7 if (x - x0) % 60 == 0 else 4}" stroke="{t.rule}"/>'
        )
    o.append(f'<line x1="{x0}" y1="{ty}" x2="{x1}" y2="{ty}" stroke="{t.rule}"/>')
    o.append(
        f'<g class="sweep"><path d="M{x0} {ty - 6}v18" stroke="{t.accent}" '
        f'stroke-width="1.5"/></g>'
    )
    o.append(
        "<style>"
        # step-end, not eased: a caret is a hard blink, and easing it is a tell
        "@keyframes caret{0%,49%{opacity:1}50%,100%{opacity:0}}"
        f"@keyframes sweep{{0%{{transform:translateX(0)}}"
        f"100%{{transform:translateX({x1 - x0}px)}}}}"
        ".caret{animation:caret 1.1s step-end infinite}"
        ".sweep{animation:sweep 9s linear infinite}"
        "@media (prefers-reduced-motion:reduce){"
        ".caret,.sweep{animation:none}.sweep{opacity:0}}"
        "</style></svg>"
    )
    write(t, "hero", "".join(o))
    if t is DARK:
        print("  hero")


# ── stack ─────────────────────────────────────────────────────────────────────
def build_stack(t: Theme) -> None:
    ROW_H, ICON = 86, 24
    PAD_X, PAD_T = 34, 116
    W = 1000
    H = PAD_T + len(STACK) * ROW_H + 20
    total = sum(len(i) for _, i in STACK)

    o: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" role="img" aria-label="Toolchain: '
        + esc(
            "; ".join(
                f"{cat} - " + ", ".join(n for n, _, _ in items) for cat, items in STACK
            )
        )
        + '">',
        "<title>Toolchain</title>",
        *panel(t, W, H),
        *heading(t, PAD_X, 46, "Toolchain", "WHAT I REACH FOR"),
        f'<text x="{W - PAD_X}" y="50" text-anchor="end" font-family="{MONO}" '
        f'font-size="33" font-weight="700" fill="{t.accent}">{total}</text>',
        f'<text x="{W - PAD_X}" y="70" text-anchor="end" font-family="{MONO}" '
        f'font-size="10" fill="{t.faint}" letter-spacing="2">'
        f"TOOLS / {len(STACK)} GROUPS</text>",
        f'<line x1="{PAD_X}" y1="88" x2="{W - PAD_X}" y2="88" stroke="{t.rule}"/>',
    ]

    for ri, (cat, items) in enumerate(STACK):
        top = PAD_T + ri * ROW_H
        if ri:
            o.append(
                f'<line x1="{PAD_X}" y1="{top - 20}" x2="{W - PAD_X}" '
                f'y2="{top - 20}" stroke="{t.rule_f}"/>'
            )
        o.append(
            f'<text x="{PAD_X}" y="{top + 14}" font-family="{MONO}" font-size="10" '
            f'fill="{t.accent_d}">{ri + 1:02d}</text>'
            f'<text x="{PAD_X + 26}" y="{top + 14}" font-family="{MONO}" '
            f'font-size="11" fill="{t.muted}" letter-spacing="2">'
            f"{esc(cat.upper())}</text>"
        )

        x = PAD_X
        for name, slug, brand in items:
            paths, vw, vh = icon_paths(slug)

            # fit the glyph to ICON height; wide marks (the AWS wordmark) keep
            # their aspect and simply claim a wider slot in the chip
            s = ICON / vh
            iw = min(vw * s, ICON * 2.6)
            s = min(s, iw / vw)

            wchip = 20 + iw + 9 + 8 * len(name) + 12
            ix, iy = x + 11, top + 45 - (vh * s) / 2
            o.append(
                f'<rect x="{x}" y="{top + 28}" width="{wchip:.0f}" height="34" '
                f'rx="3" fill="{t.chip}" stroke="{t.rule}"/>'
                f'<g transform="translate({ix:.1f},{iy:.1f}) scale({s:.4f})" '
                f'fill="{legible(brand, t.bg_lum, t.icon_contrast)}">'
                + "".join(f'<path d="{d}"/>' for d in paths)
                + "</g>"
                f'<text x="{ix + iw + 9:.1f}" y="{top + 50}" font-family="{MONO}" '
                f'font-size="12" fill="{t.text}">{esc(name)}</text>'
            )
            x += wchip + 8
    o.append("</svg>")
    write(t, "stack", "".join(o))
    if t is DARK:
        print(f"  stack              {total} tools")


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    print("building assets/ (light + dark)")
    cal = calendar()
    for t in (DARK, LIGHT):
        build_hero(t)
        build_stack(t)
        build_contributions(t, cal)


if __name__ == "__main__":
    main()
