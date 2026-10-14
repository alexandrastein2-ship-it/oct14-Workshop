"""
build_index.py: writes index.html, a one-page view of the research database.

Reads claims.json, sources.json, questions.md and REPORT.md. A claim's status
(verified or held) comes only from REPORT.md, so run `python3 verify.py`
first. Claims missing from REPORT.md are shown as held ("not checked yet").

Usage:
  python3 verify.py && python3 build_index.py

Python standard library only. Nothing in this file calls an AI model.
"""

import datetime
import html
import json
import re
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "index.html"

# Per-deal fields (questions 2-9) shown as columns in the deal table.
DEAL_FIELDS = [
    ("Total price", {2}),
    ("$/SF", {3, 4}),
    ("$/unit or key", {5}),
    ("Cap rate", {6}),
    ("Financing", {9}),
]


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
    if u.startswith("million dollars"):
        return f"${value} million"
    if u.startswith("billion dollars"):
        return f"${value} billion"
    if u.startswith("dollars per unit"):
        return f"${value} / unit"
    if u.startswith("dollars per square foot"):
        return f"${value} / SF"
    if u.startswith("percent"):
        return f"{value}%"
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
    rows = []
    for name, cs in deals.items():
        cells = []
        for _, qs in DEAL_FIELDS:
            hits = [money(c["value"], c["unit"]) for c in cs if qs & set(c["questions"])]
            cells.append(f"<td>{esc('; '.join(hits))}</td>" if hits else '<td class="gap">—</td>')
        rows.append(f"<tr><th scope=\"row\">{esc(name)}<span class=\"when\">{esc(cs[0]['period'])}</span></th>{''.join(cells)}</tr>")
    deal_blocks = "".join(
        f'<section class="deal"><h3>{esc(name)}</h3><div class="grid">'
        + "".join(claim_card(c, sources) for c in cs) + "</div></section>"
        for name, cs in deals.items())
    per_deal = next((s for s in sections if s[1] and s[1][0][0] == 1), None)
    if per_deal:
        qlist = "".join(f"<li value=\"{n}\">{esc_md(q)}</li>" for n, q in per_deal[1])
        head = "".join(f"<th scope=\"col\">{esc(f)}</th>" for f, _ in DEAL_FIELDS)
        parts.append(f"""
<section class="question-group" id="deals">
  <h2>{esc(per_deal[0])} <span class="qnums">Q1–Q{per_deal[1][-1][0]}</span></h2>
  <details><summary>The questions</summary><ol>{qlist}</ol></details>
  <p class="note">Buyer, seller, lender and dates are not numbers, so verify.py cannot check them.
  Where known they appear in each claim's description and its quote; read the quote to confirm.</p>
  <div class="table-wrap"><table>
    <thead><tr><th scope="col">Deal</th>{head}</tr></thead>
    <tbody>{''.join(rows) or '<tr><td colspan="6">No verified deal claims yet.</td></tr>'}</tbody>
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

    OUT.write_text(f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SF Deal Claims</title>
<style>
:root {{
  --bg: #f7f6f3; --surface: #ffffff; --text: #1d1d1b; --muted: #66645e;
  --line: #e2dfd8; --accent: #1f5f8b; --ok: #2e7d4f; --warn: #a15c07; --warn-bg: #fdf3e3;
  --quote: #f1efe9;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --bg: #161615; --surface: #1f1f1d; --text: #ecebe7; --muted: #a3a19a;
    --line: #34332f; --accent: #7cb4dc; --ok: #6cc28f; --warn: #f0b05a; --warn-bg: #2d2416;
    --quote: #262623;
  }}
}}
:root[data-theme="dark"] {{
  --bg: #161615; --surface: #1f1f1d; --text: #ecebe7; --muted: #a3a19a;
  --line: #34332f; --accent: #7cb4dc; --ok: #6cc28f; --warn: #f0b05a; --warn-bg: #2d2416;
  --quote: #262623;
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: var(--text);
  font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
main {{ max-width: 1100px; margin: 0 auto; padding: 24px 16px 64px; }}
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
td.gap {{ color: var(--muted); }}
details {{ margin: 0 0 10px; font-size: 14px; }}
summary {{ cursor: pointer; color: var(--accent); }}
footer {{ margin-top: 48px; color: var(--muted); font-size: 13px; }}
</style>
</head>
<body>
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
<footer>Built by build_index.py from claims.json, sources.json, questions.md and REPORT.md (checked {esc(checked)}).
Do not edit by hand.</footer>
</main>
</body>
</html>
""", encoding="utf-8")
    print(f"Wrote index.html: {len(verified)} verified, {len(held)} held, {len(deals)} deals.")


if __name__ == "__main__":
    main()
