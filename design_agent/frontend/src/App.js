import React, { useState, useCallback } from "react";
import DiagramRenderer from "./components/DiagramRenderer";
import PromptInput from "./components/PromptInput";
import "./styles/App.css";

const API_URL = "http://localhost:8000/api/generate";

const MODELS = [
  { id: "opus", label: "Claude Opus" },
  { id: "sonnet", label: "Claude Sonnet" },
  { id: "haiku", label: "Claude Haiku" },
];

function App() {
  const [prompt, setPrompt] = useState("");
  const [model, setModel] = useState("opus");
  const [diagramSpec, setDiagramSpec] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [history, setHistory] = useState([]);
  const [showJson, setShowJson] = useState(false);

  const handleGenerate = useCallback(
    async (inputPrompt) => {
      const text = inputPrompt || prompt;
      if (!text.trim()) return;

      setLoading(true);
      setError(null);

      try {
        const resp = await fetch(API_URL, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ prompt: text, model }),
        });

        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          throw new Error(err.detail || `Server error: ${resp.status}`);
        }

        const data = await resp.json();
        const spec = data.diagram || data;
        setDiagramSpec(spec);
        setHistory((prev) => [{ prompt: text, spec }, ...prev]);
      } catch (err) {
        setError(err.message || "Failed to generate diagram");
      } finally {
        setLoading(false);
      }
    },
    [prompt, model],
  );

  const handleHistoryClick = useCallback((item) => {
    setPrompt(item.prompt);
    setDiagramSpec(item.spec);
    setError(null);
  }, []);

  return (
    <div className="app">
      <header className="app-header">
        <h1>Diagram Agent</h1>
      </header>
      <div className="app-body">
        <div className="left-panel">
          <div className="model-selector">
            <label>Model</label>
            <select value={model} onChange={(e) => setModel(e.target.value)}>
              {MODELS.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label}
                </option>
              ))}
            </select>
          </div>
          <PromptInput
            prompt={prompt}
            setPrompt={setPrompt}
            onGenerate={handleGenerate}
            loading={loading}
            error={error}
            history={history}
            onHistoryClick={handleHistoryClick}
          />
        </div>
        <div className="right-panel">
          {diagramSpec ? (
            <div>
              <DiagramRenderer spec={diagramSpec} />
              <button
                onClick={() => setShowJson(!showJson)}
                className="json-toggle"
              >
                {showJson ? "Hide JSON" : "Show JSON"}
              </button>
              {showJson && (
                <pre className="json-viewer">
                  {JSON.stringify(diagramSpec, null, 2)}
                </pre>
              )}
            </div>
          ) : (
            <div className="placeholder">
              <p>
                {loading
                  ? "Generating diagram..."
                  : "Enter a prompt to generate a diagram"}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default App;
