"""
build_index.py: writes index.html, a one-page view of the research database.

Reads claims.json, sources.json, questions.md and REPORT.md. A claim's status
(verified or held) comes only from REPORT.md, so run `python3 verify.py`
first. Claims missing from REPORT.md are shown as held ("not checked yet").

Usage:
  python3 verify.py && python3 build_index.py
  python3 build_index.py --fragment <path>
      Also write the page without the <html>/<head>/<body> wrapper, for
      publishing as a claude.ai Artifact (which adds its own wrapper).

Python standard library only. Nothing in this file calls an AI model.
"""

import datetime
import html
import json
import re
import sys
from pathlib import Path

from verify import normalize

HERE = Path(__file__).parent
OUT = HERE / "index.html"

# Per-deal fields (questions 2-9) shown as columns in the deal table.
DEAL_FIELDS = [
    ("Total price", {2}),
    ("$/SF", {3, 4}),
    ("$/unit or key", {5}),
    ("Cap rate", {6}),
]

# Financing columns, filled from claims tagged with a "fin" field.
FIN_COLUMNS = [("Total loan", "loan"), ("Interest rate", "rate"), ("LTV", "ltv"),
               ("Appraised value", "appraised"), ("DSCR", "dscr")]


def fin_value(c):
    """Display text for one financing claim, with its qualifier (senior, mezzanine...)."""
    v, u = c["value"], c["unit"]
    if c["fin"] == "rate":
        dec = v.partition(".")[2]
        text = f"{float(v):.3f}%" if len(dec) > 4 else f"{v}%"
    elif c["fin"] == "ltv":
        text = f"{v}%"
    elif c["fin"] == "dscr":
        text = f"{v}x"
    else:
        text = money(v, u)
    return text + (f" ({c['fin_note']})" if c.get("fin_note") else "")


def load(name):
    path = HERE / name
    return json.loads(path.read_text(encoding="utf-8") or "[]") if path.exists() else []


def read_report():
    """claim_id -> (status, reason), parsed from the table in REPORT.md."""
    path = HERE / "REPORT.md"
    if not path.exists():
        return {}
    statuses = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| c"):
            continue
        cells = [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", line)[1:-1]]
        if len(cells) == 8:
            status = "verified" if cells[6] == "verified" else "held"
            statuses[cells[0]] = (status, cells[7])
    return statuses


def read_questions():
    """Returns (topic, [(section, [(number, text)])]) from questions.md."""
    text = (HERE / "questions.md").read_text(encoding="utf-8")
    topic = text.split("# Topic", 1)[-1].split("\n#", 1)[0].strip()
    topic = re.sub(r"\s+", " ", topic)
    body = text.split("# Questions", 1)[-1]
    sections, current = [], None
    for line in body.splitlines():
        if line.startswith("## "):
            current = (line[3:].strip(), [])
            sections.append(current)
        elif re.match(r"\d+\.\s", line):
            n, q = line.split(".", 1)
            if current is None:
                current = ("Questions", [])
                sections.append(current)
            current[1].append([int(n), q.strip()])
        elif line.strip() and current and current[1]:
            current[1][-1][1] += " " + line.strip()
    return topic, sections


def money(value, unit):
    u = unit.lower()
    asking = " asking" if "asking" in u else ""
    if u.startswith("million dollars"):
        return f"${value} million{asking}"
    if u.startswith("billion dollars"):
        return f"${value} billion"
    if u.startswith("thousand dollars per unit"):
        return f"${value}K / unit"
    if u.startswith("dollars per unit per month"):
        return f"${value} / unit / mo{asking}"
    if u.startswith("dollars per unit"):
        return f"${value} / unit"
    if u.startswith("dollars per key"):
        return f"${value} / key"
    if u.startswith("dollars per square foot"):
        return f"${value} / SF{asking}"
    if u.startswith("percent"):
        return f"{value}%"
    if u.startswith("times"):
        return f"{value}x"
    if u.startswith("dollars"):
        return f"${value}"
    return f"{value} {unit}"


def checks(claim):
    """Plain reasons a person should look again, even when verified."""
    notes = []
    nums = set(re.findall(r"\d[\d,]*(?:\.\d+)?", claim.get("quote", "")))
    nums.discard(claim.get("value", ""))
    if nums:
        notes.append(f"quote has {len(nums) + 1} numbers; confirm the right one was taken")
    if "basis not stated" in claim.get("unit", ""):
        notes.append("per-SF basis (gross or rentable) not stated")
    if "region" in claim.get("subject", "").lower() or "northern california" in claim.get("subject", "").lower():
        notes.append("covers a wider region than San Francisco")
    return notes


def deal_name(claim):
    """Deal claims use the subject convention '<property> - <field>'."""
    subject = claim.get("subject", "")
    if " - " in subject and set(claim.get("questions", [])) & set(range(1, 10)):
        return subject.split(" - ", 1)[0]
    return None


def party_info(cs):
    """Buyer/seller/lender/date for a deal, merged from its claims (first non-empty wins)."""
    info = {}
    for key in ("buyer", "seller", "lender", "date", "deal_note"):
        info[key] = next((c[key] for c in cs if c.get(key)), None)
    info["missing"] = "n/a (refinance)" if any(c.get("refinance") for c in cs) else "Not in free text"
    return info




def found_in_sources(name, cs, sources):
    """True if the name appears word for word in the text of any of the deal's sources."""
    for sid in {c["source_id"] for c in cs}:
        path = HERE / sources.get(sid, {}).get("capture", "")
        if path.is_file() and normalize(name) in normalize(path.read_text(encoding="utf-8")):
            return True
    return False


def names_html(names, cs, sources, missing="Not in free text"):
    if not names:
        return f'<span class="muted">{esc(missing)}</span>'
    out = []
    for n in names:
        ok = found_in_sources(n, cs, sources)
        mark = ('<span class="mark ok" title="Name appears word for word in the source text">✓</span>' if ok
                else '<span class="mark warn" title="Name not found in the source text">?</span>')
        out.append(f"{esc(n)} {mark}")
    return "<br>".join(out)


def esc(text):
    return html.escape(str(text))


def esc_md(text):
    """Escape, then show questions.md's **bold** as bold."""
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc(text))


def claim_card(c, sources):
    s = sources.get(c["source_id"], {})
    title, url = s.get("title", c["source_id"]), s.get("url", "")
    link = f'<a href="{esc(url)}">{esc(title)}</a>' if url else esc(title)
    notes = "".join(f'<li>{esc(n)}</li>' for n in checks(c))
    notes = f'<ul class="flags">{notes}</ul>' if notes else ""
    return f"""
<article class="claim">
  <div class="claim-head">
    <span class="value">{esc(money(c['value'], c['unit']))}</span>
    <span class="id">{esc(c['claim_id'])}</span>
  </div>
  <p class="subject">{esc(c['subject'])}</p>
  <p class="period">{esc(c['period'])}</p>
  <blockquote>{esc(c['quote'])}</blockquote>
  <p class="source">Source: {link}</p>
  {notes}
</article>"""


def main():
    claims = load("claims.json")
    sources = {s["id"]: s for s in load("sources.json")}
    report = read_report()
    topic, sections = read_questions()

    for c in claims:
        c["status"], c["reason"] = report.get(
            c["claim_id"], ("held", "not checked yet: run python3 verify.py"))
    verified = [c for c in claims if c["status"] == "verified"]
    held = [c for c in claims if c["status"] == "held"]

    parts = []

    # Per-deal questions (1-9): one table row and one block per deal.
    deals = {}
    for c in verified:
        name = deal_name(c)
        if name:
            deals.setdefault(name, []).append(c)
    def deal_date(cs):
        text = party_info(cs)["date"] or cs[0]["period"]
        m = re.search(r"([A-Z][a-z]+)\.? (\d{1,2}), (\d{4})", text)
        if not m:
            return datetime.datetime.min
        for fmt in ("%B %d %Y", "%b %d %Y"):
            try:
                return datetime.datetime.strptime(" ".join(m.groups()), fmt)
            except ValueError:
                pass
        return datetime.datetime.min

    def date_html(text, d):
        """Short date on top, with what the date means (reported, closed...) underneath."""
        if d == datetime.datetime.min:
            return esc(text)
        rest = re.sub(r"\s+", " ", re.sub(r"([A-Z][a-z]+)\.? (\d{1,2}), (\d{4})", "", text, count=1)).strip(" ;,")
        return f'<span class="d">{d:%b} {d.day}, {d.year}</span>' + (f'<span class="kind">{esc(rest)}</span>' if rest else "")

    def quarter(d):
        return f"Q{(d.month - 1) // 3 + 1} {d.year}" if d != datetime.datetime.min else "Date unknown"

    deals = dict(sorted(deals.items(), key=lambda kv: deal_date(kv[1]), reverse=True))
    types_present = []
    ncols = 7 + len(DEAL_FIELDS) + len(FIN_COLUMNS) + 1
    rows, deal_blocks, last_q = [], [], None
    for name, cs in deals.items():
        info = party_info(cs)
        ptype = next((c["product_type"] for c in cs if c.get("product_type")), "Other")
        kind = next((c["deal_kind"] for c in cs if c.get("deal_kind")), "")
        if ptype not in types_present:
            types_present.append(ptype)
        slug_t = re.sub(r"[^a-z]+", "-", ptype.lower())
        chip = f'<span class="chip t-{slug_t}">{esc(ptype)}</span>' + (f'<span class="kind">{esc(kind)}</span>' if kind else "")
        d = deal_date(cs)
        q = quarter(d)
        if q != last_q:
            rows.append(f'<tr class="period-row" data-period="{esc(q)}"><th colspan="{ncols}" scope="rowgroup"><span>{esc(q)}</span></th></tr>')
            last_q = q
        short = name.split(" (")[0]
        size = next((c["size"] for c in cs if c.get("size")), None)
        size_match = next((c.get("size_match") for c in cs if c.get("size")), None)
        if size:
            ok = found_in_sources(size_match or size, cs, sources)
            size_html = f'{esc(size)} ' + ('<span class="mark ok" title="Appears in the source text">✓</span>' if ok
                                            else '<span class="mark warn" title="Not found in the source text">?</span>')
        else:
            size_html = ""
        tenants = next((c["tenants"] for c in cs if "tenants" in c), None)
        occ = [f"{c['value']}% " + c["unit"].replace("percent", "").strip() for c in cs if 1 in c["questions"]]
        if ptype == "Office":
            if tenants:
                t_html = names_html(tenants, cs, sources)
            elif occ:
                t_html = '<span class="muted">Not named</span>'
            else:
                t_html = '<span class="muted">Not in free text</span>'
            if occ:
                t_html += "<br>" + "<br>".join(esc(o) for o in occ)
        else:
            t_html = ""
        cells = [
            f"<th scope=\"row\" class=\"deal-cell\">{esc(short)}"
            + (f'<span class="when">{esc(info["deal_note"])}</span>' if info["deal_note"] else "") + "</th>",
            f"<td class=\"date-cell\">{date_html(info['date'] or cs[0]['period'], d)}</td>",
            f"<td class=\"type-cell\">{chip}</td>",
            f"<td class=\"num\">{size_html}</td>" if size_html else '<td class="gap">—</td>',
            f"<td>{names_html(info['buyer'], cs, sources, info['missing'])}</td>",
            f"<td>{names_html(info['seller'], cs, sources, info['missing'])}</td>",
            f"<td class=\"tenants\">{t_html}</td>" if t_html else '<td class="gap">—</td>',
        ]
        for label, qs in DEAL_FIELDS:
            hits = [money(c["value"], c["unit"]) for c in cs if qs & set(c["questions"]) and not c.get("fin")]
            cell = "<br>".join(esc(h) for h in hits)
            cells.append(f"<td class=\"num\">{cell}</td>" if cell else '<td class="gap">—</td>')
        for label, key in FIN_COLUMNS:
            hits = [fin_value(c) for c in cs if c.get("fin") == key]
            cell = "<br>".join(esc(h) for h in hits)
            cells.append(f"<td class=\"num fin\">{cell}</td>" if cell else '<td class="gap fin">—</td>')
        lender = names_html(info["lender"], cs, sources) if info["lender"] else ""
        cells.append(f"<td class=\"fin\">{lender}</td>" if lender else '<td class="gap fin">—</td>')
        rows.append(f'<tr data-type="{esc(ptype)}" data-period="{esc(q)}">{"".join(cells)}</tr>')
        facts = [("Date", esc(info["date"] or cs[0]["period"])),
                 ("Type", chip)] + ([("Size", size_html)] if size_html else []) + [
                 ("Buyer", names_html(info["buyer"], cs, sources, info["missing"])),
                 ("Seller", names_html(info["seller"], cs, sources, info["missing"]))]
        if info["lender"]:
            facts.append(("Lender", names_html(info["lender"], cs, sources)))
        if ptype == "Office":
            facts.append(("Tenants", t_html))
        dl = "".join(f"<div><dt>{k}</dt><dd>{v}</dd></div>" for k, v in facts)
        deal_blocks.append(
            f'<section class="deal" data-type="{esc(ptype)}"><h3>{esc(name)}</h3><dl class="facts">{dl}</dl>'
            + (f'<p class="note">{esc(info["deal_note"])}</p>' if info["deal_note"] else "")
            + '<div class="grid">' + "".join(claim_card(c, sources) for c in cs) + "</div></section>")
    deal_blocks = "".join(deal_blocks)
    order = ["Office", "Multifamily", "Industrial", "Hotel"]
    types_present.sort(key=lambda t: order.index(t) if t in order else len(order))
    counts = {t: sum(1 for cs in deals.values() if next((c.get("product_type") for c in cs if c.get("product_type")), "Other") == t)
              for t in types_present}
    filters = '<button type="button" class="filter" aria-pressed="true" data-filter="All">All <span>{}</span></button>'.format(len(deals)) + "".join(
        f'<button type="button" class="filter" aria-pressed="false" data-filter="{esc(t)}">{esc(t)} <span>{counts[t]}</span></button>'
        for t in types_present)
    per_deal = next((s for s in sections if s[1] and s[1][0][0] == 1), None)
    if per_deal:
        qlist = "".join(f"<li value=\"{n}\">{esc_md(q)}</li>" for n, q in per_deal[1])
        fin_heads = [x for x, _ in FIN_COLUMNS] + ["Lender"]
        group = (f'<tr class="col-groups"><th colspan="7" scope="colgroup" class="grp-deal">Deal</th>'
                 f'<th colspan="{len(DEAL_FIELDS)}" scope="colgroup">Pricing</th>'
                 f'<th colspan="{len(fin_heads)}" scope="colgroup" class="fin">Financing</th></tr>')

        def th(f):
            cls = "deal-cell" if f == "Deal" else ("fin" if f in fin_heads else "")
            return f'<th scope="col" class="{cls}">{esc(f)}</th>'
        head = group + "<tr>" + "".join(th(f) for f in ["Deal", "Date", "Type", "Size", "Buyer", "Seller", "Tenants (office)"]
                                       + [f for f, _ in DEAL_FIELDS] + fin_heads) + "</tr>"
        parts.append(f"""
<section class="question-group" id="deals">
  <h2>{esc(per_deal[0])} <span class="qnums">Q1–Q{per_deal[1][-1][0]}</span></h2>
  <details><summary>The questions</summary><ol>{qlist}</ol></details>
  <p class="note">Newest first, grouped by quarter. Dates are the transaction date where the source gives one;
  otherwise the date the deal was reported or announced, as labeled.
  Buyer, seller, lender and dates are not numbers, so verify.py cannot check them.
  <span class="mark ok">✓</span> means the name appears word for word in the saved source text; it does not
  confirm the role (buyer or seller). <span class="mark warn">?</span> means the name was not found there.
  "Not in free text" means the free part of the article doesn't name the party.</p>
  <div class="filters" role="group" aria-label="Filter deals by product type">{filters}</div>
  <div class="table-wrap"><table class="deals">
    <thead>{head}</thead>
    <tbody>{''.join(rows) or f'<tr><td colspan="{ncols}">No verified deal claims yet.</td></tr>'}</tbody>
  </table></div>
  {deal_blocks}
</section>""")

    # Market and financing questions: claims grouped under each question.
    for name, qs in sections:
        if qs and qs[0][0] == 1:
            continue
        blocks = []
        for n, q in qs:
            cs = [c for c in verified if n in c["questions"]]
            inner = ('<div class="grid">' + "".join(claim_card(c, sources) for c in cs) + "</div>"
                     if cs else '<p class="empty">No verified claims yet.</p>')
            blocks.append(f'<section class="question" id="q{n}"><h3><span class="qn">Q{n}</span> {esc_md(q)}</h3>{inner}</section>')
        parts.append(f'<section class="question-group"><h2>{esc(name)}</h2>{"".join(blocks)}</section>')

    # Verified claims not tied to a question, grouped by source.
    background = [c for c in verified if not c["questions"]]
    if background:
        by_source = {}
        for c in background:
            by_source.setdefault(c["source_id"], []).append(c)
        blocks = "".join(
            f'<section class="question"><h3>{esc(sources.get(sid, {}).get("title", sid))}</h3>'
            f'<div class="grid">{"".join(claim_card(c, sources) for c in cs)}</div></section>'
            for sid, cs in by_source.items())
        parts.append(f"""
<section class="question-group" id="background">
  <h2>Background <span class="qnums">not a direct answer to a question</span></h2>
  {blocks}
</section>""")

    # Held claims, with the checker's reason.
    if held:
        items = "".join(
            f"<tr><td>{esc(c['claim_id'])}</td><td>{esc(c['subject'])}</td>"
            f"<td>{esc(money(c['value'], c['unit']))}</td><td>{esc(c['reason'])}</td></tr>"
            for c in held)
        held_html = f"""<div class="table-wrap"><table>
  <thead><tr><th scope="col">Claim</th><th scope="col">What</th><th scope="col">Value</th><th scope="col">Why held</th></tr></thead>
  <tbody>{items}</tbody></table></div>"""
    else:
        held_html = '<p class="empty">No held claims. Every claim passed the checker.</p>'
    parts.append(f'<section class="question-group" id="held"><h2>Held claims <span class="qnums">{len(held)}</span></h2>{held_html}</section>')

    report_path = HERE / "REPORT.md"
    checked = (datetime.datetime.fromtimestamp(report_path.stat().st_mtime).strftime("%B %-d, %Y %H:%M")
               if report_path.exists() else "never")

    page = f"""<title>SF Deal Claims</title>
<meta name="claude:viewport-fit-sides" content="cover">
<style>
:root {{
  --fin-bg: #f3f6f9;
  --office-fg: #1f4e79; --office-bg: #e6eef6; --office-line: #c3d4e6;
  --multi-fg: #6b3f00; --multi-bg: #f8ecd9; --multi-line: #e8d2ad;
  --ind-fg: #3f5d2a; --ind-bg: #e9f0e1; --ind-line: #cbdab8;
  --hotel-fg: #6d2a52; --hotel-bg: #f5e6ee; --hotel-line: #e3c6d6;
  --bg: #f7f6f3; --surface: #ffffff; --text: #1d1d1b; --muted: #66645e;
  --line: #e2dfd8; --accent: #1f5f8b; --ok: #2e7d4f; --warn: #a15c07; --warn-bg: #fdf3e3;
  --quote: #f1efe9;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --fin-bg: #1c2024; --office-fg: #a9c9ec; --office-bg: #1c2a38; --office-line: #2f4459;
    --multi-fg: #f0c88a; --multi-bg: #33281a; --multi-line: #4d3c24;
    --ind-fg: #b9d79c; --ind-bg: #232d1c; --ind-line: #374629;
    --hotel-fg: #eab3d1; --hotel-bg: #351f2b; --hotel-line: #503040;
    --bg: #161615; --surface: #1f1f1d; --text: #ecebe7; --muted: #a3a19a;
    --line: #34332f; --accent: #7cb4dc; --ok: #6cc28f; --warn: #f0b05a; --warn-bg: #2d2416;
    --quote: #262623; color-scheme: dark;
  }}
}}
:root[data-theme="dark"] {{
  --fin-bg: #1c2024; --office-fg: #a9c9ec; --office-bg: #1c2a38; --office-line: #2f4459;
    --multi-fg: #f0c88a; --multi-bg: #33281a; --multi-line: #4d3c24;
    --ind-fg: #b9d79c; --ind-bg: #232d1c; --ind-line: #374629;
    --hotel-fg: #eab3d1; --hotel-bg: #351f2b; --hotel-line: #503040;
    --bg: #161615; --surface: #1f1f1d; --text: #ecebe7; --muted: #a3a19a;
  --line: #34332f; --accent: #7cb4dc; --ok: #6cc28f; --warn: #f0b05a; --warn-bg: #2d2416;
  --quote: #262623; color-scheme: dark;
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: var(--text);
  font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
main {{ max-width: 1320px; margin: 0 auto; padding-block: 24px 64px;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); }}
.grid > * {{ min-width: 0; }}
header h1 {{ margin: 0 0 4px; font-size: 26px; }}
header p {{ margin: 4px 0; color: var(--muted); }}
.stats {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 16px 0 8px; }}
.stat {{ background: var(--surface); border: 1px solid var(--line); border-radius: 8px; padding: 8px 14px; }}
.stat b {{ font-size: 20px; display: block; }}
.stat.ok b {{ color: var(--ok); }} .stat.held b {{ color: var(--warn); }}
nav {{ display: flex; flex-wrap: wrap; gap: 6px 14px; margin: 12px 0 0; font-size: 14px; }}
a {{ color: var(--accent); }}
h2 {{ font-size: 20px; margin: 40px 0 12px; padding-bottom: 6px; border-bottom: 2px solid var(--line); }}
h3 {{ font-size: 16px; margin: 24px 0 10px; }}
.qnums {{ font-size: 13px; font-weight: 500; color: var(--muted); margin-left: 6px; }}
.qn {{ display: inline-block; min-width: 34px; color: var(--accent); }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 12px; }}
.claim {{ background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 14px; }}
.claim-head {{ display: flex; justify-content: space-between; align-items: baseline; gap: 8px; }}
.value {{ font-size: 20px; font-weight: 650; }}
.id {{ font-size: 12px; color: var(--ok); border: 1px solid var(--ok); border-radius: 999px; padding: 1px 8px; white-space: nowrap; }}
.id::before {{ content: "✓ "; }}
.subject {{ margin: 6px 0 2px; font-weight: 500; }}
.period {{ margin: 0 0 8px; color: var(--muted); font-size: 13px; }}
blockquote {{ margin: 0 0 8px; padding: 8px 10px; background: var(--quote); border-left: 3px solid var(--line);
  font-size: 13.5px; overflow-wrap: anywhere; }}
.source {{ margin: 0; font-size: 13px; color: var(--muted); overflow-wrap: anywhere; }}
.flags {{ margin: 8px 0 0; padding: 6px 10px 6px 26px; background: var(--warn-bg); color: var(--warn);
  border-radius: 6px; font-size: 12.5px; }}
.note, .empty {{ color: var(--muted); font-size: 14px; }}
.table-wrap {{ overflow-x: auto; border: 1px solid var(--line); border-radius: 10px; background: var(--surface); }}
table {{ border-collapse: collapse; width: 100%; font-size: 14px; }}
th, td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }}
thead th {{ font-size: 12.5px; color: var(--muted); font-weight: 600; white-space: nowrap; }}
tbody tr:last-child th, tbody tr:last-child td {{ border-bottom: 0; }}
.when {{ display: block; font-weight: 400; font-size: 12.5px; color: var(--muted); }}
td.gap, .muted {{ color: var(--muted); }}
.mark {{ font-size: 12px; font-weight: 700; }}
.mark.ok {{ color: var(--ok); }} .mark.warn {{ color: var(--warn); }}
.facts {{ display: flex; flex-wrap: wrap; gap: 6px 28px; margin: -4px 0 12px; font-size: 14px; }}
.facts div {{ display: flex; gap: 6px; }}
.facts dt {{ color: var(--muted); }} .facts dd {{ margin: 0; }}
td.date-cell {{ min-width: 104px; }} td.date-cell .d {{ white-space: nowrap; font-weight: 500; }}
.chip {{ display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: 12px; font-weight: 600; white-space: nowrap;
  color: var(--chip-fg, var(--text)); background: var(--chip-bg, var(--quote)); border: 1px solid var(--chip-line, var(--line)); }}
.t-office {{ --chip-fg: var(--office-fg); --chip-bg: var(--office-bg); --chip-line: var(--office-line); }}
.t-multifamily {{ --chip-fg: var(--multi-fg); --chip-bg: var(--multi-bg); --chip-line: var(--multi-line); }}
.t-industrial {{ --chip-fg: var(--ind-fg); --chip-bg: var(--ind-bg); --chip-line: var(--ind-line); }}
.t-hotel {{ --chip-fg: var(--hotel-fg); --chip-bg: var(--hotel-bg); --chip-line: var(--hotel-line); }}
.kind {{ display: block; margin-top: 4px; font-size: 12px; color: var(--muted); }}
td.type-cell {{ min-width: 110px; }}
tr.period-row th {{ background: var(--quote); font-size: 12.5px; letter-spacing: .04em; text-transform: uppercase;
  color: var(--muted); padding: 6px 10px; }}
table.deals .deal-cell {{ position: sticky; left: 0; z-index: 1; min-width: 170px; max-width: 220px;
  background: var(--surface); box-shadow: 1px 0 0 var(--line); }}
table.deals thead .deal-cell {{ z-index: 2; }}
table.deals tr.period-row th span {{ position: sticky; left: 10px; }}
table.deals td.num {{ white-space: nowrap; }}
table.deals td.tenants {{ min-width: 130px; }}
table.deals .fin {{ background: var(--fin-bg); }}
tr.col-groups th {{ font-size: 11.5px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted);
  padding-top: 6px; padding-bottom: 4px; }}
tr.col-groups th.grp-deal {{ position: sticky; left: 0; background: var(--surface); z-index: 2; }}
@media (max-width: 600px) {{ table.deals .deal-cell {{ min-width: 130px; max-width: 150px; }} }}
.filters {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 4px 0 12px; }}
.filter {{ font: inherit; font-size: 13.5px; padding: 5px 12px; border-radius: 999px; cursor: pointer;
  background: var(--surface); color: var(--text); border: 1px solid var(--line); }}
.filter span {{ color: var(--muted); margin-left: 2px; }}
.filter[aria-pressed="true"] {{ background: var(--text); color: var(--bg); border-color: var(--text); }}
.filter[aria-pressed="true"] span {{ color: var(--bg); opacity: .75; }}
.filter:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
td {{ font-variant-numeric: tabular-nums; }}
details {{ margin: 0 0 10px; font-size: 14px; }}
summary {{ cursor: pointer; color: var(--accent); }}
footer {{ margin-top: 48px; color: var(--muted); font-size: 13px; }}
</style>
<main>
<header>
  <h1>San Francisco CRE Deal Claims</h1>
  <p>{esc(topic)}</p>
  <div class="stats">
    <div class="stat ok"><b>{len(verified)}</b>verified claims</div>
    <div class="stat held"><b>{len(held)}</b>held claims</div>
    <div class="stat"><b>{len(sources)}</b>sources</div>
    <div class="stat"><b>{len(deals)}</b>deals</div>
  </div>
  <p>Verified means the source hasn't changed, the quote is word for word in it, and the number is in the quote.
  It does not mean the claim is the right fact. Orange notes mark claims a person should still check.</p>
  <nav><a href="#deals">Deals</a>{''.join(f'<a href="#q{n}">Q{n}</a>' for s in sections for n, _ in s[1] if n > 9)}<a href="#background">Background</a><a href="#held">Held</a></nav>
</header>
{''.join(parts)}
<script>
(function () {{
  var buttons = document.querySelectorAll(".filter");
  function apply(type) {{
    buttons.forEach(function (b) {{ b.setAttribute("aria-pressed", String(b.dataset.filter === type)); }});
    document.querySelectorAll("[data-type]").forEach(function (el) {{
      el.hidden = type !== "All" && el.dataset.type !== type;
    }});
    document.querySelectorAll("tr.period-row").forEach(function (r) {{
      var p = r.dataset.period;
      r.hidden = !document.querySelector('tr[data-type][data-period="' + p + '"]:not([hidden])');
    }});
  }}
  buttons.forEach(function (b) {{ b.addEventListener("click", function () {{ apply(b.dataset.filter); }}); }});
}})();
</script>
<footer>Built by build_index.py from claims.json, sources.json, questions.md and REPORT.md (checked {esc(checked)}).
Do not edit by hand.</footer>
</main>
"""
    OUT.write_text('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
                   '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
                   + page.replace("</style>\n<main>", "</style>\n</head>\n<body>\n<main>", 1)
                   + "</body>\n</html>\n", encoding="utf-8")
    if "--fragment" in sys.argv:
        Path(sys.argv[sys.argv.index("--fragment") + 1]).write_text(page, encoding="utf-8")
    print(f"Wrote index.html: {len(verified)} verified, {len(held)} held, {len(deals)} deals.")


if __name__ == "__main__":
    main()
