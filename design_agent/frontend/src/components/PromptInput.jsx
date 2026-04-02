import React from 'react';

function PromptInput({ prompt, setPrompt, onGenerate, loading, error, history, onHistoryClick }) {
  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      onGenerate();
    }
  };

  return (
    <div className="prompt-input-container">
      <div className="input-section">
        <label htmlFor="prompt-textarea">Describe your diagram</label>
        <textarea
          id="prompt-textarea"
          className="prompt-textarea"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="e.g. Plot sin(x) and cos(x) from -2pi to 2pi..."
          rows={5}
          disabled={loading}
        />
        <button
          className="generate-btn"
          onClick={() => onGenerate()}
          disabled={loading || !prompt.trim()}
        >
          {loading ? (
            <span className="btn-loading">
              <span className="spinner" />
              Generating...
            </span>
          ) : (
            'Generate'
          )}
        </button>
        <span className="shortcut-hint">Ctrl+Enter to generate</span>
      </div>

      {error && (
        <div className="error-display">
          <strong>Error:</strong> {error}
        </div>
      )}

      {history.length > 0 && (
        <div className="history-section">
          <h3>History</h3>
          <ul className="history-list">
            {history.map((item, idx) => (
              <li
                key={idx}
                className="history-item"
                onClick={() => onHistoryClick(item)}
                title={item.prompt}
              >
                {item.prompt.length > 60
                  ? item.prompt.substring(0, 60) + '...'
                  : item.prompt}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default PromptInput;
