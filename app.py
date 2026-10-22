import marimo

__generated_with = "0.25.2"
app = marimo.App(width="medium", app_title="An Automaton's Apology")


@app.cell
def _():
    import json
    from collections import Counter

    import marimo as mo

    from apology.paths import DATA, REPOS, RESULTS
    from apology.schema import adapt_card
    from apology.audit import trust_burden

    def load(path):
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    corpus = load(DATA / "corpus.json")
    lint = load(DATA / "lint.json")
    cards = {p.stem: adapt_card(load(p)) for p in sorted((RESULTS / "cards").glob("*.json"))}
    for _ch in corpus:
        _card = cards.get(_ch["challenge_file"].split("/")[-1].removesuffix(".lean"))
        if _card and _card["repo"] == _ch["repo"]:
            _card["trust_burden"] = trust_burden(_ch, _card.get("audit", {}))
    validation = {p.stem: load(p) for p in (RESULTS / "validation").glob("*.json")}
    findings = {p.stem: load(p) for p in (RESULTS / "findings").glob("*.json")}
    demo_restatements = load(RESULTS / "demo" / "restatements.json") or []
    SEVERITY = {"high": "🔴", "medium": "🟠", "low": "⚪"}
    return Counter, REPOS, SEVERITY, cards, corpus, demo_restatements, findings, lint, mo, validation


@app.cell
def _(corpus, lint, mo):
    mo.vstack(
        [
            mo.md(
                "# An Automaton's Apology\n"
                "**Lean checks the proof. We check the claim.** Lean verifies exactly the statement in the code. "
                "This app shows where OpenAI's Lean statements say something different from their papers: "
                "places that are *not formally verified yet*, never *wrong*."
            ),
            mo.hstack(
                [
                    mo.stat(
                        value="1.2M", label="lines of kernel-checked proof", caption="ten-proofs + Navier–Stokes/Euler"
                    ),
                    mo.stat(
                        value=f"{sum(c['nonblank_lines'] for c in corpus):,}",
                        label="lines of statement",
                        caption="the part a human must trust",
                    ),
                    mo.stat(
                        value=str(sum(f["severity"] == "high" for f in lint)),
                        label="high-severity lint warnings",
                        caption=f"{len(lint)} in total",
                    ),
                ],
                justify="start",
                gap=1,
            ),
        ]
    )
    return


@app.cell
def _(corpus, mo):
    options = {
        f"{c['repo']} · {c['challenge_file'].split('/')[-1].removesuffix('.lean')}": i for i, c in enumerate(corpus)
    }
    picker = mo.ui.dropdown(options=options, value=list(options)[min(4, len(options) - 1)], label="Result")
    mo.vstack([mo.md("## Audit cards"), picker])
    return (picker,)


@app.cell
def _(cards, corpus, lint, picker):
    challenge = corpus[picker.value]
    stem = challenge["challenge_file"].split("/")[-1].removesuffix(".lean")
    card = cards.get(stem)
    file_lint = [
        f for f in lint if f["file"] == challenge["challenge_file"].split("/")[-1] and f["repo"] == challenge["repo"]
    ]
    return card, challenge, file_lint, stem


@app.cell
def _(mo):
    def render_restatements(items):
        icon = {
            "CERTIFIED": "Historical Lean result · not rechecked",
            "FAILED": "🟡 Lean did not accept",
            "REJECTED": "⛔ rejected by the guard",
        }
        blocks = []
        for r in items:
            relation = "↔ same meaning" if r.get("mode", "iff") == "iff" else "→ consequence"
            blocks.append(
                mo.callout(
                    mo.vstack(
                        [
                            mo.md(
                                f"**{icon.get(r['status'], r['status'])}** · `{r['target'].split('.')[-1]}` {relation}"
                                + (" · uses only Mathlib notions" if r.get("mathlib_only") else "")
                            ),
                            mo.md(
                                f"**In words** (AI-written; the Lean below is the guarantee): {r.get('english', '')}"
                            ),
                            mo.accordion(
                                {
                                    "Original, built from OpenAI's file": mo.md(
                                        f"```lean\n{r.get('original_expr', '')}\n```"
                                    ),
                "Restated formal expression": mo.md(
                                        f"```lean\n{r.get('restated', '')}\n```"
                                    ),
                                    "Lean's verdict": mo.md(f"`{(r.get('detail') or '')[:400]}`"),
                                }
                            ),
                        ]
                    ),
                    kind={"CERTIFIED": "info", "REJECTED": "danger"}.get(r["status"], "warn"),
                )
            )
        return mo.vstack(blocks)

    return (render_restatements,)


@app.cell
def _(SEVERITY, card, mo, render_restatements, stem):
    def _relation(rel):
        return {
            "equivalent": "Model proposal: equivalent",
            "lean_stronger": "Model proposal: Lean stronger",
            "lean_weaker": "Model proposal: Lean weaker",
            "different": "Model concern: different",
            "not_formalized": "Model concern: not found in supplied scope",
        }.get(rel, rel)

    if card is None:
        _view = mo.callout(mo.md(f"No audit card for **{stem}**."), kind="neutral")
    else:
        _audit = card["audit"]
        _burden = card["trust_burden"]
        _coverage = [
            {
                "Paper": c["paper_ref"],
                "Lean theorem": (c.get("lean_theorem") or "—").split(".")[-1],
                "Relation": _relation(c["relation"]),
                "Why": c["why"],
            }
            for c in _audit.get("coverage", [])
        ]
        _flags = [
            {
                "": SEVERITY.get(f["severity"], ""),
                "Kind": f["category"],
                "Line": f.get("line"),
                "Declaration": (f.get("decl") or "").split(".")[-1],
                "What differs": f["explanation"],
                "Citation": "Source location checked" if f.get("location_valid", False) else "Unvalidated location",
            }
            for f in _audit.get("flags", [])
        ]
        _probes = [
            {
                "Evidence": "Historical result · not rechecked",
                "Kind": p["result"]["kind"],
                "Claim": p["result"]["claim"],
                "Attempts": len(p["attempts"]),
                "Lean": p["result"]["detail"][:120],
            }
            for p in card["probes"]
        ]
        _glossary = [
            {
                "Definition": g["decl"].split(".")[-1],
                "Plain meaning": g["plain"],
                "Model assessment": g["matches_standard"] + " · unreviewed",
                "Note": g.get("note", ""),
            }
            for g in _audit.get("glossary", [])
        ]
        _view = mo.vstack(
            [
                mo.md(f"### {stem}\n{_audit.get('summary', '')}"),
                mo.hstack(
                    [
                        mo.stat(
                            value=f"{_burden['lines_needing_human_review']} / {_burden['statement_lines']}",
                            label="lines still needing a human",
                        ),
                        mo.stat(value=str(len(_flags)), label="sticky notes"),
                        mo.stat(
                            value=f"{sum(p['result']['status'] == 'GREEN' for p in card['probes'])}/{len(card['probes'])}",
                            label="historical Lean passes (not rechecked)",
                        ),
                    ],
                    justify="start",
                ),
                mo.ui.tabs(
                    {
                        "Paper vs Lean": mo.ui.table(_coverage, selection=None) if _coverage else mo.md("—"),
                        "Sticky notes": mo.ui.table(_flags, selection=None) if _flags else mo.md("None."),
                        "Readable versions (historical checks)": render_restatements(card["restatements"])
                        if card["restatements"]
                        else mo.md("None."),
                        "Lean probes": mo.ui.table(_probes, selection=None) if _probes else mo.md("None."),
                        "Glossary": mo.ui.table(_glossary, selection=None) if _glossary else mo.md("—"),
                    }
                ),
            ]
        )
    _view
    return


@app.cell
def _(Counter, SEVERITY, file_lint, mo):
    _counts = Counter(f["severity"] for f in file_lint)
    _rows = [
        {
            "": SEVERITY[f["severity"]],
            "Rule": f["rule"],
            "Line": f["line"],
            "Declaration": f["decl"].split(".")[-1],
            "Code": f["snippet"],
            "Why it matters": f["explanation"],
        }
        for f in file_lint
        if f["severity"] in ("high", "medium")
    ]
    mo.vstack(
        [
            mo.md(f"#### Deterministic lint · {_counts['high']} high, {_counts['medium']} medium"),
            mo.ui.table(_rows, selection=None, page_size=6) if _rows else mo.md("No high or medium warnings."),
        ]
    )
    return


@app.cell
def _(REPOS, challenge, mo):
    _path = REPOS[challenge["repo"]] / challenge["challenge_file"]
    _source = _path.read_text() if _path.exists() else f"(clone {challenge['repo']} next to this repository to view)"
    mo.accordion(
        {
            f"Statement file · {challenge['challenge_file']} ({challenge['nonblank_lines']} lines)": mo.md(
                f"```lean\n{_source}\n```"
            )
        }
    )
    return


@app.cell
def _(demo_restatements, mo, render_restatements):
    mo.vstack(
        [
            mo.md(
                "## Readable versions with historical Lean results\n"
                "The AI proposes a clearer statement; Lean must prove it means exactly the same as OpenAI's. "
                "The last two are deliberate cheats, to show they are caught."
            ),
            render_restatements(demo_restatements),
        ]
    )
    return


@app.cell
def _(mo, validation):
    _case = validation["expert_case_ns_lemma_8_6"][0]
    _rows = validation["heldout_adjudicated"]["rows"]
    _real = [r for r in _rows if not r["equiv"]]
    _n = len(_real)
    _ai = sum(r["llm"] for r in _real)
    _with_lint = sum(r["llm"] or r["lint"] for r in _real)
    _alarms = sum(r["fa_llm"] for r in _real)
    _kinds = {}
    for _r in _real:
        _k = _kinds.setdefault(_r["pattern"], [0, 0])
        _k[0] += _r["llm"]
        _k[1] += 1
    _control = validation["negative_control"]
    mo.vstack(
        [
            mo.md("## Does it work?\nEvery number comes from a blind or held-out test. Misses are shown."),
            mo.callout(
                mo.md(
                    f"**Expert ground truth, Navier–Stokes Lemma 8.6** (first found by {_case['found_by']}): "
                    f"{sum(h['matched_flag'] is not None for h in _case['hits'])} of {len(_case['hits'])} items found\n\n"
                    + "\n".join(f"- {'✅' if h['matched_flag'] else '❌'} {h['label']}" for h in _case["hits"])
                ),
                kind="success",
            ),
            mo.callout(
                mo.md(
                    "**Expert ground truth, quasi-Riemann hypothesis** (ζ pole at s = 1, found by a community "
                    "audit): Opus flagged it blind at low severity; Sonnet missed it."
                ),
                kind="info",
            ),
            mo.md(f"### {len(_rows)} planted errors that Lean accepts ({len(_rows) - _n} judged meaning-preserving)"),
            mo.hstack(
                [
                    mo.stat(value=f"{_ai / _n:.0%}", label="caught by the AI", caption=f"{_ai} of {_n}"),
                    mo.stat(
                        value=f"{_with_lint / _n:.0%}", label="with deterministic lint", caption=f"{_with_lint} of {_n}"
                    ),
                    mo.stat(value=f"{_alarms / _n:.0%}", label="false alarms at reused mutation sites"),
                    mo.stat(
                        value=f"{_control['with_medium_high']}/{_control['n']}",
                        label="false flags on textbook theorems",
                    ),
                ],
                justify="start",
            ),
            mo.ui.table(
                [{"Error type": k, "Caught": f"{v[0]}/{v[1]}"} for k, v in sorted(_kinds.items())], selection=None
            ),
        ]
    )
    return


@app.cell
def _(findings, mo):
    _cit = findings["citations_navier_stokes"]
    _s = _cit["summary"]
    _absent = [r["label"] for r in _cit["labels"] if r["status"] == "absent"]
    _holes = [h for h in findings["definition_holes_oai_math"] if h["status"] != "UNSPECIFIED_IN_CHALLENGE"]
    mo.vstack(
        [
            mo.md("## Findings in OpenAI's releases\nNone of these says a theorem is false."),
            mo.callout(
                mo.md(
                    "**An error sat exactly where Lean wasn't checking.** OpenAI later corrected a claim about cones in "
                    "*Taming implies compatibility*. Run blind on the original paper, the pipeline marked that claim "
                    "*not formally verified*: it was never in the Lean code. Asked to referee the same proof, Opus "
                    "called it sound."
                ),
                kind="warn",
            ),
            mo.callout(
                mo.md(
                    f"**The code cites an earlier draft.** {_s['not_in_paper']} of {_s['labels_cited']} paper labels cited "
                    f"in the Navier–Stokes Lean files are not in the published paper: {_s['absent']} numbers do not exist "
                    f"at all ({', '.join(_absent)}), {_s['different_kind']} belong to a different kind of statement. "
                    "A second formalization (Unique Games / Max-Cut) has the same problem."
                ),
                kind="warn",
            ),
            mo.callout(
                mo.md(
                    "**Coverage gaps.** Non-sofic groups: the paper proves a specific group is not sofic; Lean proves "
                    "that *some* group is not. Navier–Stokes Lemma 8.6: Lean needs 5 extra derivatives where the paper "
                    "claims 4."
                ),
                kind="warn",
            ),
            mo.callout(
                mo.md(
                    f"**Definition holes** (reproducing a community audit): {len(_holes)} written-out definitions in "
                    f"{len({h['config'] for h in _holes})} statement files of the October release are never compared "
                    "by OpenAI's checker."
                ),
                kind="info",
            ),
        ]
    )
    return


@app.cell
def _(mo):
    from pathlib import Path
    from apology.paths import ROOT
    from apology.ui import available_inspections, render_bundle
    _bundle_options = available_inspections(ROOT)
    bundle_picker = mo.ui.dropdown(options=_bundle_options, value=next(iter(_bundle_options), None), label="Bundle run")
    mo.vstack([mo.md("## Bundle audit and review"), bundle_picker])
    return Path, ROOT, bundle_picker, render_bundle


@app.cell
def _(Path, ROOT, bundle_picker, mo, render_bundle):
    bundle_review_form = None
    if bundle_picker.value:
        _bundle_view, bundle_review_form = render_bundle(mo, Path(bundle_picker.value), ROOT)
    else:
        _bundle_view = mo.md("Generate examples with `python -m experiments.published_examples --build --run`.")
    _bundle_view
    return (bundle_review_form,)


@app.cell
def _(bundle_review_form, mo):
    mo.md("Review recorded locally. Reopen the bundle to refresh its review queue.") if bundle_review_form and bundle_review_form.value else None
    return


if __name__ == "__main__":
    app.run()
