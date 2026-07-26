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
BG0, BG1, BG2 = "#0B0817", "#151030", "#0D0A1C"
SURFACE = "#120F24"
STROKE = "#2A2148"
TEXT = "#EDEAF7"
MUTED = "#A29CC0"
FAINT = "#6F6890"
VIOLET = "#A78BFA"
CYAN = "#22D3EE"
PINK = "#F472B6"

# contribution intensity ramp, level 0..4
LEVELS = ["#181430", "#3B2A73", "#6541C4", "#9A6DFF", "#C9A6FF"]

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
    only AWS asset is a wide wordmark — hence the caller scales by viewBox
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
# their official values here).
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

    CELL, GAP = 13, 3
    STEP = CELL + GAP
    PAD_L, PAD_T = 118, 106
    W = PAD_L + len(weeks) * STEP + 30
    H = PAD_T + 7 * STEP + 96

    o: list[str] = []
    o.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" role="img" '
        f'aria-label="GitHub contribution calendar: {total} contributions in the last year">'
    )
    o.append(f"<title>{total} contributions in the last year</title>")
    o.append(defs_backdrop())
    o.append(f'<rect width="{W}" height="{H}" rx="18" fill="url(#bg)"/>')
    o.append(
        f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="18" fill="none" stroke="{STROKE}"/>'
    )
    o.append(f'<circle cx="{W * 0.16:.0f}" cy="34" r="190" fill="url(#glowV)"/>')
    o.append(f'<circle cx="{W * 0.88:.0f}" cy="{H - 20}" r="170" fill="url(#glowC)"/>')

    o.append(
        f'<text x="34" y="46" font-family="{SANS}" font-size="21" font-weight="600" fill="{TEXT}">'
        f"Contribution calendar</text>"
    )
    o.append(
        f'<text x="34" y="70" font-family="{MONO}" font-size="13" fill="{FAINT}" letter-spacing="1.4">'
        f"{days[0]['date']} &#8594; {days[-1]['date']}</text>"
    )
    o.append(
        f'<text x="{W - 34}" y="52" text-anchor="end" font-family="{SANS}" font-size="34" '
        f'font-weight="700" fill="{VIOLET}">{total}</text>'
    )
    o.append(
        f'<text x="{W - 34}" y="72" text-anchor="end" font-family="{MONO}" font-size="11" '
        f'fill="{FAINT}" letter-spacing="1.6">CONTRIBUTIONS</text>'
    )

    # weekday gutter
    for wd, name in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        y = PAD_T + wd * STEP + CELL - 2
        o.append(
            f'<text x="{PAD_L - 12}" y="{y}" text-anchor="end" font-family="{MONO}" '
            f'font-size="11" fill="{FAINT}">{name}</text>'
        )

    # month ruler. The window starts mid-month, so week 0 and week 1 can both be
    # "first week of a month" — hold a minimum gap or the two labels collide.
    seen: set[str] = set()
    last_x = -999.0
    for wi, w in enumerate(weeks):
        m = date.fromisoformat(w["firstDay"]).strftime("%b")
        x = PAD_L + wi * STEP
        if m not in seen and wi < len(weeks) - 1 and x - last_x >= 42:
            seen.add(m)
            last_x = x
            o.append(
                f'<text x="{x}" y="{PAD_T - 14}" font-family="{MONO}" '
                f'font-size="11" fill="{FAINT}">{m}</text>'
            )

    # cells
    i = 0
    for wi, w in enumerate(weeks):
        for d in w["contributionDays"]:
            lv = (
                level_of(d["contributionCount"], thresholds)
                if d["contributionCount"]
                else 0
            )
            x = PAD_L + wi * STEP
            y = PAD_T + d["weekday"] * STEP
            extra = ""
            if lv >= 3:
                # stagger the shimmer so it reads as a field, not a pulse
                extra = f' class="hot" style="animation-delay:{(i % 17) * 0.19:.2f}s"'
            o.append(
                f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="3.5" '
                f'fill="{LEVELS[lv]}"{extra}><title>{d["date"]}: '
                f"{d['contributionCount']}</title></rect>"
            )
            i += 1

    # legend
    ly = PAD_T + 7 * STEP + 30
    o.append(
        f'<text x="{PAD_L}" y="{ly + 11}" font-family="{MONO}" font-size="11" fill="{FAINT}">Less</text>'
    )
    # Spell the band each tone stands for; a bare Less→More ramp says nothing
    # about whether a lit cell means one commit or eighteen.
    bands = ["0"]
    for n in range(1, 4):
        lo, hi = thresholds[n - 1] + 1, thresholds[n]
        bands.append(str(lo) if lo >= hi else f"{lo}–{hi}")
    bands.append(f"{thresholds[3] + 1}+")

    # wide enough for the band labels to sit under each swatch without touching
    LSTEP = 40
    for n, c in enumerate(LEVELS):
        cx = PAD_L + 42 + n * LSTEP
        o.append(
            f'<rect x="{cx}" y="{ly}" width="{CELL}" height="{CELL}" rx="3.5" fill="{c}"/>'
        )
        o.append(
            f'<text x="{cx + CELL / 2}" y="{ly + 26}" text-anchor="middle" '
            f'font-family="{MONO}" font-size="8.5" fill="{FAINT}">{bands[n]}</text>'
        )
    o.append(
        f'<text x="{PAD_L + 42 + 4 * LSTEP + CELL + 12}" y="{ly + 11}" font-family="{MONO}" font-size="11" '
        f'fill="{FAINT}">More</text>'
    )

    # stat strip
    stats = [
        ("ACTIVE DAYS", str(active)),
        ("LONGEST STREAK", f"{longest}d"),
        ("BUSIEST DAY", f"{busiest['contributionCount']}"),
    ]
    sx = W - 34
    for label, value in reversed(stats):
        o.append(
            f'<text x="{sx}" y="{ly + 4}" text-anchor="end" font-family="{SANS}" font-size="16" '
            f'font-weight="600" fill="{TEXT}">{value}</text>'
        )
        o.append(
            f'<text x="{sx}" y="{ly + 20}" text-anchor="end" font-family="{MONO}" font-size="9.5" '
            f'fill="{FAINT}" letter-spacing="1.2">{label}</text>'
        )
        sx -= 132

    o.append(
        "<style>@keyframes bloom{0%,100%{opacity:.82}50%{opacity:1}}"
        ".hot{animation:bloom 4.6s ease-in-out infinite}"
        "@media (prefers-reduced-motion:reduce){.hot{animation:none;opacity:1}}</style>"
    )
    o.append("</svg>")
    (ASSETS / "contributions.svg").write_text("".join(o))
    print(
        f"  contributions.svg  {total} contributions · {active} active days · longest {longest}d"
    )


def defs_backdrop() -> str:
    return (
        "<defs>"
        f'<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{BG0}"/><stop offset="0.5" stop-color="{BG1}"/>'
        f'<stop offset="1" stop-color="{BG2}"/></linearGradient>'
        f'<radialGradient id="glowV"><stop offset="0" stop-color="{VIOLET}" stop-opacity="0.20"/>'
        '<stop offset="1" stop-color="#000" stop-opacity="0"/></radialGradient>'
        f'<radialGradient id="glowC"><stop offset="0" stop-color="{CYAN}" stop-opacity="0.15"/>'
        '<stop offset="1" stop-color="#000" stop-opacity="0"/></radialGradient>'
        f'<radialGradient id="glowP"><stop offset="0" stop-color="{PINK}" stop-opacity="0.13"/>'
        '<stop offset="1" stop-color="#000" stop-opacity="0"/></radialGradient>'
        '<pattern id="grid" width="26" height="26" patternUnits="userSpaceOnUse">'
        f'<path d="M26 0H0V26" fill="none" stroke="{VIOLET}" stroke-opacity="0.055"/></pattern>'
        "</defs>"
    )


# ── hero ──────────────────────────────────────────────────────────────────────
def build_hero() -> None:
    W, H = 1000, 280
    o: list[str] = []
    o.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" role="img" '
        f'aria-label="Kelson Qu — backend, distributed systems, agentic AI">'
    )
    o.append("<title>Kelson Qu</title>")
    o.append(defs_backdrop())
    o.append(f'<rect width="{W}" height="{H}" rx="18" fill="url(#bg)"/>')
    o.append(f'<rect width="{W}" height="{H}" rx="18" fill="url(#grid)"/>')

    o.append(
        '<g class="drift"><circle cx="150" cy="60" r="260" fill="url(#glowV)"/></g>'
    )
    o.append(
        '<g class="drift2"><circle cx="880" cy="230" r="240" fill="url(#glowC)"/></g>'
    )
    o.append(
        '<g class="drift3"><circle cx="620" cy="30" r="200" fill="url(#glowP)"/></g>'
    )

    # constellation — nodes and edges, a quiet nod to distributed systems
    nodes = [
        (742, 96),
        (812, 62),
        (884, 104),
        (858, 178),
        (776, 186),
        (700, 150),
        (930, 152),
        (820, 126),
    ]
    edges = [
        (0, 1),
        (1, 2),
        (2, 3),
        (3, 4),
        (4, 5),
        (5, 0),
        (7, 0),
        (7, 2),
        (7, 3),
        (7, 4),
        (2, 6),
        (6, 3),
    ]
    for a, b in edges:
        x1, y1 = nodes[a]
        x2, y2 = nodes[b]
        o.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{VIOLET}" '
            f'stroke-opacity="0.42" stroke-width="1.1"/>'
        )
    for n, (x, y) in enumerate(nodes):
        r = 5.5 if n == 7 else 3.6
        fill = CYAN if n == 7 else VIOLET
        o.append(
            f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}" class="pulse" '
            f'style="animation-delay:{n * 0.42:.2f}s"/>'
        )

    o.append(
        f'<text x="64" y="86" font-family="{MONO}" font-size="12.5" fill="{CYAN}" '
        f'letter-spacing="4.2">SOFTWARE&#160;ENGINEER</text>'
    )
    o.append(
        f'<text x="62" y="156" font-family="{SANS}" font-size="62" font-weight="700" '
        f'fill="{TEXT}" letter-spacing="-1.6">Kelson Qu</text>'
    )
    o.append('<rect x="64" y="180" width="54" height="3" rx="1.5" fill="url(#rule)"/>')
    o.append(
        '<defs><linearGradient id="rule" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0" stop-color="{VIOLET}"/><stop offset="1" stop-color="{CYAN}"/>'
        "</linearGradient></defs>"
    )
    o.append(
        f'<text x="64" y="214" font-family="{SANS}" font-size="18" fill="{MUTED}">'
        f"Distributed systems &#183; Agentic AI &#183; Cloud infrastructure</text>"
    )
    o.append(
        f'<text x="64" y="242" font-family="{MONO}" font-size="12.5" fill="{FAINT}" '
        f'letter-spacing="0.6">M.S. Computer Science, Northeastern &#183; Fremont, CA</text>'
    )

    o.append(
        "<style>"
        "@keyframes drift{0%,100%{transform:translate(0,0)}50%{transform:translate(34px,18px)}}"
        "@keyframes drift2{0%,100%{transform:translate(0,0)}50%{transform:translate(-30px,-16px)}}"
        "@keyframes drift3{0%,100%{transform:translate(0,0)}50%{transform:translate(18px,26px)}}"
        "@keyframes pulse{0%,100%{opacity:.45}50%{opacity:1}}"
        ".drift{animation:drift 15s ease-in-out infinite}"
        ".drift2{animation:drift2 19s ease-in-out infinite}"
        ".drift3{animation:drift3 23s ease-in-out infinite}"
        ".pulse{animation:pulse 3.4s ease-in-out infinite}"
        "@media (prefers-reduced-motion:reduce){"
        ".drift,.drift2,.drift3,.pulse{animation:none}}"
        "</style>"
    )
    o.append("</svg>")
    (ASSETS / "hero.svg").write_text("".join(o))
    print("  hero.svg")


# ── stack ─────────────────────────────────────────────────────────────────────
def build_stack() -> None:
    ROW_H, ICON = 92, 26
    PAD_X, PAD_T = 34, 92
    W = 1000
    H = PAD_T + len(STACK) * ROW_H + 22

    o: list[str] = []
    o.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" role="img" aria-label="Toolchain: '
        + esc(
            "; ".join(
                f"{cat} — " + ", ".join(n for n, _, _ in items) for cat, items in STACK
            )
        )
        + '">'
    )
    o.append("<title>Toolchain</title>")
    o.append(defs_backdrop())
    o.append(f'<rect width="{W}" height="{H}" rx="18" fill="url(#bg)"/>')
    o.append(f'<rect width="{W}" height="{H}" rx="18" fill="url(#grid)"/>')
    o.append(
        f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="18" fill="none" stroke="{STROKE}"/>'
    )
    o.append('<circle cx="90" cy="20" r="230" fill="url(#glowV)"/>')
    o.append(f'<circle cx="{W - 70}" cy="{H - 30}" r="230" fill="url(#glowC)"/>')

    o.append(
        f'<text x="{PAD_X}" y="48" font-family="{SANS}" font-size="21" font-weight="600" '
        f'fill="{TEXT}">Toolchain</text>'
    )
    o.append(
        f'<text x="{PAD_X}" y="70" font-family="{MONO}" font-size="12" fill="{FAINT}" '
        f'letter-spacing="1.4">WHAT I REACH FOR</text>'
    )

    cache: dict[str, list[str]] = {}
    for ri, (cat, items) in enumerate(STACK):
        top = PAD_T + ri * ROW_H
        if ri:
            o.append(
                f'<line x1="{PAD_X}" y1="{top - 16}" x2="{W - PAD_X}" y2="{top - 16}" '
                f'stroke="{STROKE}" stroke-opacity="0.6"/>'
            )
        o.append(
            f'<text x="{PAD_X}" y="{top + 18}" font-family="{MONO}" font-size="12" '
            f'fill="{VIOLET}" letter-spacing="2.2">{esc(cat.upper())}</text>'
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

            wchip = 22 + iw + 9 + 8 * len(name) + 12
            o.append(
                f'<g class="chip"><rect x="{x}" y="{top + 30}" width="{wchip:.0f}" height="38" '
                f'rx="10" fill="{SURFACE}" fill-opacity="0.72" stroke="{STROKE}"/>'
            )
            ix, iy = x + 12, top + 49 - (vh * s) / 2
            o.append(
                f'<g transform="translate({ix:.1f},{iy:.1f}) scale({s:.4f})" fill="{tint}">'
            )
            for d in paths:
                o.append(f'<path d="{d}"/>')
            o.append("</g>")
            o.append(
                f'<text x="{ix + iw + 9:.1f}" y="{top + 54}" font-family="{SANS}" '
                f'font-size="13.5" fill="{TEXT}" fill-opacity="0.92">{esc(name)}</text></g>'
            )
            x += wchip + 10
    o.append("</svg>")
    (ASSETS / "stack.svg").write_text("".join(o))
    print(f"  stack.svg          {sum(len(i) for _, i in STACK)} tools")


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    print("building assets/")
    build_hero()
    build_stack()
    build_contributions()


if __name__ == "__main__":
    main()
