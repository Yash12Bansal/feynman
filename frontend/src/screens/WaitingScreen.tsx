interface WaitingScreenProps {
  onStart: () => void;
  isLoading: boolean;
}

export function WaitingScreen({ onStart, isLoading }: WaitingScreenProps) {
  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        flexDirection: "column",
        gap: "1.5rem",
        background: "#0a0a0a",
        color: "#fafafa",
      }}
    >
      <h1 style={{ fontSize: "3rem", fontWeight: 700, margin: 0 }}>Feynman</h1>
      <p style={{ fontSize: "1.1rem", color: "#888", margin: 0 }}>
        AI Teacher for the Classroom
      </p>
      <button
        onClick={onStart}
        disabled={isLoading}
        style={{
          marginTop: "1rem",
          padding: "0.75rem 2rem",
          fontSize: "1.1rem",
          fontWeight: 600,
          background: isLoading ? "#333" : "#3b82f6",
          color: "#fff",
          border: "none",
          borderRadius: "0.5rem",
          cursor: isLoading ? "not-allowed" : "pointer",
        }}
      >
        {isLoading ? "Connecting..." : "Start Class"}
      </button>
    </div>
  );
}
