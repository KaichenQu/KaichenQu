#!/usr/bin/env python3
"""Regenerate the profile README's SVG assets.

Everything the profile shows is drawn here, so the page has no dependency on
third-party card services (which go down: github-readme-stats has been
returning 503 DEPLOYMENT_PAUSED and github-profile-trophy 402 for months).

    python3 scripts/build_assets.py

Requires the `gh` CLI, authenticated. Writes into assets/.

Caveat on the calendar: contributionsCollection returns only PUBLIC
contributions unless "Include private contributions on my profile" is
enabled in GitHub profile settings. With it off, commits to private repos
(e.g. the longrangeorder org) are absent from the response entirely --
restrictedContributionsCount stays 0, so nothing signals the gap. Verified
2026-07-26: 42 commits authored on longrangeorder default branches, all
correctly attributed to the account, none present in the collection. Turn
the setting on before re-running if those should be counted.

Visual language: flat ink, hairline rules, graph-paper grid, corner register
marks, one amber signal colour, monospace-led type. Deliberately no radial
gradient blooms, no violet-to-cyan wash and no abstract node constellation --
that trio is the house style of machine-generated "tech" pages and reads as
such instantly.
"""

from __future__ import annotations

import json
import re
import subprocess
import urllib.request
from datetime import date
from pathlib import Path

USER = "KaichenQu"
ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

# ── palette ───────────────────────────────────────────────────────────────────
# Neutral near-black, not a tinted one. A violet or blue cast on the background
# is most of what makes the AI-generated look read as AI-generated.
INK = "#0A0A0C"
CHIP = "#131317"
RULE = "#26262E"  # visible hairline
RULE_F = "#17171C"  # graph-paper hairline
TEXT = "#E8E8EA"
MUTED = "#8A8A93"
FAINT = "#57575F"
AMBER = "#FFB224"  # the single signal colour — instrument amber
AMBER_D = "#8A5E12"

# contribution intensity ramp, level 0..4 — a thermal read-out, not a gradient
LEVELS = ["#141418", "#4A3411", "#8A5E14", "#C78C1A", "#FFB224"]

MONO = (
    "ui-monospace,'SFMono-Regular','SF Mono',Menlo,Consolas,'Liberation Mono',monospace"
)
SANS = "system-ui,-apple-system,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif"

SI = "https://cdn.jsdelivr.net/npm/simple-icons@15/icons/{}.svg"
DEVICON = (
    "https://cdn.jsdelivr.net/gh/devicons/devicon@master/icons/{0}/{0}-original.svg"
)
DEVICON_WORDMARK = "https://cdn.jsdelivr.net/gh/devicons/devicon@master/icons/{0}/{0}-original-wordmark.svg"


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


# ── icon sourcing ─────────────────────────────────────────────────────────────
def icon_paths(slug: str) -> tuple[list[str], float, float]:
    """Return an icon's path `d` strings plus its source viewBox width/height.

    simple-icons is the preferred source (square 24x24, single path). AWS is not
    in simple-icons for trademark reasons, so it falls back to devicon, whose
    only AWS asset is a wide wordmark -- hence the caller scales by viewBox
    rather than assuming 24x24.
    """
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
    return re.findall(r'\sd="([^"]+)"', svg), vw, vh


# label, simple-icons slug, tint. Tints are brand colours nudged for legibility
# on a near-black surface (Django, Kafka, Next.js and Express are unreadable at
# their official values here). The icons keep their brand colour on purpose:
# they are the content, and only the chrome around them goes monochrome.
STACK = [
    (
        "Languages",
        [
            ("Java", "openjdk", "#E76F00"),
            ("Python", "python", "#4B8BBE"),
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
            ("Django", "django", "#44B78B"),
            ("Express", "express", "#D8D4EA"),
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
            ("Kafka", "apachekafka", "#D8D4EA"),
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
            ("Next.js", "nextdotjs", "#D8D4EA"),
            ("Tailwind", "tailwindcss", "#06B6D4"),
            ("Redux", "redux", "#764ABC"),
            ("Vite", "vite", "#646CFF"),
        ],
    ),
    (
        "AI",
        [
            ("Anthropic", "anthropic", "#D97757"),
            ("OpenAI", "openai", "#D8D4EA"),
            ("LangChain", "langchain", "#61C9A8"),
        ],
    ),
]


# ── shared panel chrome ───────────────────────────────────────────────────────
def defs() -> str:
    """Graph-paper grid: a fine 10px module with a heavier line every 50px."""
    return (
        "<defs>"
        '<pattern id="fine" width="10" height="10" patternUnits="userSpaceOnUse">'
        f'<path d="M10 0H0V10" fill="none" stroke="{RULE_F}" stroke-width="0.5"/>'
        "</pattern>"
        '<pattern id="coarse" width="50" height="50" patternUnits="userSpaceOnUse">'
        '<rect width="50" height="50" fill="url(#fine)"/>'
        f'<path d="M50 0H0V50" fill="none" stroke="{RULE_F}" stroke-width="1"/>'
        "</pattern>"
        "</defs>"
    )


def register_marks(w: float, h: float, inset: float = 16, arm: float = 7) -> list[str]:
    """Corner crosshairs, as on a technical drawing or a print registration."""
    out = []
    for cx, cy in (
        (inset, inset),
        (w - inset, inset),
        (inset, h - inset),
        (w - inset, h - inset),
    ):
        out.append(
            f'<path d="M{cx - arm} {cy}H{cx + arm}M{cx} {cy - arm}V{cy + arm}" '
            f'stroke="{RULE}" stroke-width="1"/>'
        )
    return out


def panel(w: float, h: float) -> list[str]:
    """Flat surface + graph paper + hairline border + register marks."""
    return [
        defs(),
        f'<rect width="{w}" height="{h}" rx="6" fill="{INK}"/>',
        f'<rect width="{w}" height="{h}" rx="6" fill="url(#coarse)"/>',
        f'<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="6" '
        f'fill="none" stroke="{RULE}"/>',
        *register_marks(w, h),
    ]


def heading(x: float, y: float, title: str, kicker: str) -> list[str]:
    """Panel title with a mono kicker and a short amber rule beneath it."""
    return [
        f'<text x="{x}" y="{y}" font-family="{MONO}" font-size="11" fill="{AMBER}" '
        f'letter-spacing="3">{esc(kicker)}</text>',
        f'<text x="{x}" y="{y + 26}" font-family="{SANS}" font-size="19" '
        f'font-weight="600" fill="{TEXT}">{esc(title)}</text>',
    ]


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
    for i, t in enumerate(thresholds):
        if count <= t:
            return i
    return 4


def longest_streak(days: list[dict]) -> int:
    """Longest run of consecutive days with at least one contribution."""
    longest = run = 0
    for d in days:
        run = run + 1 if d["contributionCount"] > 0 else 0
        longest = max(longest, run)
    return longest


def build_contributions() -> None:
    cal = calendar()
    weeks = cal["weeks"]
    days = [d for w in weeks for d in w["contributionDays"]]
    total = cal["totalContributions"]

    # Quantiles over every active DAY, not over the distinct counts. Ranking
    # distinct values instead buries the shape of a bursty year: with 43 active
    # days spread over only 14 distinct counts, it pushed 33 of them into the
    # dimmest band and left one day alone at the top.
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
        *panel(W, H),
        *heading(34, 46, "Contribution calendar", "COMMIT LOG"),
    ]

    o.append(
        f'<text x="{W - 34}" y="50" text-anchor="end" font-family="{MONO}" '
        f'font-size="33" font-weight="700" fill="{AMBER}">{total}</text>'
    )
    o.append(
        f'<text x="{W - 34}" y="70" text-anchor="end" font-family="{MONO}" '
        f'font-size="10" fill="{FAINT}" letter-spacing="2">'
        f"{days[0]['date']} / {days[-1]['date']}</text>"
    )
    o.append(f'<line x1="34" y1="88" x2="{W - 34}" y2="88" stroke="{RULE}"/>')

    # weekday gutter
    for wd, name in ((1, "MON"), (3, "WED"), (5, "FRI")):
        y = PAD_T + wd * STEP + CELL - 2
        o.append(
            f'<text x="{PAD_L - 14}" y="{y}" text-anchor="end" font-family="{MONO}" '
            f'font-size="9.5" fill="{FAINT}" letter-spacing="1">{name}</text>'
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
                f'<path d="M{x} {PAD_T - 12}v5" stroke="{RULE}"/>'
                f'<text x="{x}" y="{PAD_T - 18}" font-family="{MONO}" '
                f'font-size="9.5" fill="{FAINT}" letter-spacing="1">{m}</text>'
            )

    # cells — square, hard-edged, no glow
    for wi, w in enumerate(weeks):
        for d in w["contributionDays"]:
            lv = (
                level_of(d["contributionCount"], thresholds)
                if d["contributionCount"]
                else 0
            )
            x = PAD_L + wi * STEP
            y = PAD_T + d["weekday"] * STEP
            o.append(
                f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="1.5" '
                f'fill="{LEVELS[lv]}"><title>{d["date"]} &#183; '
                f"{d['contributionCount']}</title></rect>"
            )

    # legend, with the band each tone stands for. A bare Less-to-More ramp says
    # nothing about whether a lit cell means one commit or eighteen.
    ly = PAD_T + 7 * STEP + 28
    bands = ["0"]
    for n in range(1, 4):
        lo, hi = thresholds[n - 1] + 1, thresholds[n]
        bands.append(str(lo) if lo >= hi else f"{lo}-{hi}")
    bands.append(f"{thresholds[3] + 1}+")

    LSTEP = 42
    for n, c in enumerate(LEVELS):
        cx = PAD_L + n * LSTEP
        o.append(
            f'<rect x="{cx}" y="{ly}" width="{CELL}" height="{CELL}" rx="1.5" fill="{c}"/>'
        )
        o.append(
            f'<text x="{cx + CELL / 2}" y="{ly + 25}" text-anchor="middle" '
            f'font-family="{MONO}" font-size="9" fill="{FAINT}">{bands[n]}</text>'
        )
    o.append(
        f'<text x="{PAD_L - 14}" y="{ly + 10}" text-anchor="end" font-family="{MONO}" '
        f'font-size="9.5" fill="{FAINT}" letter-spacing="1">PER DAY</text>'
    )

    # read-out strip
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
            f'font-size="17" font-weight="700" fill="{TEXT}">{value}</text>'
        )
        o.append(
            f'<text x="{sx}" y="{ly + 20}" text-anchor="end" font-family="{MONO}" '
            f'font-size="9" fill="{FAINT}" letter-spacing="1.4">{label}</text>'
        )
        sx -= 128

    o.append("</svg>")
    (ASSETS / "contributions.svg").write_text("".join(o))
    print(f"  contributions.svg  {total} contributions · {active} active days")


# ── hero ──────────────────────────────────────────────────────────────────────
# A drawing title block: label column, value column, hairline ruled. Every row
# is a fact stated elsewhere in the profile -- nothing invented to fill the grid.
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


def build_hero() -> None:
    W, H = 1000, 296
    o: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" role="img" '
        f'aria-label="Kelson Qu — backend and distributed systems; agentic AI '
        f'and cloud infrastructure; M.S. Computer Science, Northeastern; '
        f'Fremont, California">',
        "<title>Kelson Qu</title>",
        *panel(W, H),
    ]

    o.append(
        f'<text x="52" y="76" font-family="{MONO}" font-size="10.5" fill="{FAINT}" '
        f'letter-spacing="3.4">GITHUB.COM / KAICHENQU</text>'
    )

    # name set in mono caps: the default move here is a huge grotesk, and the
    # mono is what commits to the instrument language the rest of the panel speaks
    size, base = 50, 150
    o.append(
        f'<text x="50" y="{base}" font-family="{MONO}" font-size="{size}" '
        f'font-weight="700" fill="{TEXT}">{NAME}</text>'
    )
    caret_x = 50 + len(NAME) * size * MONO_ADVANCE + 20
    o.append(
        f'<rect class="caret" x="{caret_x:.0f}" y="{base - 38}" width="26" '
        f'height="40" fill="{AMBER}"/>'
    )
    o.append(f'<rect x="50" y="170" width="86" height="2" fill="{AMBER}"/>')
    o.append(
        f'<text x="50" y="198" font-family="{MONO}" font-size="12" fill="{FAINT}" '
        f'letter-spacing="0.4">Ship fast. Scale further. Break nothing.</text>'
    )

    # title block, ruled, right column
    bx, bw, rowh, y0 = 520, 430, 30, 56
    lx = bx + 84
    o.append(
        f'<path d="M{bx} {y0}V{y0 + len(TITLE_BLOCK) * rowh}M{lx} {y0}'
        f'V{y0 + len(TITLE_BLOCK) * rowh}" stroke="{RULE}"/>'
    )
    for n, (label, value) in enumerate(TITLE_BLOCK):
        top = y0 + n * rowh
        o.append(f'<line x1="{bx}" y1="{top}" x2="{bx + bw}" y2="{top}" stroke="{RULE}"/>')
        o.append(
            f'<text x="{bx + 12}" y="{top + 19}" font-family="{MONO}" font-size="9.5" '
            f'fill="{AMBER_D}" letter-spacing="1.4">{label}</text>'
        )
        o.append(
            f'<text x="{lx + 12}" y="{top + 19}" font-family="{MONO}" font-size="11" '
            f'fill="{MUTED}">{esc(value)}</text>'
        )
    bottom = y0 + len(TITLE_BLOCK) * rowh
    o.append(f'<line x1="{bx}" y1="{bottom}" x2="{bx + bw}" y2="{bottom}" stroke="{RULE}"/>')

    o.append(f'<line x1="50" y1="220" x2="{W - 50}" y2="220" stroke="{RULE}"/>')

    # scale bar along the bottom edge, with a slow amber index travelling it
    ty, t0, t1 = 250, 50, W - 50
    for x in range(t0, t1 + 1, 12):
        tall = (x - t0) % 60 == 0
        o.append(f'<path d="M{x} {ty}v{7 if tall else 4}" stroke="{RULE}"/>')
    o.append(f'<line x1="{t0}" y1="{ty}" x2="{t1}" y2="{ty}" stroke="{RULE}"/>')
    o.append(
        f'<g class="sweep"><path d="M{t0} {ty - 6}v18" stroke="{AMBER}" '
        f'stroke-width="1.5"/></g>'
    )

    o.append(
        "<style>"
        # step-end, not eased: a caret is a hard blink, and easing it is a tell
        "@keyframes caret{0%,49%{opacity:1}50%,100%{opacity:0}}"
        f"@keyframes sweep{{0%{{transform:translateX(0)}}"
        f"100%{{transform:translateX({t1 - t0}px)}}}}"
        ".caret{animation:caret 1.1s step-end infinite}"
        ".sweep{animation:sweep 9s linear infinite}"
        "@media (prefers-reduced-motion:reduce){"
        ".caret,.sweep{animation:none}.sweep{opacity:0}}"
        "</style>"
    )
    o.append("</svg>")
    (ASSETS / "hero.svg").write_text("".join(o))
    print("  hero.svg")


# ── stack ─────────────────────────────────────────────────────────────────────
def build_stack() -> None:
    ROW_H, ICON = 86, 24
    PAD_X, PAD_T = 34, 116
    W = 1000
    H = PAD_T + len(STACK) * ROW_H + 20

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
        *panel(W, H),
        *heading(PAD_X, 46, "Toolchain", "WHAT I REACH FOR"),
    ]

    total = sum(len(i) for _, i in STACK)
    o.append(
        f'<text x="{W - PAD_X}" y="50" text-anchor="end" font-family="{MONO}" '
        f'font-size="33" font-weight="700" fill="{AMBER}">{total}</text>'
    )
    o.append(
        f'<text x="{W - PAD_X}" y="70" text-anchor="end" font-family="{MONO}" '
        f'font-size="10" fill="{FAINT}" letter-spacing="2">TOOLS / '
        f"{len(STACK)} GROUPS</text>"
    )
    o.append(f'<line x1="{PAD_X}" y1="88" x2="{W - PAD_X}" y2="88" stroke="{RULE}"/>')

    cache: dict[str, tuple[list[str], float, float]] = {}
    for ri, (cat, items) in enumerate(STACK):
        top = PAD_T + ri * ROW_H
        if ri:
            o.append(
                f'<line x1="{PAD_X}" y1="{top - 20}" x2="{W - PAD_X}" y2="{top - 20}" '
                f'stroke="{RULE_F}"/>'
            )
        o.append(
            f'<text x="{PAD_X}" y="{top + 14}" font-family="{MONO}" font-size="10" '
            f'fill="{AMBER_D}">{ri + 1:02d}</text>'
        )
        o.append(
            f'<text x="{PAD_X + 26}" y="{top + 14}" font-family="{MONO}" '
            f'font-size="11" fill="{MUTED}" letter-spacing="2">'
            f"{esc(cat.upper())}</text>"
        )

        x = PAD_X
        for name, slug, tint in items:
            if slug not in cache:
                cache[slug] = icon_paths(slug)
            paths, vw, vh = cache[slug]

            # fit the glyph to ICON height; wide marks (the AWS wordmark) keep
            # their aspect and simply claim a wider slot in the chip
            s = ICON / vh
            iw = min(vw * s, ICON * 2.6)
            s = min(s, iw / vw)

            wchip = 20 + iw + 9 + 8 * len(name) + 12
            o.append(
                f'<rect x="{x}" y="{top + 28}" width="{wchip:.0f}" height="34" rx="3" '
                f'fill="{CHIP}" stroke="{RULE}"/>'
            )
            ix, iy = x + 11, top + 45 - (vh * s) / 2
            o.append(
                f'<g transform="translate({ix:.1f},{iy:.1f}) scale({s:.4f})" fill="{tint}">'
            )
            for d in paths:
                o.append(f'<path d="{d}"/>')
            o.append("</g>")
            o.append(
                f'<text x="{ix + iw + 9:.1f}" y="{top + 50}" font-family="{MONO}" '
                f'font-size="12" fill="{TEXT}" fill-opacity="0.9">{esc(name)}</text>'
            )
            x += wchip + 8
    o.append("</svg>")
    (ASSETS / "stack.svg").write_text("".join(o))
    print(f"  stack.svg          {total} tools")


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    print("building assets/")
    build_hero()
    build_stack()
    build_contributions()


if __name__ == "__main__":
    main()
