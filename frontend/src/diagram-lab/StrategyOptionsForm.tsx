// TODO(DEADCODE): file unused in active pipelines (precompute-gen / lecture-playback / ask-feynman). See docs/engineering/13-redundant-code-audit.md Group 1. Safe to delete.
// /**
//  * Render a small form from a strategy's Pydantic JSON Schema.
//  *
//  * Pydantic exports `properties: { foo: {type, default, minimum, maximum, ...} }`
//  * plus `$defs` for Literal types (rendered as `allOf: [{$ref}]` on the field).
//  * We resolve $ref one level deep so Literal enums become <select>s. Anything
//  * exotic falls back to a text input — strategies should keep options simple
//  * enough that this is fine.
//  */

// import { useCallback, useMemo } from "react";
// import type { JsonSchema } from "./types";

// interface Field {
//   readonly name: string;
//   readonly type: "number" | "string" | "boolean" | "enum";
//   readonly default: unknown;
//   readonly description?: string;
//   readonly minimum?: number;
//   readonly maximum?: number;
//   readonly enumValues?: readonly string[];
// }

// function resolveRef(schema: JsonSchema, ref: string): JsonSchema | null {
//   const prefix = "#/$defs/";
//   if (!ref.startsWith(prefix)) return null;
//   const key = ref.slice(prefix.length);
//   return schema.$defs?.[key] ?? null;
// }

// function fieldsFromSchema(schema: JsonSchema): readonly Field[] {
//   const out: Field[] = [];
//   const props = schema.properties ?? {};
//   for (const [name, raw] of Object.entries(props)) {
//     let prop: JsonSchema = raw;
//     // Pydantic emits `allOf: [{$ref}]` for Literal types
//     if (prop.allOf?.length) {
//       const ref = (prop.allOf[0] as { $ref?: string }).$ref;
//       if (ref) {
//         const resolved = resolveRef(schema, ref);
//         if (resolved) prop = { ...resolved, default: prop.default };
//       }
//     }
//     if (prop.enum) {
//       out.push({
//         name,
//         type: "enum",
//         default: prop.default,
//         description: prop.description,
//         enumValues: prop.enum.map(String),
//       });
//       continue;
//     }
//     if (prop.type === "integer" || prop.type === "number") {
//       out.push({
//         name,
//         type: "number",
//         default: prop.default,
//         description: prop.description,
//         minimum: prop.minimum,
//         maximum: prop.maximum,
//       });
//       continue;
//     }
//     if (prop.type === "boolean") {
//       out.push({
//         name,
//         type: "boolean",
//         default: prop.default,
//         description: prop.description,
//       });
//       continue;
//     }
//     out.push({
//       name,
//       type: "string",
//       default: prop.default,
//       description: prop.description,
//     });
//   }
//   return out;
// }

// interface Props {
//   readonly schema: JsonSchema;
//   readonly values: Record<string, unknown>;
//   readonly onChange: (next: Record<string, unknown>) => void;
// }

// export function StrategyOptionsForm({ schema, values, onChange }: Props) {
//   const fields = useMemo(() => fieldsFromSchema(schema), [schema]);

//   const set = useCallback(
//     (name: string, value: unknown) => {
//       onChange({ ...values, [name]: value });
//     },
//     [values, onChange],
//   );

//   if (fields.length === 0) {
//     return <div style={empty}>No options for this strategy.</div>;
//   }

//   return (
//     <div style={wrap}>
//       {fields.map((f) => {
//         const v = values[f.name] ?? f.default;
//         return (
//           <div key={f.name} style={row}>
//             <label style={label}>
//               {f.name}
//               {f.description ? (
//                 <span style={hint} title={f.description}>
//                   &nbsp;ⓘ
//                 </span>
//               ) : null}
//             </label>
//             {f.type === "number" ? (
//               <input
//                 style={input}
//                 type="number"
//                 step={Number.isInteger(f.default as number) ? 1 : 0.05}
//                 value={String(v)}
//                 min={f.minimum}
//                 max={f.maximum}
//                 onChange={(e) => set(f.name, parseFloat(e.target.value))}
//               />
//             ) : f.type === "enum" ? (
//               <select
//                 style={input}
//                 value={String(v)}
//                 onChange={(e) => set(f.name, e.target.value)}
//               >
//                 {f.enumValues?.map((opt) => (
//                   <option key={opt} value={opt}>
//                     {opt}
//                   </option>
//                 ))}
//               </select>
//             ) : f.type === "boolean" ? (
//               <input
//                 type="checkbox"
//                 checked={Boolean(v)}
//                 onChange={(e) => set(f.name, e.target.checked)}
//               />
//             ) : (
//               <input
//                 style={input}
//                 type="text"
//                 value={String(v ?? "")}
//                 onChange={(e) => set(f.name, e.target.value)}
//               />
//             )}
//           </div>
//         );
//       })}
//     </div>
//   );
// }

// const wrap: React.CSSProperties = {
//   display: "flex",
//   flexDirection: "column",
//   gap: 8,
// };
// const row: React.CSSProperties = {
//   display: "flex",
//   alignItems: "center",
//   justifyContent: "space-between",
//   gap: 8,
// };
// const label: React.CSSProperties = {
//   fontSize: 11,
//   color: "#a1a1aa",
//   fontFamily: "JetBrains Mono, SF Mono, monospace",
// };
// const hint: React.CSSProperties = {
//   color: "#6b7280",
//   cursor: "help",
// };
// const input: React.CSSProperties = {
//   width: 100,
//   padding: "4px 6px",
//   background: "#0f0f17",
//   border: "1px solid #2a2a3a",
//   borderRadius: 4,
//   color: "#e8e8ee",
//   fontSize: 11,
//   fontFamily: "JetBrains Mono, SF Mono, monospace",
// };
// const empty: React.CSSProperties = {
//   fontSize: 12,
//   color: "#6b7280",
//   fontStyle: "italic",
// };
