import { useRef } from "react";
import type { ReactNode } from "react";
import type { Rect } from "./types";

export interface BoardElementProps {
  id: string;
  bounds: Rect;
  dataType?: string;
  children?: ReactNode;
}

export function BoardElement({
  id,
  bounds,
  dataType,
  children,
}: BoardElementProps) {
  const ref = useRef<HTMLDivElement>(null);

  return (
    <div
      ref={ref}
      className="wb-element"
      data-element-id={id}
      data-type={dataType}
      style={{
        left: bounds.x,
        top: bounds.y,
        width: bounds.width,
        height: bounds.height,
      }}
    >
      {children}
    </div>
  );
}
