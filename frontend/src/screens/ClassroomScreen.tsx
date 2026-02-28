import { VisualScene } from "../engine/VisualScene";
import { useVisualChannel } from "../livekit/useVisualChannel";

export function ClassroomScreen() {
  const { instructions } = useVisualChannel();

  return <VisualScene instructions={instructions} />;
}
