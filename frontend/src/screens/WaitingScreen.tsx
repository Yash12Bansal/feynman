export function WaitingScreen() {
  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        flexDirection: "column",
        gap: "1rem",
      }}
    >
      <h1>Feynman</h1>
      <p>Waiting for session to start...</p>
    </div>
  );
}
