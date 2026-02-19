import { Canvas } from "../engine/Canvas";

export function ClassroomScreen() {
  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <Canvas />
    </div>
  );
}
