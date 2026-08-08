# Legal and ethical gates

**⚠ THIS IS RESEARCH, NOT LEGAL ADVICE. It is a reading of primary sources by an AI agent, not by a
lawyer. Nothing here should be relied on. It exists to tell you what to take to a lawyer, and to
stop a send happening before you have.**

Full working, with every section and subsection of the legislation cited:
[`../02_Research/02_Web/W4-novel-breakthrough-and-the-line.md`](../02_Research/02_Web/W4-novel-breakthrough-and-the-line.md)
§§1214–2115.

---

## 1. The four findings that change the artefact

### 1.1 The Spam Act carve-out does not help — APP 7 *is* the regime for post

The comfortable assumption is that because the Spam Act covers only electronic messages, unaddressed
postal mail is lightly regulated. The opposite appears to be true.

- OAIC's APP Guidelines Ch 7 [7.9], [7.11]: **direct marketing expressly includes addressed postal mail.**
- APP 7.8 disapplies APP 7 **only** where the Spam Act or Do Not Call Register Act apply. Neither
  reaches post — **so APP 7 is not excluded; it is the operative provision.**
- Because the data is third-party-sourced, that lands in **APP 7.3**: consent *or* impracticability,
  **plus** a simple opt-out, **plus a prominent opt-out statement in every single piece.**
  "Inconvenience" is not impracticability — and it is hard to argue obtaining consent is
  impracticable when you are holding the postal address and about to post to it.
- **APP 7.6** — on request, you must say **where you got their information**, free, within ~30 days.
  This requires **per-record provenance captured at ingestion. It cannot be retrofitted.**

**Design consequences, immediately actionable:**
1. **Every piece carries a prominent opt-out.** Not fine print. This is also good psychology —
   control beats concealment in the personalisation literature.
2. **A suppression list must exist before the first send**, and honouring it must be automatic.
3. **Provenance per field, captured now.** Where did this land size come from? This sale price? If
   the answer is "the scraper", that needs to be recorded per record, from today, not reconstructed
   later.

Note also *Clearview AI* ([2021] AICmr 54 [168]–[180]): **"publicly available" is not a defence** to
APP 3.5 — covert, indiscriminate collection for private commercial purposes was collection by
*unfair means*. That case concerned sensitive biometric data and the extension to property data is
**not established** — but it is the reasoning a regulator would reach for.

### 1.2 It is an "appraisal", never a "valuation"

**The Valuers Registration Act 1992 (Qld) is in force.** The scoping premise that Queensland repealed
it is wrong. s 63 carries a maximum of **100 penalty units**; s 63(2) has a body-corporate carve-out
only if a director or employee is a registered valuer.

**Sweep the word "valuation" out of every printed asset** and out of the copy that surrounds them.
"Appraisal", "comparable sales", "adjusted range" are the safe register — and the Owner-Subject
Article's existing prohibition on a single figure is doing double duty here.

### 1.3 Queensland has legislated what a defensible comparable set looks like — use it as a gate

**POA 2014 s 215 + Sch 2**: **≥3 comparable properties, sold within 6 months, similar standard and
condition, within 5 km.**

This binds agents, not us — but it is the reference standard against which any weaker comparable set
would look unreasonable to a regulator or a court. **It is also a gift**, because it converts a
judgement call into a hard, checkable gate.

The Owner-Subject Article's existing gates are already close and in places stricter (≥4 comparables,
hard 2.0 km radius widening in 0.5 km steps). **The one place it is weaker is recency:** the current
build accepted sales from 17 December 2025 in an article dated 2026-08-08 — inside 8 months, outside
the 6-month standard.

**Recommendation: adopt s 215 as a hard mailability gate.** No address gets mailed unless it has
**≥3 comparables sold within 6 months within 5 km**, on top of the existing envelope and
`directional_only` rules. Cheap to implement in `build_owner_article.py`, and it means the artefact
meets the only written Australian standard that exists.

### 1.4 ⚠ POA s 222(1) may reach the website, not just the mailer

The most serious unflagged finding. **POA 2014 s 222(1)** prohibits supplying **for reward**
"addresses or other particulars of … places of residence or land … that are for sale". Maximum
**200 penalty units or 2 years**.

Fields runs public for-sale pages and has a paid off-market product. Whether "for reward" and the
s 222(2) appointed-agent exception leave a route open is **exactly the kind of question that must go
to a Queensland property lawyer**, and it concerns **production today**, independent of whether any
mail is ever sent.

Related: **POA s 97(3)(b)–(c)** — you "act as a property agent" merely by advertising, stating, or
**in any way holding out as being ready** to sell, exchange, let or **negotiate**. Max 200 penalty
units or 2 years. Mail copy that offers data and stops short of offering to act is probably fine;
copy that drifts toward "we can help you sell" is the risk. The Owner-Subject Article's existing
**no-CTA rule already sits on the right side of this** — which is a nice accident of an editorial
decision made for tone reasons.

---

## 2. The addressing paradox — there is no clean choice

Queensland's two relevant Acts use "unsolicited" in **opposite senses**. This is not a technicality;
it removes the option of getting it right by being careful.

| | **WRRA s 106** (waste / "No Junk Mail") | **POA s 22 → s 222(3)** (property information sessions) | **Privacy (APP 7)** |
|---|---|---|---|
| **Name-addressed** ("Mr Smith") | **NOT** unsolicited → s 107 sticker prohibition does not apply ✅ | **IS** an unsolicited invitation → restriction applies ⚠ | Strengthens the case you hold **personal information** ⚠ |
| **"The Homeowner"** | **IS** unsolicited → s 107 prohibition applies ⚠ | **NOT** unsolicited ✅ | Weaker personal-information footing ✅ |

Also live: **WRRA s 107** makes delivering non-name-addressed commercial material to a letterbox
marked "No Junk Mail" a prohibited act — a **letter is expressly "advertising material"** (s 105).
And **s 112** puts a duty on whoever *arranges* distribution (max **100 penalty units**), with s 111
compelling you to name the deliverers within 7 days.

**Practical read (to be confirmed by a lawyer):** we do not hold owner names anyway (the mailing
lists have none), which pushes us to "The Homeowner" — and therefore into WRRA s 107 territory,
which is **only** a problem for *unaddressed* delivery. **Australia Post addressed mail to a
street address is not a letterbox drop and does not engage s 107.** That is one more reason the
unaddressed door-drop option should die: it is cheaper, weaker (0.5% vs 0.9%), cannot carry the
personalisation that is the entire product, *and* carries a statutory exposure the addressed
version does not.

---

## 3. The exemption everything rests on may not exist

The whole APP analysis assumes the **small business exemption (s 6D)** applies. It is defeated by
**"trading in personal information"**, which OAIC defines to include *providing a benefit, service or
advantage in order to collect personal information about another individual from someone else* —
i.e. **potentially, paying for property or owner data.**

Fields pays for data (PropRadar, Bright Data). Whether that constitutes trading is question 1 for
the lawyer. And separately, the exemption is a **stated target of Commonwealth reform** with an
unresolved timetable — so even a favourable answer today has a shelf life.

---

## 4. The ethical gates, which are stricter than the legal ones

These are ours, not a regulator's. They come from the evidence, and several are already enforced in
code.

| Gate | Why | Enforced where |
|---|---|---|
| **Never print an inference about the person** | Inferred attributes score 3.11/7 vs 4.08 for stated; disclosing an inference is *worse than saying nothing* | Copy review; not yet automated |
| **Never reference their browsing** | Behavioural triggering is legitimate; behavioural disclosure is not. This is the one that ends relationships rather than wasting postage | Copy review; not yet automated |
| **Never name the neighbours** | Neighbour-record mail is more effective *and* generated documented opt-out backlash | Article already prints addresses of **sold** properties only — public transaction record, not living neighbours' data |
| **Never a single figure; always a range with its width** | Design envelope; ±12% band contains the sale price ~61% of the time; ACL "reasonable grounds" | `guardrails.py`, `factbook.verify()` ✅ |
| **Never defer information about their own home to a later piece** | Leverage over something that matters to them | `guardrails.py` TEASE class ✅ |
| **Allow-list every merge field** | The one verified catastrophe in this literature (OfficeMax's *"Daughter Killed In Car Crash"*) was a **merge-field accident**, not a strategy | **Not built. Must be, before any send** |
| **Re-validate every address on the day of lodgement** | Eligibility moves between nightly runs; and mailing a home currently listed with another agent is the highest reputational risk | PropRadar guard exists; the batch-level pass is not built |
| **Instrument annoyance separately from opt-out** | **34% of Opower recipients had weakly negative willingness to pay while only 0.08–3.3% opted out.** A quiet mailbox is inertia, not consent | Not built |

---

## 5. Before the first envelope is sealed

**Blocking — do not send until these are done:**

1. **A Queensland property lawyer reviews POA ss 22, 97, 215, 222 against both the mail piece and
   the live website.** s 222(1) is the one that could matter most and is not about the mail at all.
2. **A privacy adviser answers the s 6D trading question** and the APP 7.3 pathway.
3. **A prominent opt-out on every piece**, with a suppression list that is honoured automatically.
4. **Per-record provenance** captured from today, for APP 7.6.
5. **Merge-field allow-list** with a hard fail on anything unexpected.
6. **s 215 comparable gate** wired into the builder.
7. **Lodgement-day re-validation** of the whole batch.

**Non-blocking but do it anyway:** register the sending entity's suppression preferences with ADMA's
Do Not Mail service (≥45 days to process, binds members only, does not cover unaddressed material —
so it is a good-faith signal rather than a real control).

---

## 6. The honest summary

Nothing found here says the programme cannot run. What it says is that **the artefact has to be an
appraisal-not-valuation, range-not-figure, public-facts-not-inferences, opt-out-on-every-piece,
s 215-compliant, addressed letter** — which is, almost exactly, the artefact that already exists in
`Owner_Subject_Article/`, built for editorial reasons before any of this was known.

The genuinely uncomfortable finding is **s 222(1)**, because it points at the website rather than
the mail, and it was not on anyone's list. That one should be taken to a lawyer regardless of what
happens to this project.
