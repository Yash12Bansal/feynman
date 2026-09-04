// Builds the MATS write-up skeleton: headings in Nanda's order, figures embedded,
// appendix tables copied from logbook.md / WRITEUP_KIT.md, and highlighted slots
// where Yash's prose goes. No prose is written for him.
const fs = require("fs");
const D = require("docx");
const { Document, Packer, Paragraph, TextRun, HeadingLevel, ImageRun, Table, TableRow, TableCell,
        WidthType, ShadingType, AlignmentType, PageBreak, LevelFormat, BorderStyle, TabStopType } = D;
const C = JSON.parse(fs.readFileSync("writeup_content.json", "utf8"));

const PAGE_W = 11906, MARGIN = 1134, TEXT_W = PAGE_W - 2 * MARGIN; // A4, 2 cm margins (DXA)
const GREY = "6B6B6B", SLOT = "FFF2A8";

// ---------- inline markdown -> runs ----------
function runs(text, base = {}) {
  const out = [];
  const re = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g;
  let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(new TextRun({ text: text.slice(last, m.index), ...base }));
    const t = m[0];
    if (t.startsWith("**")) out.push(new TextRun({ text: t.slice(2, -2), bold: true, ...base }));
    else if (t.startsWith("`")) out.push(new TextRun({ text: t.slice(1, -1), font: "Consolas", size: 18, ...base }));
    else out.push(new TextRun({ text: t.slice(1, -1), italics: true, ...base }));
    last = m.index + t.length;
  }
  if (last < text.length) out.push(new TextRun({ text: text.slice(last), ...base }));
  return out;
}
const P = (text, opts = {}) => new Paragraph({ children: runs(text), spacing: { after: 100 }, ...opts });
const H1 = (t) => new Paragraph({ text: t, heading: HeadingLevel.HEADING_1, spacing: { before: 360, after: 120 } });
const H2 = (t) => new Paragraph({ text: t, heading: HeadingLevel.HEADING_2, spacing: { before: 240, after: 80 } });
const H3 = (t) => new Paragraph({ children: runs(t), heading: HeadingLevel.HEADING_3, spacing: { before: 180, after: 60 } });
const slot = (t) => new Paragraph({ children: [new TextRun({ text: "▢ WRITE HERE: " + t, shading: { type: ShadingType.CLEAR, fill: "FFF2A8", color: "auto" } })], spacing: { after: 120 } });
const guide = (t) => new Paragraph({ children: runs(t, { italics: true, color: GREY, size: 18 }), spacing: { after: 60 } });
const guideHead = (t) => new Paragraph({ children: [new TextRun({ text: t, italics: true, color: GREY, size: 18, bold: true })], spacing: { before: 60, after: 40 } });
const bullet = (t, level = 0) => new Paragraph({ children: runs(t), numbering: { reference: "bul", level }, spacing: { after: 60 } });
const gbullet = (t) => new Paragraph({ children: runs(t, { italics: true, color: GREY, size: 18 }), numbering: { reference: "bul", level: 0 }, spacing: { after: 40 } });
const quote = (t) => new Paragraph({ children: runs(t, { size: 20 }), indent: { left: 400 }, border: { left: { style: BorderStyle.SINGLE, size: 6, color: "BBBBBB", space: 8 } }, spacing: { after: 60 } });
const mono = (t) => new Paragraph({ children: [new TextRun({ text: t, font: "Consolas", size: 17 })], spacing: { after: 0 }, indent: { left: 300 } });
const pb = () => new Paragraph({ children: [new PageBreak()] });
const caption = (t) => new Paragraph({ children: runs(t, { size: 19 }), alignment: AlignmentType.LEFT, spacing: { after: 200 } });

function fig(name, widthIn = 6.3) {
  const f = C.figs[name]; const w = Math.round(widthIn * 96); const h = Math.round(w * f.h / f.w);
  return new Paragraph({ children: [new ImageRun({ type: "png", data: fs.readFileSync(f.path), transformation: { width: w, height: h } })], spacing: { before: 120, after: 60 } });
}

function table(rows, widths, fontSize = 17) {
  const total = widths.reduce((a, b) => a + b, 0);
  const cw = widths.map(w => Math.round(TEXT_W * w / total));
  return new Table({
    width: { size: TEXT_W, type: WidthType.DXA }, columnWidths: cw,
    rows: rows.map((r, i) => new TableRow({
      tableHeader: i === 0,
      children: r.map((c, j) => new TableCell({
        width: { size: cw[j], type: WidthType.DXA },
        shading: i === 0 ? { type: ShadingType.CLEAR, fill: "EDEDED", color: "auto" } : undefined,
        margins: { top: 40, bottom: 40, left: 70, right: 70 },
        children: [new Paragraph({ children: runs(c, { size: fontSize, bold: i === 0 }), spacing: { after: 0 } })],
      })),
    })),
  });
}

function parasFrom(items) {
  const out = [];
  for (const it of items) {
    if (it.type === "h") out.push(H3(it.text));
    else if (it.type === "bullet") out.push(bullet(it.text));
    else if (it.type === "num") out.push(bullet(it.text));
    else out.push(P(it.text));
  }
  return out;
}

// random examples markdown -> paragraphs (inside replies, '#' lines become bold text, never headings)
function examples(lines) {
  const out = []; let inReply = false;
  for (let raw of lines) {
    const l = raw.replace(/\s+$/, "");
    if (!l.trim()) continue;
    if (l.startsWith("# ")) continue;                       // file title: replaced by our heading
    if (l.startsWith("## ")) { inReply = false; out.push(H3(l.slice(3))); continue; }
    if (/^#{3,}\s/.test(l)) { out.push(new Paragraph({ children: runs(l.replace(/^#+\s*/, ""), { bold: true, size: 20 }), indent: { left: 300 }, spacing: { before: 80, after: 40 } })); continue; }
    if (l.startsWith("> ")) { out.push(quote(l.slice(2))); continue; }
    if (l.trim() === "---") continue;
    if (/^\s*[-*] /.test(l)) { out.push(new Paragraph({ children: runs(l.replace(/^\s*[-*] /, ""), { size: 20 }), numbering: { reference: "bul", level: /^\s{2,}/.test(l) ? 1 : 0 }, spacing: { after: 30 } })); continue; }
    if (/^\s*\d+\. /.test(l)) { out.push(new Paragraph({ children: runs(l.replace(/^\s*\d+\. /, ""), { size: 20 }), indent: { left: 500 }, spacing: { after: 30 } })); continue; }
    if (/^\*\*Qwen's actual reply/.test(l) || /^\*\*Strength/.test(l)) { inReply = true; out.push(P(l)); continue; }
    if (/^Judge \(/.test(l)) { inReply = false; out.push(P(l)); continue; }
    out.push(inReply ? new Paragraph({ children: runs(l, { size: 20 }), indent: { left: 300 }, spacing: { after: 50 } }) : P(l));
  }
  return out;
}

// ---------- document ----------
const kids = [];
const add = (...x) => kids.push(...x.flat());

// Title block
add(new Paragraph({ children: [new TextRun({ text: "▢ TITLE (yours) — specific and plain; ingredients: user competence, updates one way, half made by the model itself", shading: { type: ShadingType.CLEAR, fill: "FFF2A8", color: "auto" }, bold: true, size: 32 })], spacing: { after: 120 } }));
add(P("Yash Bansal · Application to MATS 12.0, Neel Nanda stream · September 2026"));
add(new Paragraph({ children: [new TextRun({ text: "▢ Hours: __ h project + __ h executive summary (Toggl screenshot in Appendix I) · Code: [link, commit __] · Logbook: [link]", shading: { type: ShadingType.CLEAR, fill: "FFF2A8", color: "auto" } })], spacing: { after: 60 } }));
add(new Paragraph({ children: [new TextRun({ text: "▢ Optional one-line epistemic status (the MATS 6.0 accept opened with one).", shading: { type: ShadingType.CLEAR, fill: "FFF2A8", color: "auto" } })], spacing: { after: 200 } }));
add(guide("Everything in grey italics is a GUIDE for you and must be deleted before submitting. Yellow boxes are where your own words go. Nothing below is written for you; the numbers are copied from the result files and the logbook so you do not retype them."));

// Executive summary
add(H1("Executive summary"));
add(guide("His rule: ~1 page ideal, max 3 pages and max 600 words, WITH graphs; bullet points can work well. His three suggested headings are used below. Calibrated verbs: compelling (E1, E4, asymmetry, anchoring) · suggestive (the self-shaped half) · tentative (sycophancy where unsure)."));
add(H2("What problem am I trying to solve?"));
add(slot("2–4 sentences: prior work = static facts about the user (TalkTuner, Chen et al. 2024); competence is dynamic; a model that decides you are a novice and discounts your corrections is the seed of sycophancy and manipulation; his list asks whether models 'form dynamic models of users for attributes that vary across turns, e.g. what the user knows'. ~70 words."));
add(H2("High-level takeaways"));
add(slot("2 insights + 1 lead, each with its number and CI, plus one line that the existence result was expected and is the tool. ~180 words."));
add(guideHead("Numbers to use (source in brackets)"));
add(gbullet("Existence (expected): 98.5% held-out per snapshot at layer 22; chance 33.3%; shuffled 32.7%; topic control 100%; length-only 46.1%; direction shared across two writers (raw transfer 61–68% → 94.1% thresholds refit, 97.6% pooled). [results_e1.json]"));
add(gbullet("Update one way: e→n minus n→e journey fraction +0.31 [+0.16, +0.46] at the first switched turn, +0.26 [+0.16, +0.36] at the last; both directions cross 0.5 within one turn; 27% of novice-start users still classified novice after three expert turns, 0% of expert-start users still expert after three novice turns. [results_e2.json]"));
add(gbullet("Half self-shaped: anchoring 0.28 [0.18, 0.39] below a lifelong expert; history effect +0.30 [+0.21, +0.40] vs writing effect −0.02; with the model's own replies replaced by a neutral line +0.17 [+0.09, +0.26]. Expert start: +0.03 with real replies vs +0.16 with neutral ones. [results_e2.json]"));
add(gbullet("Three layers: internal 96.6% from the first message, 99.4% [98.3, 100] per dialogue; behaviour anchoring −0.29 ± 0.11 on a 5-point pitch scale (≈14% of the range vs 30% in the probe); stated: 'intermediate' for all 179+179+96 (three-way), 118/119 forced binary at the end, 178/179 'beginner' on the first message (chance) while the probe reads it at 96.6%; after a switch stated 60% / 67% vs probe 73% / 100%. [results_e1_justask*.json, results_e2_causal.json]"));
add(gbullet("Lead (exploratory, post-hoc, n=12): internal P(true) for false claims the model corrected 0.15 [0.10, 0.20] (n=79) vs not corrected 0.52 (n=12); difference +0.38 [+0.23, +0.53]; ~4 of 91 are 'knew it was false and still did not correct'. [results_e3_600_summary.json]"));
add(gbullet("Pre-registration: 11 predictions written before any run; 8 yes, 3 no; three of the four lowest-probability bets (25–32%) came out yes. [logbook §0, Appendix A]"));
add(H2("Key experiments"));
add(guide("One short paragraph + one graph each: what it was, what it found, why it supports the takeaway. Captions are yours; two lines each."));
add(fig("e2_update_curves", 5.6));
add(caption("▢ Figure 1 caption: frozen layer-22 probe on 96 scripted reversal dialogues; P(expert) per user turn with 95% bootstrap bands; baselines from consistent dialogues at the same turn index."));
add(slot("Paragraph for Figure 1 (asymmetry and anchoring). ~90 words."));
add(fig("e2_anchoring_source", 6.3));
add(caption("▢ Figure 2 caption: distance of the final estimate (turn 6) from the lifelong baseline of the new level under three versions of the pre-switch history: cut off; kept with the model's replies replaced by 'Thanks, that's a good question. Let's keep going.'; kept in full."));
add(slot("Paragraph for Figure 2 (where the first impression lives). ~90 words."));
add(fig("e3_internal_by_verdict_600", 4.6));
add(caption("▢ Figure 3 caption: 91 false claims the model answered correctly when asked neutrally; internal truth-probe P(claim true) at the end of the claim turn, split by what the model's 600-token reply did (Gemini 2.5 Pro judge; all 12 not-corrected verdicts hand-checked)."));
add(slot("Paragraph for Figure 3 (the lead, labelled exploratory). ~80 words."));
add(H2("Biggest limitations, and what I would do next"));
add(slot("2–3 bullets: single 8B model; synthetic dialogues; the placeholder control is off-distribution; E3 cells small, judge noise ±3. Then 2 next steps. ~60 words."));
add(H2("What I verified by hand"));
add(slot("1–2 bullets: all 12 uncorrected E3 replies + 9 corrections read (21/21 final, 18–19/21 first pass); 48 E4 replies read blind; 30 QC dialogues; one headline number recomputed. ~40 words."));
add(guide("Word count check: everything from 'What problem' to here must be ≤ 600 words. Figures do not count."));

// Random examples
add(pb(), H1("Randomly selected examples (not cherry-picked)"));
add(guide("His rule: 'include some randomly selected qualitative examples in the write-up, ideally just after the executive summary. Randomly selected, not cherry-picked!' These are pasted from writeup_random_examples.md unchanged (seed 2026). Add one sentence of your own on how they were drawn if you want; do not edit the examples."));
add(examples(C.ex));

// Setup
add(pb(), H1("Setup"));
add(H2("Terms used below"));
add(table([["Term", "Meaning"],
  ["residual stream", "The running vector per token that every transformer layer reads from and writes to; Qwen3-8B has 36 layers and a 4096-dimensional stream. We read it at the last token of the prompt, i.e. the state from which the model would begin its reply."],
  ["linear probe", "A logistic-regression classifier fitted on stored residual-stream vectors while the model stays frozen. High accuracy on unseen topics means the information is linearly present, not that the model uses it."],
  ["P(expert)", "The probe's probability that the user is an expert (third class of novice / intermediate / expert)."],
  ["held-out topics", "Immunology, chess, statistics, networking: never used to train any probe; every accuracy reported is on these unless stated."],
  ["reversal dialogue", "Scripted 6-turn dialogue whose user behaves as one level for turns 1–3 and the other level for turns 4–6."],
  ["journey fraction", "How far the estimate has travelled from its own pre-switch value toward the lifelong baseline of the new level, at the same turn index; removes the 'less distance to travel' confound."],
  ["anchoring gap", "Lifelong-baseline P(expert) minus the reversal dialogue's final P(expert), both at turn 6."],
  ["history effect / writing effect", "History effect = the drop caused by keeping the pre-switch turns in context; writing effect = how the post-switch turns score in isolation relative to lifelong dialogues."],
  ["difference-in-differences", "The confident-minus-hedged shift in the truth probe on false claims, minus the same shift on true claims; removes a probe that merely reads hedging words."],
  ["diff-of-means direction", "mean(expert activations) − mean(novice activations) at layer 22; added at every position during generation (steering) or projected to the dataset mean (mean-ablation)."],
  ["α*", "The largest steering strength whose mean coherence score stays ≥ 4/5 at both signs; fixed as a rule before the run (it was 8, in units of 0.1‖d‖)."],
  ["FK grade", "Flesch–Kincaid reading grade of a reply, an automatic proxy for pitch; the judge's 1–5 level score is the primary pitch measure."]], [1, 4], 17));
add(H2("Model and data"));
add(slot("2–4 sentences in your words on the subject model and why thinking is off, then point at the table."));
add(table([["Dataset", "Size", "Shape", "Used for"],
  ["main (Codex / GPT)", "536 dialogues, 2,748 snapshots", "12 topics × 3 levels × ~15; 4–8 user turns; user never states level", "E1 probe train/test; baselines for E2"],
  ["main (Gemma-3-27B)", "540 dialogues, 2,846 snapshots", "same brief, second writer", "cross-generator control"],
  ["explicit", "144", "12 × 3 × 4; user states level in turn 1", "told vs shown competence (H1c)"],
  ["reversal", "96 (48 per direction)", "6 user turns; behaviour flips at turn 4", "E2 dynamics, anchoring, causal follow-up"],
  ["truth", "192 statements", "8 true + 8 false per topic, no dialogue", "truth probe training"],
  ["honesty", "190 (184 kept)", "12 topics × {true, false} × {confident, hedged}; claim in user turn 3", "E3"]], [1.3, 1.4, 2.6, 2], 17));
add(H2("How the dialogues were written, and the anti-confound rules"));
add(slot("3–5 sentences: three model families kept apart (subject Qwen; writers GPT via Codex and Gemma-3-27B; judges Gemini 2.5 Pro, Phi-4); the rules (same topics and questions at every level, no self-labels, 25–60 words per turn at every level, neutral tone, level only through misconceptions, terminology precision, question type, calibration of hedging); level definitions and the verbatim rule block are in Appendix H."));
add(H2("Quality control before any GPU time"));
add(slot("3–5 sentences on the three checks (length audit, leak filter, blind judges) and what the 37% judge result turned out to be. Tables below are from the logbook."));
add(guide("Words per user turn, mean ± sd (logbook §4a):"));
add(table(C.t4a, [1, 2, 2], 17));
add(guide("Blind judge on user turns only, 120 random dialogues per run (logbook §4d). Every error in every run is a one-step upward shift; rank correlation 0.86–0.87."));
add(table(C.t4d, [3, 1.2, 1.3, 1.3, 1, 1.1], 15));
add(guide("Leak filter: Codex 0 (4 dialogues rejected at merge); Gemma 2 flags, both false positives ('years of' fund data; 'intermediate nodes')."));
add(H2("Activations, probe, steering, judges"));
add(slot("Bullets or 4–6 sentences. Facts: residual stream at the last prompt token, all 37 layers, one forward pass per user turn; logistic regression with standardized features, C = 0.1, trained on 8 topics, tested on the 4 held-out ones; downstream probe trained on both writers (pre-registered rule: within a few points of within-writer accuracy; it was within 1); steering = diff-of-means at layer 22, hook on that layer's output at every position, α ∈ {±4, ±8} × 0.1‖d‖, 3 random directions of equal norm, 12 neutral prompts; judges Gemini 2.5 Pro via OpenRouter (E3, E4, causal), Phi-4 local second judge, Gemma-27B and Phi-4 for QC; rubrics verbatim in Appendix H."));

// Results
add(pb(), H1("Results"));
add(guide("One section per claim, in this order, claims first (never chronological). Each: the question and what you predicted → the result with CI → the dumbest alternative explanation and the control → what it does not show. Calibrated verbs. Numbers below are copied from the result files for you to use."));

add(H2("Claim A. About half of the first-impression effect is carried by the content of the model's own earlier replies"));
add(slot("Question + prediction (H2c: 32%, line 0.1). Result. Controls. What it does not show. Hypothesis paragraph labelled as such. ~250 words. Figure 2 is in the summary; refer to it."));
add(guideHead("Numbers"));
add(gbullet("Anchoring at matched turn 6: novice→expert 0.28 [0.18, 0.39] below a lifelong expert; expert→novice 0.03 [0.01, 0.05] above a lifelong novice. [results_e2.json]"));
add(gbullet("Writer-not-model control: post-switch turns in isolation 1.000 (lifelong expert 0.983); history effect +0.30 [+0.21, +0.40]; writing effect −0.02 [−0.04, −0.00]."));
add(gbullet("Saturated probe: flip fractions n→e 0.42 / 0.58 / 0.73 on the three switched turns; e→n 0.73 / 0.92 / 1.00. Say the curves are mostly per-dialogue flips."));
add(gbullet("Neutral-placeholder control (every turn kept, the three pre-switch replies replaced by 'Thanks, that's a good question. Let's keep going.'): history effect +0.17 [+0.09, +0.26] vs +0.30 [+0.21, +0.40] with the real replies. Expert start: +0.16 [+0.08, +0.24] with neutral replies vs +0.03 with the real expert-pitched replies."));
add(gbullet("Disclose: an earlier control that merged the user's turns into one message gave +0.01 and was a merge artifact; superseded."));
add(gbullet("Allowed wording: 'roughly half of the first-impression effect is attributable to the content of the model's own earlier replies, and its own replies shape the estimate in both directions'. Not 'the model anchors on itself'. Prior work: 'Old Habits Die Hard' (2026) shows a model's own outputs trap later states in general; we did not find the two-channel split on a user representation."));
add(gbullet("Caveats: the placeholder is off-distribution; CIs overlap so 'about half' is approximate; probe readout at one layer."));

add(H2("Claim B. Updating is one-directional"));
add(slot("Question + prediction (H2b: 29%). Result. Why journey fraction. Fits E1. Caveats. Prior work. ~200 words. Figure 1 is in the summary; refer to it."));
add(guideHead("Numbers"));
add(gbullet("Journey fraction e→n − n→e: +0.31 [+0.16, +0.46] first switched turn; +0.26 [+0.16, +0.36] last turn. Codex probe +0.23 / +0.22, CIs clear of 0. [results_e2.json]"));
add(gbullet("Crossover: n→e one turn after the switch; e→n on the first switched turn. Journey fractions n→e 0.39 → 0.71; e→n 0.70 → 0.97. Mean P(expert) by turn: n→e [0.0, 0.0, 0.0, 0.38, 0.61, 0.70]; e→n [1.0, 0.99, 1.0, 0.30, 0.09, 0.03]."));
add(gbullet("Fits E1: novices who learned inside natural dialogues never moved the estimate (P(novice) ≈ 0.99 at their last turn while blind judges called those turns intermediate)."));
add(gbullet("Caveats: scripted reversals from one writer; the assistant's post-switch replies are in context in both directions (cannot create the asymmetry alone). Prior work: Schubert et al. ICML 2024 (asymmetric belief updating of rewards); the LessWrong user-attribute post reports updates but no directional asymmetry. Wording: 'we did not find prior work reporting this asymmetry for a user model.'"));

add(H2("Claim C. Three layers disagree: internal estimate, behaviour, stated estimate"));
add(slot("Question (post-hoc: his 'compare against just ask the model'). Results for the three layers. Say plainly the probe is not needed for the existence claim at the end of a dialogue. Caveat. Prior work (LessWrong post is the direct predecessor; call this incremental). ~250 words."));
add(fig("e2_causal_anchoring", 6.3));
add(caption("▢ Figure 4 caption: the model's actual final-turn reply in five conditions, judged pitch (primary) and reading grade; n = 60 / 48 / 48 / 61 / 61; error bars are standard errors."));
add(guideHead("Numbers"));
add(gbullet("Internal: 96.6% from the first message alone; 99.4% [98.3, 100] per dialogue at the final turn. [results_e1.json]"));
add(gbullet("Behaviour: pitch lifelong novice 2.58 ± 0.10; reversal n→e 4.35 ± 0.09; steered 4.75 ± 0.06; lifelong expert 4.64 ± 0.06; ablated 4.36 ± 0.07; coherence 4.90–4.98. A (reversal − expert) −0.29 ± 0.11; B (steered − expert) +0.11 ± 0.09, sufficiency only (no steered-lifelong-expert condition); C (ablation) −0.28 ± 0.09, about a quarter of the adaptation. Cosine probe-vs-diff-of-means 0.46 (random ≈ 0.02). [results_e2_causal.json]"));
add(gbullet("Stated: three-way → 'intermediate' for all 179 + 179 + 96 (33.5%); third-person 'be accurate, not polite' → 49% (middle-option default, not politeness); forced binary → 118/119 at the final turn; first message → 'beginner' 178/179 (chance) while the probe reads it at 96.6%; after a switch stated matches current behaviour 60% (n→e) / 67% (e→n) vs probe 73% / 100%. [results_e1_justask*.json]"));
add(gbullet("Caveat: one assistant reply is in context in the first-turn condition; the model may read its own reply."));

add(H2("Claim D (exploratory). Failures to correct a false claim concentrate where the truth probe is unsure"));
add(slot("Label it post-hoc and exploratory in the first sentence. Setup (truth probe, pre-filter). H3b as a null with direction noted. H3c. The split. Judge and hand-check. The 200-token pivot disclosed with before/after numbers. Prior work. ~300 words. Figure 3 is in the summary; refer to it."));
add(fig("e3_sycophancy_gap_600", 4.4));
add(caption("▢ Figure 5 caption: share of false claims validated / not corrected by the user's voice, 600-token replies, Gemini 2.5 Pro judge (n = 45 confident, 46 hedged)."));
add(guideHead("Numbers"));
add(gbullet("Truth probe: layer 21, 96.9% on held-out bare statements; in dialogue 88.7% on held-out topics (n=62), 90.8% all topics; claim-sentence position 88.7%. Pre-filter: 184 of 190 claims answered correctly when asked neutrally; cells 45 / 46 / 47 / 46. [results_e3.json]"));
add(gbullet("600-token replies: confident correct 37 / validate 6 / hedge 2 of 45; hedged 42 / 2 / 2 of 46. Validate 13.3% vs 4.3%, gap +0.09 [−0.02, +0.20], ratio 3.1; not corrected 17.8% vs 8.7%, gap +0.09 [−0.04, +0.22]. H3b = NO by the pre-registered rule (gap < 15 points, CI includes 0). [results_e3_600_summary.json]"));
add(gbullet("H3c: difference-in-differences +0.01 [−0.12, +0.14] (bound ±0.15); raw means false/confident 0.248, false/hedged 0.147, true 0.921 / 0.830. [results_e3.json]"));
add(gbullet("By verdict (end-of-turn probe): corrected n=79 0.15 [0.10, 0.20]; hedged n=4 0.54; validated n=8 0.52 [0.37, 0.67]; not-corrected − corrected +0.38 [+0.23, +0.53]; claim-sentence position +0.05 [−0.11, +0.23]. Of the 12 uncorrected, ~8 had P(true) ≥ 0.4 and ~4 had the model internally sure the claim was false."));
add(gbullet("Judge: Phi-4 second judge 63% three-way, 55/60 validated-vs-not; Gemini gave different verdicts to 4 of 21 identical borderline replies. Hand-check 21/21 final, 18–19/21 first pass. Pivot: 157/184 replies cut at 200 tokens; 13/21 decisive verdicts changed at 600; all 91 regenerated; validate 15.6% / 6.5% → 13.3% / 4.3%."));
add(gbullet("Prior work: 'When Truth Is Overridden' (AAAI 2026); 'Dissociating the Internal Representations of Sycophancy' (2026); truth-probe line. Wording: 'extends the internal-origins-of-sycophancy line with a per-case split; exploratory, n=12.'"));

add(H2("Confirmation 1. User competence is a linear direction at mid layers (E1)"));
add(slot("Short. One sentence that this was expected and is the tool. Then the numbers and the method point (direction transfers, calibration does not). ~150 words."));
add(fig("e1_layer_profile", 5.4));
add(caption("▢ Figure 6 caption: probe accuracy by layer on held-out topics, with the shuffled-label and topic controls and the length-only baseline."));
add(guideHead("Numbers"));
add(gbullet("Best layer 22: 98.5% per snapshot; 99.4% [98.3, 100] per dialogue (178/179). Chance 33.3%; shuffled 32.7%; topic 100%; length-only 46.1%. Layer profile 81% at layer 1, ~90% from 11, ~98% from 21. Confusion: novice 312/314, intermediate 299/301, expert 308/318; novice↔expert swaps 0/933; binary 99.7%. [results_e1.json]"));
add(gbullet("Cross-generator raw 67.6% / 60.7%; codex→gemma confusion [291, 0, 0; 266, 50, 0; 3, 30, 282] (the whole drop is Gemma intermediates called novice); Codex direction with thresholds refit on Gemma 94.1%; pooled probe 97.6% / 97.6%; best raw-transfer layer 14 (~66%)."));
add(gbullet("Explicit↔implicit 91.4% / 96.7%; own-set 98.9% / 98.5%; ratio 0.92 (line 0.8). H1b NO: turn 0 already 96.6%, turn 3 − turn 0 = +3.4 (line +8), a ceiling pre-registered in logbook §4e. P(true class) by turn 0.94–1.0."));

add(H2("Confirmation 2. The direction is causal for pitch; prompting is equally covert (E4)"));
add(slot("Short. Method in two sentences, the H4 statistic, the H4b null, the one-sided floor, your 'simple explanation' observation with counts, what is not closed. ~200 words."));
add(fig("e4_dose_response", 5.4));
add(caption("▢ Figure 7 caption: reading grade of replies to 12 neutral questions by steering strength, competence direction vs the mean of three random directions of equal norm; dashed lines are the system-prompt baselines."));
add(guideHead("Numbers"));
add(gbullet("Coherence 5.0 at every strength → α* = 8. FK by strength: −8: 9.2, −4: 9.9, 0: 9.2, +4: 11.2, +8: 12.1; random 10.0–10.5. Span +2.87 vs random −0.26 → +3.13 grade levels (SE 0.60; line 2). Judged level 1.17 → 1.67 → 2.58 (span +1.42 vs random +0.06). Prompt baselines: beginner 7.1 / 1.0; expert 11.4 / 2.25. [results_e4.json]"));
add(gbullet("H4b: steered 0/60 mention the reader's level; prompted 2/24 by rubric (3/24 counting the expert-prompt reply that calls the model 'a domain expert'). No qualitative difference."));
add(gbullet("Framing phrases ('simple way/explanation', 'simply', 'break it down', 'plain English') on full replies: prompt-beginner 10/12; steer −8 5/12; −4 4/12; 0 2/12; +4 0/12; +8 0/12; prompt-expert 0/12; random directions 1–3/12 at every strength."));
add(gbullet("Not closed: direction read at user-turn ends but added on assistant tokens too; 'belief about the user' vs 'plan for the reply's register' may be one direction at layer 22."));

// Could-be-wrong table
add(pb(), H1("How these results could be wrong, and what I checked"));
add(guide("His words: 'A really positive sign about an application is when I think of a way the results could be false, then discover you've already checked it.' Table copied from the kit; add a one-line intro of your own if you like."));
add(table(C.tkit, [1.3, 2.4, 2.4, 2.2], 15));

add(H1("Three things that went wrong"));
add(slot("Three short paragraphs in your words: (1) the blind judge at 37% and what it turned out to be; (2) the 200-token cap that manufactured sycophancy; (3) the merge-artifact control. Each: what you saw, what you asked, what you changed, what came out. ~200 words."));

add(H1("What I verified myself, and how"));
add(slot("Bullets. His example of strong evidence: 'I read 30 transcripts and confirmed the probe's positives were real.' ~120 words."));
add(guideHead("Facts"));
add(gbullet("30 QC dialogues read (10 per level) before any experiment; 6 random Codex novices read by the agent as a second reader (logbook §4c)."));
add(gbullet("All 12 uncorrected E3 replies + 9 random corrections read in full with the user's message: 21/21 final agreement; 2–3 verdicts changed after seeing the judge's label (the file showed it), so first-pass 18–19/21. All 14 distinct false claims checked false by hand."));
add(gbullet("48 E4 replies read blind: coherent 48/48; level mentions 0/24 steered, 3/24 prompted (judge 2/24); the framing-phrase observation came from this read and was then counted on the full replies."));
add(gbullet("One headline number recomputed by hand: ______ (fill in)."));
add(gbullet("Not done: human read of the 50 causal replies (judge coherence 4.90–4.98 is the only check there)."));

add(H1("How I used the agent, and what stayed mine"));
add(slot("A short, truthful paragraph. Yours: predictions, thresholds and floors; approving each pivot and each added control; reading the data and replies; the hand-checks; the decision to skip the causal read; the writing. The agent's: code, runs, figures, logging drafts, literature snippets, the outside review readers. Rules you gave it: never change parameters silently; name the dumbest alternative explanation after every result; print 5 random examples for every dataset; never write the summary. ~120 words."));

add(H1("Negative results"));
add(slot("Bullets, same prominence as the positives. ~120 words."));
add(guideHead("Facts"));
add(gbullet("H1b: no rise with turn index (96.6% from the first message; +3.4 vs a +8 line)."));
add(gbullet("H3b: confident voice does not double validation by the pre-registered absolute-gap rule (gap +0.09 [−0.02, +0.20]); ratio 3.1 passes, the rule does not."));
add(gbullet("H3c difference-in-differences +0.01 [−0.12, +0.14]: a null that supports the hypothesis (tone does not corrupt the internal truth score)."));
add(gbullet("H4b: no qualitative difference between steering and prompting on acknowledgment (0/60 vs 2/24)."));
add(gbullet("Raw cross-generator transfer 61–68% before the threshold-refit analysis explained it; by-verdict split absent at the claim-sentence position (+0.05 [−0.11, +0.23]); user-history-only control (+0.01) was a merge artifact."));

add(H1("Limitations"));
add(slot("Bullets, shortest first. ~150 words."));
add(guideHead("Facts"));
add(gbullet("One model (Qwen3-8B), one size; synthetic dialogues from two LLM writers with scripted personas."));
add(gbullet("Neutral-placeholder control is off-distribution; probe saturated (baselines 0.001 / 0.983), means are mostly per-dialogue flips."));
add(gbullet("E3 cells 45/46; exploratory split rests on 12 cases and one probe position; judge non-deterministic at the boundary (±3)."));
add(gbullet("Steering adds the direction on assistant tokens too; no position-restricted version; no steered-lifelong-expert condition (B is sufficiency only); causal human read not done."));
add(gbullet("Pooled probe could hold two writer-specific rules (argued against, not closed); prior-art check was abstracts and snippets only."));

add(H1("What I would do next"));
add(slot("4–5 bullets, each tied to a limitation. ~100 words."));
add(guideHead("Candidates"));
add(gbullet("Steered-lifelong-expert condition so B tests un-anchoring, not sufficiency."));
add(gbullet("Localize the self-anchor: ablate the direction only on assistant tokens during the reversal; replace the model's replies with level-neutral but responsive text."));
add(gbullet("Sizes and families (Qwen3 1.7B–32B, Llama, Gemma): does the asymmetry sign hold; does anchoring shrink with scale."));
add(gbullet("Real transcripts (WildChat / LMSYS) where users reveal expertise: does the probe's estimate predict reply complexity."));
add(gbullet("Scale the sycophancy-by-uncertainty split to hundreds of cases; test whether truth-direction steering reduces validation only in the uncertain bin."));

// Appendix
add(pb(), H1("Appendix"));
add(H2("A. Pre-registered predictions and outcomes (logbook §0, written before any experiment ran)"));
add(table(C.pred, [0.45, 2.2, 1.3, 3.2, 2.4, 2.2], 13));
add(P(C.notes.replace(/\*\*/g, "")));
add(H2("B. Observation → question → change → outcome (logbook §8)"));
add(table(C.t8, [0.8, 2.2, 2.0, 2.0, 2.4], 14));
add(H2("C. Quality-control record (logbook §4)"));
add(parasFrom(C.p4b)); add(parasFrom(C.p4c)); add(guide("Decision written before E1 ran (logbook §4e):")); add(parasFrom(C.p4e));
add(H2("D. Hand-checks (logbook §5 and the E4 read)"));
add(P("E3: every false-claim reply the judge labelled validate or hedge at 600 tokens (12; the entire 'not corrected' count) plus 9 random corrections; 14 distinct claims, each checked false by hand. Final agreement 21 of 21; the judge's label was visible in the file, and 2–3 verdicts were changed after comparing, so first-pass agreement is 18–19 of 21."));
add(table(C.t5, [0.4, 2.6, 1, 1.6, 1, 0.8], 15));
add(new Paragraph({ children: [new TextRun({ text: "▢ First-pass disagreements (which items, and your first label): ______", shading: { type: ShadingType.CLEAR, fill: "FFF2A8", color: "auto" } })], spacing: { before: 80, after: 120 } }));
add(P("E4 (48 replies, judge labels hidden): coherent 48/48; mentions the reader's level: steered 0/24 (judge 0/24, phrase list 0/24); prompted 3/24 (judge 2/24, phrase list 1/24). The third is the expert-prompt reply to the stocks question, 'As a domain expert, I can provide a nuanced analysis': the model calling itself the expert, which the rubric does not count, but a visible leak of the system prompt."));
add(H2("E. Pivot: the 200-token reply cap (logbook §6)"));
add(parasFrom(C.p6));
add(H2("F. External review against Nanda's own materials (logbook §7)"));
add(parasFrom(C.p7));
add(H2("G. Prior-art check (logbook §9; titles verified by hand before citing)"));
add(table(C.t9, [2.2, 3.4, 1.4, 2.6], 13));
add(H2("H. Prompts and parameters, verbatim"));
add(H3("Level definitions (config.py)"));
add(table([["Level", "Definition given to the writer"]].concat(Object.entries(C.levels).map(([k, v]) => [k, v])), [0.7, 4], 16));
add(H3("Topics and seed questions (config.py); held-out: " + C.heldout.join(", ")));
add(table([["Topic", "Seed question"]].concat(Object.entries(C.topics).map(([k, v]) => [k, v])), [1, 3], 15));
add(H3("Hard rules in every generation prompt (01c_generate_codex.py)"));
add(C.rules.split("\n").map(mono));
add(H3("Judge rubrics (judge_rubrics.md)"));
add(C.rub.filter(l => l.trim()).map(l => l.startsWith("#") ? new Paragraph({ children: runs(l.replace(/^#+\s*/, ""), { bold: true }), spacing: { before: 100, after: 40 } }) : mono(l)));
add(H3("Parameters"));
add(bullet("Subject model Qwen/Qwen3-8B, bfloat16, thinking disabled; activations at the last prompt token, all 37 hidden states, one forward pass per user turn."));
add(bullet("Competence probe: StandardScaler + LogisticRegression(C = 0.1, max_iter = 2000), trained on 8 topics; layer chosen by held-out accuracy (22); downstream probe trained on both writers. Truth probe: same recipe on 192 bare statements, layer 21."));
add(bullet("E2: 96 reversal dialogues, 6 user turns, switch at turn 4; baselines from main-set dialogues with ≥ 6 user turns at turn 6; 2,000 bootstrap resamples over dialogues."));
add(bullet("E3: neutral pre-filter; replies greedy, 600 tokens (first pass 200); judge Gemini 2.5 Pro via OpenRouter, reasoning effort low; Phi-4 second judge on 60."));
add(bullet("E4: direction = mean(expert) − mean(novice) at layer 22 from the Codex main set; forward hook on layer 22 output, added at every position; α ∈ {−8, −4, 0, 4, 8} × 0.1‖d‖; 3 random unit directions of equal norm; 12 prompts; α* rule fixed before the run; FK grade + judge (level, coherence, mentions_level) + phrase list."));
add(bullet("Causal follow-up: five conditions (n = 60 / 48 / 48 / 61 / 61); mean-ablation sets the projection on the unit direction to the dataset mean at every position; judge Gemini 2.5 Pro."));
add(H2("I. Time log"));
add(new Paragraph({ children: [new TextRun({ text: "▢ Toggl screenshot here, and the session table from logbook §1 (start, end, hours, what). State the project total and the executive-summary hours separately.", shading: { type: ShadingType.CLEAR, fill: "FFF2A8", color: "auto" } })], spacing: { after: 120 } }));
add(H2("J. Code and data"));
add(new Paragraph({ children: [new TextRun({ text: "▢ Link to the repository folder research/mats-application (commit __), after a secrets check. Scripts 01–14, results_*.json, figures/, logbook.md, judge_rubrics.md.", shading: { type: ShadingType.CLEAR, fill: "FFF2A8", color: "auto" } })], spacing: { after: 120 } }));

const doc = new Document({
  creator: "Yash Bansal", title: "MATS 12.0 application write-up (skeleton)",
  styles: {
    default: { document: { run: { font: "Arial", size: 21 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true, run: { size: 32, bold: true, color: "1F3864" }, paragraph: { spacing: { before: 360, after: 120 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true, run: { size: 26, bold: true, color: "1F3864" }, paragraph: { spacing: { before: 240, after: 80 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true, run: { size: 22, bold: true, color: "333333" }, paragraph: { spacing: { before: 180, after: 60 }, outlineLevel: 2 } },
    ],
  },
  numbering: { config: [{ reference: "bul", levels: [
    { level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 270 } } } },
    { level: 1, format: LevelFormat.BULLET, text: "–", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 1000, hanging: 270 } } } } ] }] },
  sections: [{ properties: { page: { size: { width: PAGE_W, height: 16838 }, margin: { top: MARGIN, bottom: MARGIN, left: MARGIN, right: MARGIN } } }, children: kids }],
});
Packer.toBuffer(doc).then(b => { fs.writeFileSync("MATS12_writeup_skeleton.docx", b); console.log("written", b.length, "bytes"); });
