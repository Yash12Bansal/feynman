// Builds the MATS write-up skeleton: headings in Nanda's order, figures embedded,
// appendix tables copied from logbook.md / WRITEUP_KIT.md, and highlighted slots
// where Yash's prose goes. No prose is written for him.
const fs = require("fs");
const D = require("docx");
const { Document, Packer, Paragraph, TextRun, HeadingLevel, ImageRun, Table, TableRow, TableCell,
        WidthType, ShadingType, AlignmentType, PageBreak, LevelFormat, BorderStyle, TabStopType } = D;
const C = JSON.parse(fs.readFileSync(__dirname + "/content.json", "utf8"));

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
    if (l.startsWith("[…")) { out.push(new Paragraph({ children: runs(l, { italics: true, color: GREY, size: 19 }), indent: { left: 300 }, spacing: { after: 60 } })); continue; }
    out.push(inReply ? new Paragraph({ children: runs(l, { size: 20 }), indent: { left: 300 }, spacing: { after: 50 } }) : P(l));
  }
  return out;
}


// ---------- markdown draft -> document ----------
const MD = fs.readFileSync(process.argv[2] || "/home/user/feynman/research/mats-application/writeup_draft.md", "utf8").split("\n");
const TERMS = [["Term", "Meaning"],
  ["residual stream", "The running vector per token that every transformer layer reads from and writes to; Qwen3-8B has 36 layers and a 4096-dimensional stream. I read it at the last token of the prompt, the state from which the model would begin its reply."],
  ["linear probe", "A logistic-regression classifier fitted on stored residual-stream vectors while the model stays frozen. High accuracy on unseen topics means the information is linearly present, not that the model uses it."],
  ["P(expert)", "The probe's probability that the user is an expert (third class of novice / intermediate / expert)."],
  ["held-out topics", "Immunology, chess, statistics, networking: never used to train any probe; every accuracy reported is on these unless stated."],
  ["reversal dialogue", "Scripted 6-turn dialogue whose user behaves as one level for turns 1–3 and the other level for turns 4–6."],
  ["journey fraction", "How far the estimate has travelled from its own pre-switch value toward the lifelong baseline of the new level, at the same turn index; removes the 'less distance to travel' confound."],
  ["anchoring gap", "Lifelong-baseline P(expert) minus the reversal dialogue's final P(expert), both at turn 6."],
  ["history effect / writing effect", "History effect: the drop caused by keeping the pre-switch turns in context. Writing effect: how the post-switch turns score in isolation relative to lifelong dialogues."],
  ["difference-in-differences", "The confident-minus-hedged shift in the truth probe on false claims, minus the same shift on true claims; removes a probe that merely reads hedging words."],
  ["diff-of-means direction", "mean(expert activations) − mean(novice activations) at layer 22; added at every position during generation (steering) or projected to the dataset mean (mean-ablation)."],
  ["α*", "The largest steering strength whose mean coherence score stays ≥ 4/5 at both signs; fixed as a rule before the run (it was 8, in units of 0.1‖d‖)."],
  ["FK grade", "Flesch–Kincaid reading grade of a reply, an automatic proxy for pitch; the judge's 1–5 level score is the primary pitch measure."]];
const DATASETS = [["Dataset", "Size", "Shape", "Used for"],
  ["main (Codex / GPT)", "536 dialogues, 2,748 snapshots", "12 topics × 3 levels × ~15; 4–8 user turns; user never states level", "E1 probe train/test; baselines for E2"],
  ["main (Gemma-3-27B)", "540 dialogues, 2,846 snapshots", "same brief, second writer", "cross-writer control"],
  ["explicit", "144", "12 × 3 × 4; user states level in turn 1", "told vs shown competence (H1c)"],
  ["reversal", "96 (48 per direction)", "6 user turns; behaviour flips at turn 4", "E2 dynamics, anchoring, behavioural follow-up"],
  ["truth", "192 statements", "8 true + 8 false per topic, no dialogue", "truth probe training"],
  ["honesty", "190 (184 kept)", "12 topics × {true, false} × {confident, hedged}; claim in user turn 3", "E3"],
  ["linking", "284 (268 kept)", "142 claims (95 false, 47 true) × {novice-looking, expert-looking}; identical claim turn in both", "E5"]];
const TABLES = { terms: [TERMS, [1, 4], 17], datasets: [DATASETS, [1.3, 1.4, 2.6, 2], 17],
  pred: [C.pred, [0.45, 2.2, 1.3, 3.2, 2.4, 2.2], 13], t4a: [C.t4a, [1, 2, 2], 17], t4d: [C.t4d, [3, 1.2, 1.3, 1.3, 1, 1.1], 15],
  t5: [C.t5, [0.4, 2.6, 1, 1.6, 1, 0.8], 15], t8: [C.t8, [0.8, 2.2, 2.0, 2.0, 2.4], 14], t9: [C.t9, [2.2, 3.4, 1.4, 2.6], 13], tkit: [C.tkit, [1.3, 2.4, 2.4, 2.2], 15],
  tkit2: [C.tkit2, [1.5, 2.2, 2.8, 1.1], 14], terms2: [C.terms, [1.3, 4], 16], timelog: [C.timelog, [1, 5], 16] };
const yellow = (t, extra = {}) => new Paragraph({ children: [new TextRun({ text: t, shading: { type: ShadingType.CLEAR, fill: "FFF2A8", color: "auto" }, ...extra })], spacing: { after: 120 } });

const kids = []; const add = (...x) => kids.push(...x.flat());
let inComment = false, titleOpts = [], firstH1 = true;
for (let raw of MD) {
  const l = raw.replace(/\s+$/, "");
  if (l.startsWith("<!--")) { inComment = !l.endsWith("-->"); continue; }
  if (inComment) { if (l.endsWith("-->")) inComment = false; continue; }
  if (!l.trim()) continue;
  if (l.startsWith("NOTE:")) { const m = l.match(/^NOTE:\s*\((\w)\)\s*(.*)$/); if (m) titleOpts.push(m[2]); continue; }
  if (l === "# TITLE") { add(yellow("▢ TITLE — pick one or write your own:", { bold: true, size: 30 })); continue; }
  if (l.startsWith("TITLE: ")) { add(new Paragraph({ children: [new TextRun({ text: l.slice(7), bold: true, size: 30 })], spacing: { after: 140 } })); continue; }
  if (titleOpts.length && !l.startsWith("NOTE")) { for (const o of titleOpts) add(yellow("   " + o, { size: 26 })); titleOpts = []; }
  let m;
  if ((m = l.match(/^\{\{fig:([^|]+)\|(.*)\}\}$/))) { add(fig(m[1].trim(), /linking|bare/.test(m[1]) ? 5.8 : /anchoring_source|causal|history/.test(m[1]) ? 6.3 : /update_curves/.test(m[1]) ? 5.1 : 5.4)); add(caption(m[2])); continue; }
  if ((m = l.match(/^\{\{table:(\w+)\}\}$/))) { const [rows, w, fs_] = TABLES[m[1]]; add(table(rows, w, fs_)); add(new Paragraph({ spacing: { after: 80 } })); continue; }
  if (l === "{{examples}}") { add(examples(C.ex)); continue; }
  if (l === "{{examples2}}") { add(examples(C.ex2)); continue; }
  if (l === "{{levels}}") { add(table([["Level", "Definition"]].concat(Object.entries(C.levels)), [0.7, 4], 16)); continue; }
  if (l === "{{topics}}") { add(table([["Topic", "Seed question"]].concat(Object.entries(C.topics)), [1, 3], 15)); continue; }
  if (l === "{{rules}}") { add(C.rules.split("\n").map(mono)); add(new Paragraph({ spacing: { after: 80 } })); continue; }
  if (l === "{{rubrics}}") { add(C.rub.filter(x => x.trim()).map(x => x.startsWith("#") ? new Paragraph({ children: runs(x.replace(/^#+\s*/, ""), { bold: true }), spacing: { before: 100, after: 40 } }) : mono(x))); continue; }
  if ((m = l.match(/^\{\{paras:(\w+)\}\}$/))) { add(parasFrom(C[m[1]])); continue; }
  if (l.startsWith("# ")) { add(firstH1 ? H1(l.slice(2)) : [pb(), H1(l.slice(2))]); firstH1 = false; continue; }
  if (l.startsWith("## ")) { add(H2(l.slice(3))); continue; }
  if (l.startsWith("### ")) { add(H3(l.slice(4))); continue; }
  if (/^- /.test(l)) { add(bullet(l.slice(2))); continue; }
  if (/^\d+\. /.test(l)) { add(bullet(l.replace(/^\d+\. /, ""))); continue; }
  if (l.includes("______") || /^Hours:/.test(l)) { add(yellow(l)); continue; }
  if (l.startsWith("▢ ")) { add(yellow(l)); continue; }
  if (l.startsWith("Epistemic status:")) { add(new Paragraph({ children: runs(l, { italics: true }), spacing: { after: 160 } })); continue; }
  add(P(l));
}
const doc = new Document({
  creator: "Yash Bansal", title: "MATS 12.0 application write-up (draft)",
  styles: { default: { document: { run: { font: "Arial", size: 21 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true, run: { size: 32, bold: true, color: "1F3864" }, paragraph: { spacing: { before: 360, after: 120 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true, run: { size: 26, bold: true, color: "1F3864" }, paragraph: { spacing: { before: 240, after: 80 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true, run: { size: 22, bold: true, color: "333333" }, paragraph: { spacing: { before: 180, after: 60 }, outlineLevel: 2 } } ] },
  numbering: { config: [{ reference: "bul", levels: [
    { level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 270 } } } },
    { level: 1, format: LevelFormat.BULLET, text: "–", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 1000, hanging: 270 } } } } ] }] },
  sections: [{ properties: { page: { size: { width: PAGE_W, height: 16838 }, margin: { top: MARGIN, bottom: MARGIN, left: MARGIN, right: MARGIN } } }, children: kids }],
});
const OUT = process.argv[3] || __dirname + "/MATS12_writeup_draft.docx";
Packer.toBuffer(doc).then(b => { fs.writeFileSync(OUT, b); console.log("written", OUT, b.length, "bytes"); });
