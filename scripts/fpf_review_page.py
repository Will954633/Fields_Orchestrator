#!/usr/bin/env python3
"""Generate a polished, self-contained review page of the personalised FPF batch
for Will to approve before sending. Reads fpf_personalize.build_all()."""
import os, sys, html
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv("/home/fields/Fields_Orchestrator/.env")
import fpf_personalize as P
import fpf_send as S

E = html.escape


def chip(txt, kind="neutral"):
    return f'<span class="chip {kind}">{E(str(txt))}</span>'


def card(rec, picks):
    greet = f"Hi {rec['first_name']}" if rec['first_name'] else "Hi there"
    greet_kind = "good" if rec['first_name'] else "muted"
    subs = " · ".join(S.SUBURB_LABEL.get(s, s) for s in rec['subs_ranked'])
    signals = []
    signals.append(f'<div class="sig"><span class="k">Greeting</span>{chip(greet, greet_kind)}'
                   + (f'<span class="note">CRM name: {E(rec["crm_name"])}</span>' if rec['crm_name'] else '') + '</div>')
    signals.append(f'<div class="sig"><span class="k">Suburbs</span><span class="v">{E(subs)}</span></div>')
    signals.append(f'<div class="sig"><span class="k">Budget</span><span class="v">{E(rec["budget_basis"])}</span></div>')
    if rec['timeframe'] or rec['owns']:
        tf = {"now": "moving now", "in_3_6_months": "3–6 months"}.get(rec['timeframe'], rec['timeframe'] or "—")
        owns = {"yes": "owns a GC home", "no": "doesn't own"}.get(rec['owns'], "")
        signals.append(f'<div class="sig"><span class="k">Brief</span><span class="v">{E(tf)}{" · " + E(owns) if owns else ""}</span></div>')
    if rec['surfaceable_viewed']:
        vh = "".join(chip(c['address'].split(",")[0], "good") for c, _ in rec['surfaceable_viewed'])
        signals.append(f'<div class="sig"><span class="k">Viewed on site</span><span class="chips">{vh}</span></div>')
    if rec['viewed_dead']:
        vd = "".join(chip(f"{s.replace('-', ' ')} — {st}", "dead") for s, _, st, _ in rec['viewed_dead'])
        signals.append(f'<div class="sig"><span class="k">Viewed (gone)</span><span class="chips">{vd}</span></div>')
    if rec['content_subs']:
        cc = " · ".join(f"{S.SUBURB_LABEL.get(k, k)} ×{v}" for k, v in sorted(rec['content_subs'].items(), key=lambda x: -x[1]))
        signals.append(f'<div class="sig"><span class="k">Reads</span><span class="v">{E(cc)}</span></div>')
    n = len(picks)
    signals.append(f'<div class="sig"><span class="k">List</span>{chip(f"{n} homes", "good" if n >= 5 else "warn")}</div>')

    email_html = P.render_html(rec, picks)
    subj = P.subject_for(rec, picks)
    return f'''<article class="card">
      <div class="panel">
        <div class="addr">{E(rec['email'])}</div>
        <div class="src">{E('Facebook lead' if rec['src'] == 'fb_lead' else 'Website subscriber')}</div>
        {''.join(signals)}
      </div>
      <div class="mail">
        <div class="subj"><span class="k">Subject</span>{E(subj)}</div>
        <div class="frame">{email_html}</div>
      </div>
    </article>'''


def build(path):
    results = P.build_all()
    n = len(results)
    named = sum(1 for r, _ in results if r['first_name'])
    viewed = sum(1 for r, _ in results if r['surfaceable_viewed'])
    inferred = sum(1 for r, _ in results if 'inferred' in r['budget_basis'])
    thin = sum(1 for r, p in results if len(p) < 5)
    stamp = datetime.now(S.AEST).strftime("%A %d %B %Y · %H:%M AEST")

    cards = "\n".join(card(r, p) for r, p in results)
    stats = f'''
      <div class="stat"><span class="num">{n}</span><span class="lbl">recipients</span></div>
      <div class="stat"><span class="num">{named}</span><span class="lbl">greeted by name</span></div>
      <div class="stat"><span class="num">{viewed}</span><span class="lbl">lead with a viewed home</span></div>
      <div class="stat"><span class="num">{inferred}</span><span class="lbl">budget inferred from views</span></div>
      <div class="stat"><span class="num">{thin}</span><span class="lbl">thin list (&lt;5)</span></div>'''

    page = f'''<style>
  :root {{
    --ground:#faf8f5; --surface:#ffffff; --surface2:#f4efe8; --ink:#1f1b18; --muted:#6b6259;
    --accent:#b0672f; --good:#2f7d5b; --warn:#a9741f; --dead:#9a8f84; --border:#e7ded3;
    --shadow:0 1px 2px rgba(40,28,15,.05),0 8px 24px rgba(40,28,15,.06);
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --ground:#17140f; --surface:#211d16; --surface2:#2a2419; --ink:#f0ebe4; --muted:#a2978a;
      --accent:#d68a4e; --good:#5cb98d; --warn:#d1a24e; --dead:#7d7367; --border:#342c20;
      --shadow:0 1px 2px rgba(0,0,0,.3),0 8px 24px rgba(0,0,0,.35); }}
  }}
  :root[data-theme="dark"] {{ --ground:#17140f; --surface:#211d16; --surface2:#2a2419; --ink:#f0ebe4;
    --muted:#a2978a; --accent:#d68a4e; --good:#5cb98d; --warn:#d1a24e; --dead:#7d7367; --border:#342c20;
    --shadow:0 1px 2px rgba(0,0,0,.3),0 8px 24px rgba(0,0,0,.35); }}
  :root[data-theme="light"] {{ --ground:#faf8f5; --surface:#ffffff; --surface2:#f4efe8; --ink:#1f1b18;
    --muted:#6b6259; --accent:#b0672f; --good:#2f7d5b; --warn:#a9741f; --dead:#9a8f84; --border:#e7ded3;
    --shadow:0 1px 2px rgba(40,28,15,.05),0 8px 24px rgba(40,28,15,.06); }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--ground); color:var(--ink);
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    line-height:1.55; -webkit-font-smoothing:antialiased; }}
  .wrap {{ max-width:1040px; margin:0 auto; padding:32px 20px 80px; }}
  header .eyebrow {{ text-transform:uppercase; letter-spacing:.14em; font-size:12px; font-weight:600;
    color:var(--accent); margin:0 0 6px; }}
  header h1 {{ font-size:30px; line-height:1.15; margin:0 0 4px; text-wrap:balance; letter-spacing:-.01em; }}
  header .when {{ color:var(--muted); font-size:14px; margin:0 0 24px; }}
  .stats {{ display:flex; flex-wrap:wrap; gap:12px; margin:0 0 14px; }}
  .stat {{ flex:1 1 150px; background:var(--surface); border:1px solid var(--border); border-radius:12px;
    padding:14px 16px; box-shadow:var(--shadow); }}
  .stat .num {{ display:block; font-size:26px; font-weight:700; font-variant-numeric:tabular-nums; letter-spacing:-.02em; }}
  .stat .lbl {{ display:block; font-size:12.5px; color:var(--muted); margin-top:2px; }}
  .hint {{ font-size:13.5px; color:var(--muted); background:var(--surface2); border:1px solid var(--border);
    border-radius:10px; padding:10px 14px; margin:0 0 28px; }}
  .hint b {{ color:var(--ink); }}
  .card {{ display:grid; grid-template-columns:300px 1fr; gap:0; background:var(--surface);
    border:1px solid var(--border); border-radius:14px; overflow:hidden; box-shadow:var(--shadow); margin:0 0 20px; }}
  .panel {{ background:var(--surface2); border-right:1px solid var(--border); padding:18px; }}
  .panel .addr {{ font-weight:650; font-size:14.5px; word-break:break-all; }}
  .panel .src {{ font-size:12px; color:var(--muted); margin:1px 0 14px; }}
  .sig {{ display:flex; flex-direction:column; gap:4px; padding:9px 0; border-top:1px solid var(--border); }}
  .sig .k {{ text-transform:uppercase; letter-spacing:.08em; font-size:10.5px; font-weight:600; color:var(--muted); }}
  .sig .v {{ font-size:13.5px; }}
  .sig .note {{ font-size:11.5px; color:var(--muted); }}
  .chips {{ display:flex; flex-wrap:wrap; gap:5px; }}
  .chip {{ display:inline-block; font-size:12px; font-weight:550; padding:2px 9px; border-radius:999px;
    background:var(--border); color:var(--ink); }}
  .chip.good {{ background:color-mix(in srgb, var(--good) 18%, transparent); color:var(--good); }}
  .chip.warn {{ background:color-mix(in srgb, var(--warn) 20%, transparent); color:var(--warn); }}
  .chip.muted {{ background:var(--border); color:var(--muted); }}
  .chip.dead {{ background:transparent; color:var(--dead); text-decoration:line-through; border:1px dashed var(--border); }}
  .mail {{ padding:18px; min-width:0; }}
  .mail .subj {{ font-size:14px; font-weight:600; margin-bottom:12px; padding-bottom:12px; border-bottom:1px solid var(--border); }}
  .mail .subj .k {{ display:block; text-transform:uppercase; letter-spacing:.08em; font-size:10.5px;
    font-weight:600; color:var(--accent); margin-bottom:3px; }}
  .frame {{ background:var(--ground); border:1px solid var(--border); border-radius:10px; padding:6px 14px;
    font-size:14px; overflow-x:auto; }}
  .frame a {{ color:var(--accent) !important; }}
  @media (max-width:720px) {{ .card {{ grid-template-columns:1fr; }} .panel {{ border-right:none; border-bottom:1px solid var(--border); }} }}
</style>
<div class="wrap">
  <header>
    <p class="eyebrow">Five Property Friday · pre-send review</p>
    <h1>Personalised shortlists — ready to send</h1>
    <p class="when">{stamp} · nothing sends until you approve · 9am auto-batch is held</p>
  </header>
  <div class="stats">{stats}</div>
  <p class="hint">Each card shows the <b>enrichment signals</b> we resolved (left) and the <b>actual email</b> that recipient receives (right). Homes they viewed on site lead the list; budgets are inferred from what they browsed where we have it, else the suburb median. <b>Verify the CRM names before send</b> — a wrong first name is worse than none.</p>
  {cards}
</div>'''
    open(path, "w").write(page)
    print(f"wrote {path}")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/claude-1001/-home-fields-Fields-Orchestrator/f1694ada-0d66-4689-89a2-0c2e57b35933/scratchpad/fpf_review.html"
    build(out)
