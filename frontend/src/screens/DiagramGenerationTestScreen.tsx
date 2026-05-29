// TODO(DEADCODE): file unused in active pipelines (precompute-gen / lecture-playback / ask-feynman). See docs/engineering/13-redundant-code-audit.md Group 1. Safe to delete.
// /**
//  * Diagram-generation testbed at `#/diagram_generation_test`.
//  *
//  * Plugin-driven experimental lab: the strategy list, model list, and per-
//  * strategy options come from `GET /api/diagtest/strategies` so adding a new
//  * backend strategy automatically surfaces in the UI.
//  *
//  * Layout: three columns — control / canvas / inspect. Reuses
//  * `DesignDiagramContent` and `SlideAnnotationLayer` from the main board so
//  * the testbed exercises the same renderer the production agent emits to.
//  *
//  * Not part of the production app — strictly experimentation.
//  */

// import {
//   useCallback,
//   useEffect,
//   useMemo,
//   useRef,
//   useState,
//   type CSSProperties,
// } from "react";
// import { DesignDiagramContent } from "../engine/whiteboard/content/DesignDiagramContent";
// import { SlideAnnotationLayer } from "../engine/whiteboard/split/SlideAnnotationLayer";
// import { StrategyOptionsForm } from "../diagram-lab/StrategyOptionsForm";
// import {
//   fetchHistory,
//   fetchMathsLibrary,
//   fetchStrategies,
//   injectAnnotation,
//   runStrategy,
// } from "../diagram-lab/api";
// import type {
//   AnnotationInjectResponse,
//   HistoryEntry,
//   LabDiagramSpec,
//   MathsLibrary,
//   RunResponse,
//   StrategyDescriptor,
// } from "../diagram-lab/types";
// import type {
//   AnnotationInstruction,
//   DrawDesignDiagramInstruction,
//   ElementMeta,
// } from "../types/visuals";

// type InspectTab = "spec" | "raw" | "metadata" | "annotate";
// type AnnotateMode = "prompt" | "form";

// // ── Helpers ────────────────────────────────────────────────────

// function isTikzSpec(
//   spec: LabDiagramSpec | null | undefined,
// ): spec is LabDiagramSpec & {
//   _tikz_svg: string;
// } {
//   return Boolean(spec?._tikz_svg);
// }

// function specElementsForAnnotation(
//   spec: LabDiagramSpec,
// ): readonly { id: string; role?: string }[] {
//   const dictionary = (spec.dictionary ?? {}) as Record<
//     string,
//     { role?: string }
//   >;
//   const elements = (spec.elements ?? []) as readonly {
//     id?: string;
//     type?: string;
//   }[];
//   const seen = new Set<string>();
//   const out: { id: string; role?: string }[] = [];
//   for (const el of elements) {
//     if (el.id && !seen.has(el.id)) {
//       out.push({ id: el.id, role: dictionary[el.id]?.role });
//       seen.add(el.id);
//     }
//   }
//   for (const [id, meta] of Object.entries(dictionary)) {
//     if (!seen.has(id)) {
//       out.push({ id, role: meta.role });
//       seen.add(id);
//     }
//   }
//   return out;
// }

// function fmtMs(ms: number | null | undefined): string {
//   if (ms == null) return "—";
//   if (ms < 1000) return `${Math.round(ms)} ms`;
//   return `${(ms / 1000).toFixed(2)} s`;
// }

// // ── DiagramStage — renders normal spec OR raw TikZ SVG, with overlay ──

// interface DiagramStageProps {
//   readonly spec: LabDiagramSpec | null;
//   readonly annotations: readonly AnnotationInstruction[];
//   readonly loading: boolean;
// }

// function DiagramStage({ spec, annotations, loading }: DiagramStageProps) {
//   const stageRef = useRef<HTMLDivElement | null>(null);

//   if (!spec && !loading) {
//     return (
//       <div style={stageEmpty}>
//         <div style={stageEmptyText}>
//           Pick a strategy and prompt on the left, then hit Run.
//         </div>
//       </div>
//     );
//   }

//   const width = spec?.width ?? 900;
//   const height = spec?.height ?? 650;

//   return (
//     <div style={stageWrap}>
//       <div ref={stageRef} style={stageInner} data-testid="diagram-stage">
//         {loading && <div style={loadingBar}>generating…</div>}
//         {spec ? (
//           isTikzSpec(spec) ? (
//             <div
//               style={tikzWrap}
//               // The SVG comes from pdflatex output we generated ourselves —
//               // not user input — so dangerouslySetInnerHTML is acceptable here.
//               dangerouslySetInnerHTML={{ __html: spec._tikz_svg }}
//             />
//           ) : (
//             <DesignDiagramContent
//               instruction={
//                 {
//                   type: "draw_design_diagram",
//                   element_id: "diagram-lab-spec",
//                   title: spec.title ?? "",
//                   spec: spec as DrawDesignDiagramInstruction["spec"],
//                 } as DrawDesignDiagramInstruction
//               }
//             />
//           )
//         ) : null}
//         {spec && !isTikzSpec(spec) && (
//           <SlideAnnotationLayer
//             viewBox={`0 0 ${width} ${height}`}
//             dictionary={
//               spec.dictionary as Record<string, ElementMeta> | undefined
//             }
//             annotations={annotations}
//             stageRef={stageRef}
//           />
//         )}
//       </div>
//     </div>
//   );
// }

// // ── LatencyBanner ──────────────────────────────────────────

// interface LatencyBannerProps {
//   readonly result: RunResponse["result"] | null;
// }

// function LatencyBanner({ result }: LatencyBannerProps) {
//   if (!result) {
//     return <div style={latencyEmpty}>No run yet.</div>;
//   }
//   const t = result.timing;
//   return (
//     <div style={latencyWrap}>
//       <span style={latencyItem}>
//         <span style={latencyKey}>total</span>
//         <span style={latencyValStrong}>{fmtMs(t.total_ms)}</span>
//       </span>
//       <span style={latencyDot}>·</span>
//       <span style={latencyItem}>
//         <span style={latencyKey}>first token</span>
//         <span style={latencyVal}>{fmtMs(t.first_token_ms)}</span>
//       </span>
//       <span style={latencyDot}>·</span>
//       <span style={latencyItem}>
//         <span style={latencyKey}>LLM</span>
//         <span style={latencyVal}>{fmtMs(t.llm_ms)}</span>
//       </span>
//       {t.sandbox_ms != null && (
//         <>
//           <span style={latencyDot}>·</span>
//           <span style={latencyItem}>
//             <span style={latencyKey}>sandbox</span>
//             <span style={latencyVal}>{fmtMs(t.sandbox_ms)}</span>
//           </span>
//         </>
//       )}
//       {t.render_ms != null && (
//         <>
//           <span style={latencyDot}>·</span>
//           <span style={latencyItem}>
//             <span style={latencyKey}>render</span>
//             <span style={latencyVal}>{fmtMs(t.render_ms)}</span>
//           </span>
//         </>
//       )}
//       {Object.entries(t.extra).map(([k, v]) => (
//         <span key={k} style={latencyItem}>
//           <span style={latencyDot}>·</span>
//           <span style={latencyKey}>{k}</span>
//           <span style={latencyVal}>{fmtMs(v)}</span>
//         </span>
//       ))}
//       <span style={latencyDot}>·</span>
//       <span style={latencyItem}>
//         <span style={latencyKey}>model</span>
//         <span style={latencyVal}>{result.model_used}</span>
//       </span>
//     </div>
//   );
// }

// // ── AnnotationTester ──────────────────────────────────────

// interface AnnotationTesterProps {
//   readonly spec: LabDiagramSpec | null;
//   readonly onAdd: (instr: AnnotationInstruction) => void;
//   readonly onClear: () => void;
//   readonly annotationCount: number;
// }

// function AnnotationTester({
//   spec,
//   onAdd,
//   onClear,
//   annotationCount,
// }: AnnotationTesterProps) {
//   const [mode, setMode] = useState<AnnotateMode>("prompt");
//   const [intent, setIntent] = useState("circle the hypotenuse");
//   const [busy, setBusy] = useState(false);
//   const [lastResp, setLastResp] = useState<AnnotationInjectResponse | null>(
//     null,
//   );
//   const [err, setErr] = useState<string | null>(null);

//   // Form mode state
//   const [kind, setKind] = useState<
//     "pin_label" | "draw_callout" | "bracket" | "highlight_pulse"
//   >("highlight_pulse");
//   const [targetMode, setTargetMode] = useState<"id" | "role">("id");
//   const [targetValue, setTargetValue] = useState("");
//   const [secondaryTarget, setSecondaryTarget] = useState("");
//   const [text, setText] = useState("");
//   const [color, setColor] = useState("cyan");

//   const elements = useMemo(
//     () => (spec ? specElementsForAnnotation(spec) : []),
//     [spec],
//   );
//   const allRoles = useMemo(
//     () =>
//       Array.from(
//         new Set(elements.map((e) => e.role).filter((r): r is string => !!r)),
//       ),
//     [elements],
//   );

//   useEffect(() => {
//     if (!targetValue && elements[0]) {
//       setTargetValue(
//         targetMode === "role"
//           ? (elements[0].role ?? elements[0].id)
//           : elements[0].id,
//       );
//     }
//   }, [elements, targetMode, targetValue]);

//   const runPromptAnnotation = useCallback(async () => {
//     if (!spec || !intent.trim()) return;
//     setBusy(true);
//     setErr(null);
//     try {
//       const resp = await injectAnnotation({ spec, intent });
//       setLastResp(resp);
//       onAdd(resp.instruction);
//     } catch (e) {
//       setErr(e instanceof Error ? e.message : String(e));
//     } finally {
//       setBusy(false);
//     }
//   }, [spec, intent, onAdd]);

//   const submitForm = useCallback(() => {
//     if (!spec) return;
//     const id = `lab-${Date.now()}`;
//     let instr: AnnotationInstruction;
//     if (kind === "highlight_pulse") {
//       instr = {
//         type: "highlight_pulse",
//         element_id: id,
//         target_element_id: targetMode === "id" ? targetValue : "",
//         target: { kind: targetMode, value: targetValue },
//         color,
//         duration_ms: 1200,
//       } as AnnotationInstruction;
//     } else if (kind === "pin_label") {
//       instr = {
//         type: "pin_label",
//         element_id: id,
//         target_element_id: targetMode === "id" ? targetValue : "",
//         target: { kind: targetMode, value: targetValue },
//         text: text || targetValue,
//         position: "above",
//       } as AnnotationInstruction;
//     } else if (kind === "draw_callout") {
//       instr = {
//         type: "draw_callout",
//         element_id: id,
//         target_element_id: targetMode === "id" ? targetValue : "",
//         target: { kind: targetMode, value: targetValue },
//         text: text || `note about ${targetValue}`,
//         direction: "right",
//       } as AnnotationInstruction;
//     } else {
//       instr = {
//         type: "bracket",
//         element_id: id,
//         element_a_id: targetValue,
//         element_b_id: secondaryTarget,
//         label: text || "",
//         side: "above",
//       } as AnnotationInstruction;
//     }
//     onAdd(instr);
//   }, [
//     spec,
//     kind,
//     targetMode,
//     targetValue,
//     secondaryTarget,
//     text,
//     color,
//     onAdd,
//   ]);

//   return (
//     <div style={annotateWrap}>
//       <div style={annotateModeRow}>
//         <button
//           style={{ ...modeBtn, ...(mode === "prompt" ? modeBtnActive : null) }}
//           onClick={() => setMode("prompt")}
//         >
//           prompt-driven
//         </button>
//         <button
//           style={{ ...modeBtn, ...(mode === "form" ? modeBtnActive : null) }}
//           onClick={() => setMode("form")}
//         >
//           explicit form
//         </button>
//         <div style={{ flex: 1 }} />
//         <button style={modeBtnMuted} onClick={onClear}>
//           clear ({annotationCount})
//         </button>
//       </div>

//       {mode === "prompt" ? (
//         <>
//           <label style={inspectLabel}>
//             Free-text intent (routed through haiku)
//           </label>
//           <textarea
//             style={textarea}
//             rows={3}
//             value={intent}
//             onChange={(e) => setIntent(e.target.value)}
//             placeholder="e.g. circle the hypotenuse and add a label '10 cm'"
//           />
//           <button
//             style={runBtn}
//             disabled={!spec || busy || !intent.trim()}
//             onClick={runPromptAnnotation}
//           >
//             {busy ? "thinking…" : "Inject annotation"}
//           </button>
//           {err && <div style={errBox}>{err}</div>}
//           {lastResp && (
//             <>
//               <div style={injectMeta}>
//                 latency {fmtMs(lastResp.latency_ms)} · chose{" "}
//                 {lastResp.chosen_target
//                   ? `${lastResp.chosen_target.kind}=${lastResp.chosen_target.value}`
//                   : "—"}
//               </div>
//               <pre style={injectPre}>
//                 {JSON.stringify(lastResp.instruction, null, 2)}
//               </pre>
//             </>
//           )}
//         </>
//       ) : (
//         <div style={formGrid}>
//           <label style={inspectLabel}>Annotation kind</label>
//           <select
//             style={selectInput}
//             value={kind}
//             onChange={(e) => setKind(e.target.value as typeof kind)}
//           >
//             <option value="highlight_pulse">highlight_pulse</option>
//             <option value="pin_label">pin_label</option>
//             <option value="draw_callout">draw_callout</option>
//             <option value="bracket">bracket (needs two targets)</option>
//           </select>

//           <label style={inspectLabel}>Target by</label>
//           <div style={btnRow}>
//             <button
//               style={{
//                 ...modeBtn,
//                 ...(targetMode === "id" ? modeBtnActive : null),
//               }}
//               onClick={() => setTargetMode("id")}
//             >
//               id
//             </button>
//             <button
//               style={{
//                 ...modeBtn,
//                 ...(targetMode === "role" ? modeBtnActive : null),
//               }}
//               onClick={() => setTargetMode("role")}
//             >
//               role
//             </button>
//           </div>

//           <label style={inspectLabel}>
//             {kind === "bracket" ? "Target A" : "Target"}
//           </label>
//           {targetMode === "id" ? (
//             <select
//               style={selectInput}
//               value={targetValue}
//               onChange={(e) => setTargetValue(e.target.value)}
//             >
//               <option value="">(pick…)</option>
//               {elements.map((e) => (
//                 <option key={e.id} value={e.id}>
//                   {e.id}
//                   {e.role ? ` — ${e.role}` : ""}
//                 </option>
//               ))}
//             </select>
//           ) : (
//             <select
//               style={selectInput}
//               value={targetValue}
//               onChange={(e) => setTargetValue(e.target.value)}
//             >
//               <option value="">(pick…)</option>
//               {allRoles.map((r) => (
//                 <option key={r} value={r}>
//                   {r}
//                 </option>
//               ))}
//             </select>
//           )}

//           {kind === "bracket" && (
//             <>
//               <label style={inspectLabel}>Target B</label>
//               <select
//                 style={selectInput}
//                 value={secondaryTarget}
//                 onChange={(e) => setSecondaryTarget(e.target.value)}
//               >
//                 <option value="">(pick…)</option>
//                 {elements.map((e) => (
//                   <option key={e.id} value={e.id}>
//                     {e.id}
//                   </option>
//                 ))}
//               </select>
//             </>
//           )}

//           {(kind === "pin_label" ||
//             kind === "draw_callout" ||
//             kind === "bracket") && (
//             <>
//               <label style={inspectLabel}>Text</label>
//               <input
//                 style={selectInput}
//                 type="text"
//                 value={text}
//                 onChange={(e) => setText(e.target.value)}
//                 placeholder={
//                   kind === "pin_label" ? "short label" : "longer note"
//                 }
//               />
//             </>
//           )}

//           {kind === "highlight_pulse" && (
//             <>
//               <label style={inspectLabel}>Color</label>
//               <select
//                 style={selectInput}
//                 value={color}
//                 onChange={(e) => setColor(e.target.value)}
//               >
//                 <option value="cyan">cyan</option>
//                 <option value="amber">amber</option>
//                 <option value="green">green</option>
//                 <option value="magenta">magenta</option>
//               </select>
//             </>
//           )}

//           <div />
//           <button
//             style={runBtn}
//             disabled={
//               !spec || !targetValue || (kind === "bracket" && !secondaryTarget)
//             }
//             onClick={submitForm}
//           >
//             Add annotation
//           </button>
//         </div>
//       )}
//     </div>
//   );
// }

// // ── InspectPanel ──────────────────────────────────────────

// interface InspectPanelProps {
//   readonly result: RunResponse["result"] | null;
//   readonly spec: LabDiagramSpec | null;
//   readonly annotations: readonly AnnotationInstruction[];
//   readonly onAddAnnotation: (instr: AnnotationInstruction) => void;
//   readonly onClearAnnotations: () => void;
// }

// function InspectPanel({
//   result,
//   spec,
//   annotations,
//   onAddAnnotation,
//   onClearAnnotations,
// }: InspectPanelProps) {
//   const [tab, setTab] = useState<InspectTab>("annotate");

//   return (
//     <div style={inspectPanel}>
//       <div style={tabRow}>
//         {(["spec", "raw", "metadata", "annotate"] as InspectTab[]).map((t) => (
//           <button
//             key={t}
//             style={{ ...tabBtn, ...(tab === t ? tabBtnActive : null) }}
//             onClick={() => setTab(t)}
//           >
//             {t}
//           </button>
//         ))}
//       </div>
//       <div style={tabContent}>
//         {tab === "spec" && (
//           <pre style={preWide}>
//             {spec ? JSON.stringify(spec, null, 2) : "(no spec)"}
//           </pre>
//         )}
//         {tab === "raw" && (
//           <pre style={preWide}>{result?.raw_output ?? "(no run yet)"}</pre>
//         )}
//         {tab === "metadata" && (
//           <pre style={preWide}>
//             {result
//               ? JSON.stringify(
//                   {
//                     model_used: result.model_used,
//                     timing: result.timing,
//                     warnings: result.warnings,
//                     metadata: result.metadata,
//                   },
//                   null,
//                   2,
//                 )
//               : "(no run yet)"}
//           </pre>
//         )}
//         {tab === "annotate" && (
//           <AnnotationTester
//             spec={spec}
//             onAdd={onAddAnnotation}
//             onClear={onClearAnnotations}
//             annotationCount={annotations.length}
//           />
//         )}
//       </div>
//     </div>
//   );
// }

// // ── Main screen ───────────────────────────────────────────

// export function DiagramGenerationTestScreen() {
//   const [strategies, setStrategies] = useState<StrategyDescriptor[] | null>(
//     null,
//   );
//   const [strategyId, setStrategyId] = useState<string>("python_dsl");
//   const [model, setModel] = useState<string>("sonnet");
//   const [options, setOptions] = useState<Record<string, unknown>>({});
//   const [prompt, setPrompt] = useState<string>("");
//   const [library, setLibrary] = useState<MathsLibrary | null>(null);
//   const [history, setHistory] = useState<HistoryEntry[]>([]);

//   const [running, setRunning] = useState(false);
//   const [result, setResult] = useState<RunResponse["result"] | null>(null);
//   const [err, setErr] = useState<string | null>(null);

//   const [annotations, setAnnotations] = useState<
//     readonly AnnotationInstruction[]
//   >([]);

//   // Load strategies + library on mount
//   useEffect(() => {
//     fetchStrategies()
//       .then(setStrategies)
//       .catch((e) => setErr(String(e)));
//     fetchMathsLibrary()
//       .then(setLibrary)
//       .catch(() => {});
//     fetchHistory()
//       .then(setHistory)
//       .catch(() => {});
//   }, []);

//   const selectedStrategy = useMemo(
//     () => strategies?.find((s) => s.id === strategyId) ?? null,
//     [strategies, strategyId],
//   );

//   // Reset options when strategy changes — defaults come from the descriptor
//   useEffect(() => {
//     if (selectedStrategy) {
//       setOptions(selectedStrategy.options_defaults);
//       if (!selectedStrategy.supports_models.includes(model)) {
//         setModel(selectedStrategy.default_model);
//       }
//     }
//   }, [selectedStrategy, model]);

//   const doRun = useCallback(async () => {
//     if (!selectedStrategy || !prompt.trim()) return;
//     setRunning(true);
//     setErr(null);
//     setAnnotations([]);
//     try {
//       const resp = await runStrategy({
//         strategy_id: selectedStrategy.id,
//         model,
//         prompt,
//         options,
//       });
//       setResult(resp.result);
//       fetchHistory()
//         .then(setHistory)
//         .catch(() => {});
//     } catch (e) {
//       setErr(e instanceof Error ? e.message : String(e));
//     } finally {
//       setRunning(false);
//     }
//   }, [selectedStrategy, model, prompt, options]);

//   const addAnnotation = useCallback((instr: AnnotationInstruction) => {
//     setAnnotations((prev) => [...prev, instr]);
//   }, []);
//   const clearAnnotations = useCallback(() => setAnnotations([]), []);

//   const useLibraryPrompt = useCallback((p: string) => {
//     setPrompt(p);
//     setAnnotations([]);
//   }, []);

//   const reloadHistoryEntry = useCallback(async (entry: HistoryEntry) => {
//     try {
//       const resp = await fetch(`/api/diagtest/history/${entry.run_id}`);
//       if (!resp.ok) return;
//       const full = (await resp.json()) as {
//         result?: RunResponse["result"];
//         prompt: string;
//         strategy_id: string;
//         model: string;
//       };
//       if (full.result) {
//         setResult(full.result);
//         setStrategyId(full.strategy_id);
//         setModel(full.model);
//         setPrompt(full.prompt);
//         setAnnotations([]);
//       }
//     } catch {
//       /* ignore */
//     }
//   }, []);

//   // ── Render ──────────────────────────────────────────────

//   return (
//     <div style={container}>
//       {/* ── Left: control panel ─────────────────────────── */}
//       <aside style={sidebar}>
//         <header style={headerCss}>
//           <h2 style={titleCss}>Diagram Lab</h2>
//           <span style={subtitleCss}>experimental · /api/diagtest</span>
//         </header>

//         <section style={section}>
//           <div style={sectionLabel}>Strategy</div>
//           {!strategies ? (
//             <div style={hintText}>loading…</div>
//           ) : (
//             <select
//               style={fullSelect}
//               value={strategyId}
//               onChange={(e) => setStrategyId(e.target.value)}
//             >
//               {strategies.map((s) => (
//                 <option
//                   key={s.id}
//                   value={s.id}
//                   disabled={!s.availability.available}
//                 >
//                   {s.display_name}{" "}
//                   {s.availability.available ? "" : `· ${s.availability.reason}`}
//                 </option>
//               ))}
//             </select>
//           )}
//           {selectedStrategy && (
//             <div style={strategyDesc}>{selectedStrategy.description}</div>
//           )}
//         </section>

//         <section style={section}>
//           <div style={sectionLabel}>Model</div>
//           <div style={modelRow}>
//             {selectedStrategy?.supports_models.map((m) => (
//               <button
//                 key={m}
//                 style={{
//                   ...modelBtn,
//                   ...(model === m ? modelBtnActive : null),
//                 }}
//                 onClick={() => setModel(m)}
//               >
//                 {m}
//               </button>
//             ))}
//           </div>
//         </section>

//         <section style={section}>
//           <div style={sectionLabel}>Options</div>
//           {selectedStrategy && (
//             <StrategyOptionsForm
//               schema={selectedStrategy.options_schema}
//               values={options}
//               onChange={setOptions}
//             />
//           )}
//         </section>

//         <section style={section}>
//           <div style={sectionLabel}>Prompt</div>
//           <textarea
//             style={promptTextarea}
//             rows={6}
//             placeholder="e.g. Draw a right triangle with…"
//             value={prompt}
//             onChange={(e) => setPrompt(e.target.value)}
//           />
//           <button
//             style={runBtnBig}
//             disabled={running || !prompt.trim() || !selectedStrategy}
//             onClick={doRun}
//           >
//             {running ? "running…" : "Run"}
//           </button>
//           {err && <div style={errBox}>{err}</div>}
//         </section>

//         <section style={section}>
//           <div style={sectionLabel}>Maths library</div>
//           {library?.groups.map((g) => (
//             <details key={g.topic} style={libGroup}>
//               <summary style={libGroupSummary}>{g.topic}</summary>
//               {g.prompts.map((p) => (
//                 <button
//                   key={p.id}
//                   style={libPromptBtn}
//                   onClick={() => useLibraryPrompt(p.prompt)}
//                   title={p.prompt}
//                 >
//                   {p.label}
//                 </button>
//               ))}
//             </details>
//           ))}
//         </section>

//         <section style={section}>
//           <div style={sectionLabel}>Recent runs</div>
//           {history.slice(0, 12).map((h) => (
//             <button
//               key={h.run_id}
//               style={historyBtn}
//               onClick={() => reloadHistoryEntry(h)}
//               title={h.prompt}
//             >
//               <span style={historyHead}>
//                 <span style={historyStrat}>{h.strategy_id}</span>
//                 <span style={h.success ? historyTimeOk : historyTimeFail}>
//                   {h.success ? fmtMs(h.total_ms) : "fail"}
//                 </span>
//               </span>
//               <span style={historyPrompt}>{h.prompt.slice(0, 70)}</span>
//             </button>
//           ))}
//         </section>
//       </aside>

//       {/* ── Center: diagram canvas ──────────────────────── */}
//       <main style={canvasColumn}>
//         <div style={canvasArea}>
//           <DiagramStage
//             spec={result?.spec ?? null}
//             annotations={annotations}
//             loading={running}
//           />
//         </div>
//         <LatencyBanner result={result} />
//       </main>

//       {/* ── Right: inspect ─────────────────────────────── */}
//       <InspectPanel
//         result={result}
//         spec={result?.spec ?? null}
//         annotations={annotations}
//         onAddAnnotation={addAnnotation}
//         onClearAnnotations={clearAnnotations}
//       />
//     </div>
//   );
// }

// // ── Styles ────────────────────────────────────────────────

// const container: CSSProperties = {
//   display: "grid",
//   gridTemplateColumns: "320px 1fr 380px",
//   width: "100%",
//   height: "100vh",
//   background: "#050508",
//   color: "#f0f0f0",
//   fontFamily: "Inter, system-ui, -apple-system, sans-serif",
// };

// const sidebar: CSSProperties = {
//   borderRight: "1px solid #15151f",
//   background: "#0a0a12",
//   padding: 16,
//   display: "flex",
//   flexDirection: "column",
//   gap: 16,
//   overflowY: "auto",
// };

// const headerCss: CSSProperties = {
//   display: "flex",
//   flexDirection: "column",
//   gap: 2,
//   paddingBottom: 12,
//   borderBottom: "1px solid #15151f",
// };

// const titleCss: CSSProperties = {
//   margin: 0,
//   fontSize: 17,
//   fontWeight: 700,
//   letterSpacing: "-0.02em",
// };

// const subtitleCss: CSSProperties = {
//   fontSize: 10,
//   color: "#6b7280",
//   fontFamily: "JetBrains Mono, SF Mono, monospace",
//   letterSpacing: "0.04em",
// };

// const section: CSSProperties = {
//   display: "flex",
//   flexDirection: "column",
//   gap: 8,
// };

// const sectionLabel: CSSProperties = {
//   fontSize: 10,
//   fontWeight: 600,
//   textTransform: "uppercase",
//   color: "#6b7280",
//   letterSpacing: "0.08em",
// };

// const hintText: CSSProperties = {
//   fontSize: 12,
//   color: "#6b7280",
//   fontStyle: "italic",
// };

// const fullSelect: CSSProperties = {
//   width: "100%",
//   padding: "8px 10px",
//   background: "#0f0f17",
//   border: "1px solid #2a2a3a",
//   borderRadius: 6,
//   color: "#e8e8ee",
//   fontSize: 12,
//   fontFamily: "inherit",
// };

// const strategyDesc: CSSProperties = {
//   fontSize: 11,
//   color: "#9ca3af",
//   lineHeight: 1.5,
//   padding: "4px 0",
// };

// const modelRow: CSSProperties = {
//   display: "flex",
//   gap: 4,
//   flexWrap: "wrap",
// };

// const modelBtn: CSSProperties = {
//   padding: "5px 10px",
//   border: "1px solid #2a2a3a",
//   borderRadius: 5,
//   background: "#15151f",
//   color: "#9ca3af",
//   cursor: "pointer",
//   fontSize: 11,
//   fontFamily: "JetBrains Mono, SF Mono, monospace",
// };

// const modelBtnActive: CSSProperties = {
//   borderColor: "#7fd4ff",
//   background: "rgba(127, 212, 255, 0.12)",
//   color: "#7fd4ff",
// };

// const promptTextarea: CSSProperties = {
//   width: "100%",
//   padding: 10,
//   background: "#0f0f17",
//   border: "1px solid #2a2a3a",
//   borderRadius: 6,
//   color: "#e8e8ee",
//   fontSize: 13,
//   fontFamily: "inherit",
//   resize: "vertical",
//   lineHeight: 1.4,
//   boxSizing: "border-box",
// };

// const runBtnBig: CSSProperties = {
//   padding: "10px 14px",
//   border: "1px solid #7fd4ff",
//   borderRadius: 6,
//   background: "rgba(127, 212, 255, 0.12)",
//   color: "#7fd4ff",
//   cursor: "pointer",
//   fontSize: 13,
//   fontWeight: 600,
// };

// const runBtn: CSSProperties = {
//   padding: "8px 12px",
//   border: "1px solid #7fd4ff",
//   borderRadius: 5,
//   background: "rgba(127, 212, 255, 0.12)",
//   color: "#7fd4ff",
//   cursor: "pointer",
//   fontSize: 12,
//   fontWeight: 600,
// };

// const errBox: CSSProperties = {
//   padding: 8,
//   background: "rgba(239, 68, 68, 0.1)",
//   border: "1px solid rgba(239, 68, 68, 0.3)",
//   borderRadius: 4,
//   color: "#fca5a5",
//   fontSize: 11,
//   fontFamily: "JetBrains Mono, SF Mono, monospace",
//   whiteSpace: "pre-wrap",
//   wordBreak: "break-word",
// };

// const libGroup: CSSProperties = {
//   background: "#0f0f17",
//   borderRadius: 6,
//   padding: "6px 8px",
// };

// const libGroupSummary: CSSProperties = {
//   cursor: "pointer",
//   fontSize: 11,
//   color: "#cbd5e1",
//   textTransform: "uppercase",
//   letterSpacing: "0.04em",
// };

// const libPromptBtn: CSSProperties = {
//   display: "block",
//   width: "100%",
//   textAlign: "left",
//   padding: "4px 6px",
//   marginTop: 4,
//   background: "transparent",
//   border: "none",
//   color: "#9ca3af",
//   cursor: "pointer",
//   fontSize: 11,
//   borderRadius: 3,
// };

// const historyBtn: CSSProperties = {
//   display: "flex",
//   flexDirection: "column",
//   width: "100%",
//   textAlign: "left",
//   padding: "6px 8px",
//   background: "#0f0f17",
//   border: "1px solid #15151f",
//   borderRadius: 4,
//   color: "#cbd5e1",
//   cursor: "pointer",
//   fontSize: 11,
// };

// const historyHead: CSSProperties = {
//   display: "flex",
//   justifyContent: "space-between",
//   marginBottom: 2,
// };

// const historyStrat: CSSProperties = {
//   color: "#7fd4ff",
//   fontFamily: "JetBrains Mono, SF Mono, monospace",
//   fontSize: 10,
// };

// const historyTimeOk: CSSProperties = {
//   color: "#86efac",
//   fontFamily: "JetBrains Mono, SF Mono, monospace",
//   fontSize: 10,
// };

// const historyTimeFail: CSSProperties = {
//   color: "#fca5a5",
//   fontFamily: "JetBrains Mono, SF Mono, monospace",
//   fontSize: 10,
// };

// const historyPrompt: CSSProperties = {
//   color: "#9ca3af",
//   fontSize: 10,
//   overflow: "hidden",
//   textOverflow: "ellipsis",
//   whiteSpace: "nowrap",
// };

// // ── canvas column ──

// const canvasColumn: CSSProperties = {
//   display: "flex",
//   flexDirection: "column",
//   minWidth: 0,
//   minHeight: 0,
// };

// const canvasArea: CSSProperties = {
//   flex: 1,
//   minHeight: 0,
//   display: "flex",
//   alignItems: "center",
//   justifyContent: "center",
//   padding: 24,
//   background: "radial-gradient(circle at 50% 40%, #15151f 0%, #050508 60%)",
// };

// const stageWrap: CSSProperties = {
//   position: "relative",
//   width: "100%",
//   height: "100%",
//   display: "flex",
//   alignItems: "center",
//   justifyContent: "center",
// };

// const stageInner: CSSProperties = {
//   position: "relative",
//   maxWidth: "100%",
//   maxHeight: "100%",
//   display: "flex",
//   alignItems: "center",
//   justifyContent: "center",
// };

// const stageEmpty: CSSProperties = {
//   display: "flex",
//   alignItems: "center",
//   justifyContent: "center",
//   width: "100%",
//   height: "100%",
// };

// const stageEmptyText: CSSProperties = {
//   color: "#6b7280",
//   fontSize: 13,
//   fontStyle: "italic",
// };

// const tikzWrap: CSSProperties = {
//   display: "flex",
//   alignItems: "center",
//   justifyContent: "center",
// };

// const loadingBar: CSSProperties = {
//   position: "absolute",
//   top: 8,
//   left: "50%",
//   transform: "translateX(-50%)",
//   padding: "4px 10px",
//   background: "rgba(127, 212, 255, 0.15)",
//   border: "1px solid rgba(127, 212, 255, 0.4)",
//   borderRadius: 12,
//   color: "#7fd4ff",
//   fontSize: 11,
//   fontFamily: "JetBrains Mono, SF Mono, monospace",
//   zIndex: 10,
// };

// const latencyWrap: CSSProperties = {
//   padding: "8px 16px",
//   background: "#0a0a12",
//   borderTop: "1px solid #15151f",
//   display: "flex",
//   gap: 8,
//   alignItems: "center",
//   fontSize: 11,
//   fontFamily: "JetBrains Mono, SF Mono, monospace",
//   flexWrap: "wrap",
// };

// const latencyEmpty: CSSProperties = {
//   padding: "8px 16px",
//   background: "#0a0a12",
//   borderTop: "1px solid #15151f",
//   color: "#6b7280",
//   fontSize: 11,
//   fontStyle: "italic",
// };

// const latencyItem: CSSProperties = {
//   display: "flex",
//   gap: 4,
//   alignItems: "baseline",
// };
// const latencyKey: CSSProperties = { color: "#6b7280" };
// const latencyVal: CSSProperties = { color: "#cbd5e1" };
// const latencyValStrong: CSSProperties = { color: "#7fd4ff", fontWeight: 600 };
// const latencyDot: CSSProperties = { color: "#374151" };

// // ── inspect column ──

// const inspectPanel: CSSProperties = {
//   borderLeft: "1px solid #15151f",
//   background: "#0a0a12",
//   display: "flex",
//   flexDirection: "column",
//   minWidth: 0,
// };

// const tabRow: CSSProperties = {
//   display: "flex",
//   borderBottom: "1px solid #15151f",
// };

// const tabBtn: CSSProperties = {
//   flex: 1,
//   padding: "8px 4px",
//   background: "transparent",
//   border: "none",
//   color: "#6b7280",
//   cursor: "pointer",
//   fontSize: 11,
//   textTransform: "uppercase",
//   letterSpacing: "0.05em",
//   borderBottom: "2px solid transparent",
// };

// const tabBtnActive: CSSProperties = {
//   color: "#7fd4ff",
//   borderBottomColor: "#7fd4ff",
// };

// const tabContent: CSSProperties = {
//   flex: 1,
//   overflow: "auto",
//   padding: 12,
//   minHeight: 0,
// };

// const preWide: CSSProperties = {
//   margin: 0,
//   fontSize: 10,
//   lineHeight: 1.4,
//   color: "#cbd5e1",
//   whiteSpace: "pre-wrap",
//   wordBreak: "break-word",
//   fontFamily: "JetBrains Mono, SF Mono, monospace",
// };

// const annotateWrap: CSSProperties = {
//   display: "flex",
//   flexDirection: "column",
//   gap: 8,
// };

// const annotateModeRow: CSSProperties = {
//   display: "flex",
//   gap: 6,
//   alignItems: "center",
// };

// const modeBtn: CSSProperties = {
//   padding: "4px 10px",
//   border: "1px solid #2a2a3a",
//   borderRadius: 4,
//   background: "#15151f",
//   color: "#9ca3af",
//   cursor: "pointer",
//   fontSize: 11,
//   fontFamily: "JetBrains Mono, SF Mono, monospace",
// };

// const modeBtnActive: CSSProperties = {
//   borderColor: "#7fd4ff",
//   background: "rgba(127, 212, 255, 0.12)",
//   color: "#7fd4ff",
// };

// const modeBtnMuted: CSSProperties = {
//   padding: "4px 10px",
//   border: "1px solid #2a2a3a",
//   borderRadius: 4,
//   background: "transparent",
//   color: "#6b7280",
//   cursor: "pointer",
//   fontSize: 10,
// };

// const inspectLabel: CSSProperties = {
//   fontSize: 10,
//   fontWeight: 600,
//   textTransform: "uppercase",
//   color: "#6b7280",
//   letterSpacing: "0.06em",
// };

// const textarea: CSSProperties = {
//   width: "100%",
//   padding: 8,
//   background: "#0f0f17",
//   border: "1px solid #2a2a3a",
//   borderRadius: 4,
//   color: "#e8e8ee",
//   fontSize: 12,
//   fontFamily: "inherit",
//   resize: "vertical",
//   boxSizing: "border-box",
// };

// const injectMeta: CSSProperties = {
//   fontSize: 10,
//   color: "#6b7280",
//   fontFamily: "JetBrains Mono, SF Mono, monospace",
//   padding: "2px 0",
// };

// const injectPre: CSSProperties = {
//   margin: 0,
//   fontSize: 10,
//   lineHeight: 1.4,
//   color: "#cbd5e1",
//   background: "#0f0f17",
//   border: "1px solid #1e1e30",
//   borderRadius: 4,
//   padding: 8,
//   whiteSpace: "pre-wrap",
//   wordBreak: "break-word",
//   fontFamily: "JetBrains Mono, SF Mono, monospace",
// };

// const formGrid: CSSProperties = {
//   display: "grid",
//   gridTemplateColumns: "minmax(0, 1fr)",
//   gap: 6,
// };

// const btnRow: CSSProperties = { display: "flex", gap: 4 };

// const selectInput: CSSProperties = {
//   width: "100%",
//   padding: "6px 8px",
//   background: "#0f0f17",
//   border: "1px solid #2a2a3a",
//   borderRadius: 4,
//   color: "#e8e8ee",
//   fontSize: 12,
//   fontFamily: "inherit",
//   boxSizing: "border-box",
// };
