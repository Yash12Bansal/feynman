import { useState } from "react";
import type { CreateSessionRequest } from "../lib/api";

interface WaitingScreenProps {
  onStart: (body?: CreateSessionRequest) => void;
  isLoading: boolean;
}

export function WaitingScreen({ onStart, isLoading }: WaitingScreenProps) {
  const [topic, setTopic] = useState("");
  const [subject, setSubject] = useState("physics");

  const handleStart = () => {
    onStart(topic ? { topic, subject } : undefined);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && topic && !isLoading) handleStart();
  };

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

      <div
        style={{
          marginTop: "1rem",
          display: "flex",
          flexDirection: "column",
          gap: "0.75rem",
          width: "320px",
        }}
      >
        <input
          type="text"
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Topic (e.g. Kinematics)"
          autoFocus
          style={{
            padding: "0.75rem 1rem",
            fontSize: "1rem",
            background: "#1a1a1a",
            color: "#fafafa",
            border: "1px solid #333",
            borderRadius: "0.5rem",
            outline: "none",
          }}
        />
        <select
          value={subject}
          onChange={(e) => setSubject(e.target.value)}
          style={{
            padding: "0.75rem 1rem",
            fontSize: "1rem",
            background: "#1a1a1a",
            color: "#fafafa",
            border: "1px solid #333",
            borderRadius: "0.5rem",
            outline: "none",
          }}
        >
          <option value="physics">Physics</option>
          <option value="math">Math</option>
          <option value="chemistry">Chemistry</option>
          <option value="biology">Biology</option>
        </select>
      </div>

      <button
        onClick={handleStart}
        disabled={isLoading || !topic}
        style={{
          marginTop: "0.5rem",
          padding: "0.75rem 2rem",
          fontSize: "1.1rem",
          fontWeight: 600,
          background: isLoading || !topic ? "#333" : "#3b82f6",
          color: "#fff",
          border: "none",
          borderRadius: "0.5rem",
          cursor: isLoading || !topic ? "not-allowed" : "pointer",
        }}
      >
        {isLoading ? "Connecting..." : "Start Class"}
      </button>
    </div>
  );
}
