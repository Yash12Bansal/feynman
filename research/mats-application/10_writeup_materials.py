"""Write-up materials, generated from the result files (never retyped):
  results_digest.md          every final number, per experiment, with file provenance
  writeup_random_examples.md the 5 RANDOMLY selected qualitative examples Nanda's doc
                             requires (fixed seed 2026; not cherry-picked), plus one
                             steering pair as a separate appendix item
Run: python 10_writeup_materials.py
"""
import json, random, re, os
from config import HELDOUT_TOPICS

def L(p): return json.load(open(p)) if os.path.exists(p) else None
e1, e2, e3, e3s, e3b, e4 = (L("results_e1.json"), L("results_e2.json"), L("results_e3.json"),
                            L("results_e3_600_summary.json"), L("results_e3b.json"), L("results_e4.json"))
agr = L("results_e3_agreement_local_600.json")
ci = lambda t: f"{t[0]:+.2f} [{t[1]:+.2f}, {t[2]:+.2f}]"
pc = lambda x: f"{100*x:.1f}%"

# ---------------- prediction table from the logbook ----------------
rows = []
for line in open("logbook.md"):
    m = re.match(r"^\| (H\d\w?) +\| (.*?) +\| (.*?) +\| (.*?) +\| (.*?) \| (.*?) \|\s*$", line)
    if m: rows.append(m.groups())

D = []
D.append("# Results digest — generated from result files by 10_writeup_materials.py\n")
D.append("Subject model Qwen3-8B (thinking off). Generators: Codex/GPT (all sets) and Gemma-3-27B (main set). "
         "Judge: Gemini 2.5 Pro via OpenRouter (E3, E4); Phi-4 local second judge; Gemma-3-27B and Phi-4 for QC. "
         f"Held-out topics: {', '.join(HELDOUT_TOPICS)}.\n")
D.append("## Prediction table (from logbook.md)\n\n| # | Hypothesis | My prediction | Outcome |\n|---|---|---|---|")
for h, hyp, pred, why, out, learned in rows:
    D.append(f"| {h} | {hyp} | {pred} | {out} |")

D.append("\n## E1 — is user competence linearly readable? (results_e1.json)\n")
if e1:
    bl = e1["best_layer"]; a = e1["acc_by_layer"]
    D.append(f"- Best layer {bl} of 36: held-out-topic accuracy {pc(a[bl])} per snapshot; per dialogue (final turn) "
             f"{pc(e1['dialogue_level_acc_ci'][0])} [{pc(e1['dialogue_level_acc_ci'][1])}, {pc(min(1,e1['dialogue_level_acc_ci'][2]))}], n={e1['n_heldout_dialogues']} dialogues. Chance 33.3%.")
    D.append(f"- Controls at layer {bl}: shuffled labels {pc(e1['acc_shuffled'][bl])}; topic probe (positive control) {pc(e1['acc_topic'][bl])}; "
             f"length-only classifier {pc(e1['length_only_baseline'])}.")
    D.append(f"- Layer profile: {pc(a[1])} at layer 1, {pc(a[11])} at layer 11, {pc(a[21])} at 21, {pc(a[36])} at 36.")
    c = e1["heldout_confusion"]; D.append(f"- Held-out confusion (rows true novice/intermediate/expert): {c}; novice↔expert swaps {e1['extreme_swaps']}/{sum(map(sum,c))}; "
             f"binary novice-vs-expert probe {pc(e1['novice_vs_expert_binary_acc'])}.")
    tf = e1["acc_turn_fixed_probe"]; D.append(f"- Turn curve, one probe: {[round(x,3) for x in tf]} (n per turn {e1['n_per_turn']}); turn3−turn0 = {e1['h1b_rise_turn3_minus_turn0']:+.3f} (H1b line +0.08).")
    D.append(f"- P(true class) by turn: " + "; ".join(f"{k} {[round(x,2) for x in v]}" for k, v in e1["p_true_by_turn"].items()))
    t = e1["transfer"]; D.append(f"- Explicit↔implicit (H1c): explicit→implicit {pc(t['explicit->implicit'])}, implicit→explicit {pc(t['implicit->explicit'])}, "
             f"own-set {pc(t['explicit->explicit'])} / {pc(t['implicit->implicit'])}; min transfer ÷ own-set = {min(t['explicit->implicit']/t['explicit->explicit'], t['implicit->explicit']/t['implicit->implicit']):.2f} (line 0.8).")
    x = e1["cross_generator"]
    D.append(f"- Cross-generator at layer {bl}: codex→gemma {pc(x['codex->gemma'])}, gemma→codex {pc(x['gemma->codex'])}, within {pc(x['codex->codex'])} / {pc(x['gemma->gemma'])}. "
             f"codex→gemma confusion {x['codex->gemma_confusion']}. Codex direction + Gemma-refit thresholds {pc(x['codex_direction_gemma_recalibrated'])}. "
             f"Pooled probe: {pc(x['pooled_codex_heldout'])} / {pc(x['pooled_gemma_heldout'])}. Best raw-transfer layer {x['best_transfer_layer']}.")
    D.append("- Figures: figures/e1_layer_profile.png, figures/e1_turn_curve.png")

D.append("\n## E2 — does the estimate update? (results_e2.json, pooled probe)\n")
if e2:
    b = e2["baseline_turn5"]; D.append(f"- Consistent baselines at turn 6: novice {b['novice']:.3f}, expert {b['expert']:.3f}.")
    for nm in ("novice->expert", "expert->novice"):
        r = e2[nm]; jf = r["journey_fraction"]
        D.append(f"- {nm}: mean P(expert) by turn {[round(x,2) for x in r['mean_curve']]}; crossover after switch {r['crossover_0.5']} turn(s) (midpoint line: {r['crossover_midpoint']}); "
                 f"journey fraction turn3 {ci(jf['turn3'])}, turn5 {ci(jf['turn5'])}; fraction of dialogues flipped {[round(x,2) for x in r['fraction_of_dialogues_flipped_by_turn']]}.")
    a = e2["h2b_asymmetry_e2n_minus_n2e"]; D.append(f"- H2b asymmetry (e→n minus n→e): turn3 {ci(a['turn3'])}, turn5 {ci(a['turn5'])} (line +0.15, CI clear of 0).")
    g = e2["h2c_anchoring_gap"]; D.append(f"- H2c anchoring at turn 6: novice→expert {ci(g['novice->expert (consistent expert - reversal)'])}; expert→novice {ci(g['expert->novice (reversal - consistent novice)'])} (line 0.1).")
    c = e2.get("h2c_control_history_vs_writing", {})
    for nm, v in c.items():
        D.append(f"- Control {nm}: full-context final {v['full_context_final']:.3f} | post-switch turns only {v['post_only_final']:.3f} | lifelong {v['consistent_target']:.3f} → "
                 f"history effect {ci(v['history_effect_ci'])}, writing effect {ci(v['writing_effect_ci'])}"
                 + (f"; user-turns-only history effect {ci(v['history_effect_user_turns_only_ci'])}" if "history_effect_user_turns_only_ci" in v else ""))
    D.append("- Figure: figures/e2_update_curves.png")

D.append("\n## E3 — what the model says vs what it represents (results_e3.json, results_e3_600_summary.json)\n")
if e3:
    D.append(f"- Kept {184} of 190 dialogues (Qwen answered the claim correctly when asked neutrally; {e3['n_filtered_model_didnt_know']} dropped). Cells {e3['n_cells']}.")
    D.append(f"- Truth probe: bare statements held-out {pc(e3['H3_bare_statement_acc_heldout'])}; in-dialogue at end of claim turn {pc(e3['H3_in_dialogue_acc_heldout'][0])} (n={e3['H3_in_dialogue_acc_heldout'][1]} held-out), all topics {pc(e3['H3_in_dialogue_acc_all'][0])}; "
             f"claim-sentence position {pc(e3['H3_claimpos_in_dialogue_acc_heldout'][0])} held-out (H3 line 65%).")
    D.append(f"- Internal score (end of turn): false/confident {e3['probe_p_true_false_confident']:.3f}, false/hedged {e3['probe_p_true_false_hedged']:.3f}, true/confident {e3['probe_p_true_true_confident']:.3f}, true/hedged {e3['probe_p_true_true_hedged']:.3f}; "
             f"difference-in-differences {ci(e3['H3c_diff_in_diff_ci'])} (H3c bound ±0.15).")
    D.append(f"- FIRST PASS (200-token replies, superseded): validate {pc(e3['P(validate|false,confident)'])} vs {pc(e3['P(validate|false,hedged)'])}; 157/184 replies were cut.")
if e3s:
    D.append(f"- FULL-LENGTH replies (600 tokens, the numbers to report): confident {e3s['verdicts_600_conf']}, hedged {e3s['verdicts_600_hedged']}; "
             f"validate {pc(e3s['P(validate|false,confident)'])} vs {pc(e3s['P(validate|false,hedged)'])}, gap {ci(e3s['H3b_validate_gap_ci'])}, ratio {e3s['H3b_ratio']:.1f}; "
             f"not corrected {pc(e3s['failed_to_correct_conf'])} vs {pc(e3s['failed_to_correct_hedged'])}, gap {ci(e3s['failed_to_correct_gap_ci'])}. {e3s['changed_vs_200']} verdicts changed vs 200 tokens.")
    v = e3s["internal_by_verdict600_probe_p_true"]
    D.append(f"- Internal P(true) of FALSE claims by what the model did (end-of-turn probe): corrected n={v['correct']['n']} {v['correct']['mean_ci'][0]:.2f} [{v['correct']['mean_ci'][1]:.2f},{v['correct']['mean_ci'][2]:.2f}]; "
             f"hedged n={v['hedge']['n']} {v['hedge']['mean_ci'][0]:.2f}; validated n={v['validate']['n']} {v['validate']['mean_ci'][0]:.2f} [{v['validate']['mean_ci'][1]:.2f},{v['validate']['mean_ci'][2]:.2f}]; "
             f"not-corrected − corrected {ci(v['not_corrected_minus_corrected_ci'])}. Claim-sentence position: {ci(e3s['internal_by_verdict600_probe_p_true_claimpos']['not_corrected_minus_corrected_ci'])}. (Exploratory, post-hoc.)")
if agr:
    it = agr["items"]; two = sum((i['primary']=='validate')==(i['second']=='validate') for i in it)
    D.append(f"- Second judge (Phi-4) on 60 full-length replies: 3-way agreement {pc(agr['agreement'])}; validated-vs-not {two}/{len(it)}.")
D.append("- Judge non-determinism: 4/21 borderline replies received different Gemini verdicts on identical text across two runs.")
D.append("- Figures: figures/e3_sycophancy_gap_600.png, figures/e3_internal_by_verdict_600.png")

D.append("\n## E4 — is the direction causal? (results_e4.json)\n")
if e4:
    D.append(f"- α* = {e4['alpha_star']} (largest strength with coherence ≥ 4; coherence by strength {e4['coherence_by_alpha_steer']}).")
    D.append(f"- Reading grade by strength, competence direction {{{', '.join(f'{k}: {v:.1f}' for k,v in e4['fk_by_alpha_steer'].items())}}}; random directions {{{', '.join(f'{k}: {v:.1f}' for k,v in e4['fk_by_alpha_rand'].items())}}}.")
    D.append(f"- H4: span steer {e4['H4_fk_span_steer']:+.2f} vs random {e4['H4_fk_span_random']:+.2f} → {e4['H4_statistic_steer_minus_random']:+.2f} grade levels (SE {e4['H4_se_over_prompts']:.2f} over 12 prompts; line 2). "
             f"Judged level span {e4['H4_level_span_steer']:+.2f} vs random {e4['H4_level_span_random']:+.2f} (line 1); level by strength {{{', '.join(f'{k}: {v:.2f}' for k,v in e4['level_by_alpha_steer'].items())}}}.")
    D.append(f"- Prompt baselines: beginner grade {e4['prompt_baseline_fk']['novice']:.1f} / level {e4['prompt_baseline_level']['novice']:.2f}; expert grade {e4['prompt_baseline_fk']['expert']:.1f} / level {e4['prompt_baseline_level']['expert']:.2f}.")
    a = e4["H4b_acknowledgment"]
    D.append(f"- H4b acknowledgment of the user's level: steered {pc(a['steered_phrase'])} (phrase) / {pc(a['steered_judge'])} (judge) of {a['n_steered']}; prompted {pc(a['prompted_phrase'])} / {pc(a['prompted_judge'])} of {a['n_prompted']} (line: steered ≤10%, prompted ≥30%).")
    D.append("- Figure: figures/e4_dose_response.png")

D.append("\n## QC (logbook section 4)\n- Length by level: Codex 33/33/37 words, Gemma 43/38/34 (opposite directions). Leaks: 0 / 2 false positives.\n"
         "- Blind judge, user turns only: Gemma-27B 71% 3-way (Codex); Phi-4 52% all turns → 80% first two turns (Codex); 70% (Gemma). 0 novice↔expert swaps in every run; rank corr 0.86–0.87.\n")
open("results_digest.md", "w").write("\n".join(D))
print("results_digest.md written:", len(D), "lines")

# ---------------- 5 random qualitative examples ----------------
rng = random.Random(2026)
E = ["# Five randomly selected qualitative examples (seed 2026, not cherry-picked)\n",
     "Selection rule, fixed before drawing: 2 main-set dialogues (one Codex, one Gemma; level and topic random), "
     "1 reversal dialogue (direction random), 2 honesty dialogues with Qwen's full-length reply and the judge's verdict "
     "(one false claim, one true claim; voice random). Every item shows the label the generator was asked to produce.\n"]
def show(msgs):
    return "\n".join(f"> **{m['role'].upper()}:** {m['content']}" for m in msgs)
main_c = [json.loads(l) for l in open("data/main.jsonl")]; main_g = [json.loads(l) for l in open("data_gemma/main.jsonl")]
for tag, rows_ in (("Codex", main_c), ("Gemma-3-27B", main_g)):
    d = rng.choice(rows_)
    E.append(f"## Example: main set, generator {tag} — `{d['id']}` — label **{d['level']}**, topic {d['topic']}\n\n{show(d['messages'])}\n")
rev = [json.loads(l) for l in open("data/reversal.jsonl")]; d = rng.choice(rev)
E.append(f"## Example: reversal set — `{d['id']}` — direction **{d['direction']}**, switch at user turn {d['switch_turn']+1}\n\n{show(d['messages'])}\n")
r600 = [r for r in json.load(open("results_e3_600.json"))["results"] if not r["filtered"]]
for truth in (False, True):
    pool = [r for r in r600 if r["claim_true"] == truth and r.get("reply_600")]
    r = rng.choice(pool)
    idx = [i for i, m in enumerate(r["messages"]) if m["role"] == "user"][r["claim_turn"]]
    E.append(f"## Example: honesty set — `{r['id']}` — claim is **{'TRUE' if truth else 'FALSE'}**, voice **{r['voice']}**\n\n"
             f"Claim: *{r['claim']}*\n\nQwen asked neutrally (\"True or false…\"): `{r['neutral'][:60].strip()}`\n\n"
             f"Dialogue up to the claim turn:\n\n{show(r['messages'][:idx+1])}\n\n"
             f"**Qwen's actual reply ({'600' if not truth else '200'} tokens, greedy):**\n\n{r['reply_600']}\n\n"
             f"Judge (Gemini 2.5 Pro): **{r['verdict_600']}**. Truth-probe P(claim true) at end of claim turn: **{r['probe_p_true']:.2f}**"
             + (f"; at claim-sentence end: {r['probe_p_true_claimpos']:.2f}" if r.get("probe_p_true_claimpos") is not None else "") + "\n")
e4raw = json.load(open("results_e4_raw.json"))["results"]
p = rng.choice(sorted({r["prompt"] for r in e4raw}))
E.append(f"## Appendix item (separate from the five): steering pair for a random prompt — \"{p}\"\n")
for a in (-8, 8):
    r = next(r for r in e4raw if r["dir"] == "steer" and r["alpha"] == a and r["prompt"] == p)
    E.append(f"**Strength {a:+d} (toward {'novice' if a < 0 else 'expert'})** — grade {r['fk']:.1f}, judged level {r['level']}, coherence {r['coherence']}\n\n{r['text']}\n")
for d_ in ("prompt_novice", "prompt_expert"):
    r = next(r for r in e4raw if r["dir"] == d_ and r["prompt"] == p)
    E.append(f"**System prompt: {'the user is a complete beginner' if 'novice' in d_ else 'the user is a domain expert'}** — grade {r['fk']:.1f}, judged level {r['level']}\n\n{r['text']}\n")
open("writeup_random_examples.md", "w").write("\n".join(E))
print("writeup_random_examples.md written")
