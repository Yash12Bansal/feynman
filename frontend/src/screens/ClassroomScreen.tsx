import { Canvas } from "../engine/Canvas";
import { useVisualChannel } from "../livekit/useVisualChannel";

export function ClassroomScreen() {
  const { instructions } = useVisualChannel();

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
      <Canvas instructions={instructions} />
    </div>
  );
}
