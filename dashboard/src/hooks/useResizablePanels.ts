import { useState, useEffect, useCallback, useRef, type RefObject, type CSSProperties } from "react";

interface UseResizablePanelsOptions {
  /** Minimum pixel height for each panel (default 80) */
  minHeight?: number;
  /** Initial height ratios for each of the 3 panels (default [0.3, 0.4, 0.3]) */
  initialRatios?: [number, number, number];
}

interface DividerHandleProps {
  onMouseDown: (e: React.MouseEvent) => void;
  style: CSSProperties;
  className: string;
}

interface UseResizablePanelsReturn {
  /** Pixel heights for panels [top, middle, bottom] */
  heights: [number, number, number];
  /** Props to spread onto a divider div; index 0 = between panel 0 & 1, index 1 = between panel 1 & 2 */
  handleProps: (index: 0 | 1) => DividerHandleProps;
}

const DIVIDER_HEIGHT = 6;

export function useResizablePanels(
  containerRef: RefObject<HTMLDivElement | null>,
  options: UseResizablePanelsOptions = {},
): UseResizablePanelsReturn {
  const { minHeight = 80, initialRatios = [0.3, 0.4, 0.3] } = options;

  // split1 = pixel offset of first divider from top of container
  // split2 = pixel offset of second divider from top of container
  const [split1, setSplit1] = useState<number | null>(null);
  const [split2, setSplit2] = useState<number | null>(null);
  const [containerHeight, setContainerHeight] = useState(0);

  // Keep a ref to avoid stale closure in mousemove handlers
  const stateRef = useRef({ split1: 0, split2: 0, containerHeight: 0 });

  // ── Observe container height ──────────────────────────
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const observer = new ResizeObserver(([entry]) => {
      const h = entry.contentRect.height;
      setContainerHeight(h);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [containerRef]);

  // ── Initialize splits once we know the container height ──
  useEffect(() => {
    if (containerHeight > 0 && split1 === null) {
      const usable = containerHeight - 2 * DIVIDER_HEIGHT;
      const s1 = usable * initialRatios[0];
      const s2 = usable * (initialRatios[0] + initialRatios[1]) + DIVIDER_HEIGHT;
      setSplit1(s1);
      setSplit2(s2);
    }
  }, [containerHeight, split1, initialRatios]);

  // ── Keep stateRef up-to-date ──────────────────────────
  useEffect(() => {
    stateRef.current = {
      split1: split1 ?? 0,
      split2: split2 ?? 0,
      containerHeight,
    };
  }, [split1, split2, containerHeight]);

  // ── Clamping helper ───────────────────────────────────
  const clamp = useCallback(
    (s1: number, s2: number, totalH: number): [number, number] => {
      const maxS1 = s2 - DIVIDER_HEIGHT - minHeight; // panel 2 needs minHeight
      const minS1 = minHeight; // panel 1 needs minHeight
      let clampedS1 = Math.max(minS1, Math.min(maxS1, s1));

      const maxS2 = totalH - DIVIDER_HEIGHT - minHeight; // panel 3 needs minHeight
      const minS2 = clampedS1 + DIVIDER_HEIGHT + minHeight; // panel 2 needs minHeight
      let clampedS2 = Math.max(minS2, Math.min(maxS2, s2));

      // Re-clamp s1 in case s2 pushed it
      clampedS1 = Math.max(minHeight, Math.min(clampedS2 - DIVIDER_HEIGHT - minHeight, clampedS1));

      return [clampedS1, clampedS2];
    },
    [minHeight],
  );

  // ── Drag handler factory ──────────────────────────────
  const handleMouseDown = useCallback(
    (dividerIndex: 0 | 1) => (e: React.MouseEvent) => {
      e.preventDefault();
      const startY = e.clientY;
      const { split1: startSplit1, split2: startSplit2, containerHeight: totalH } = stateRef.current;

      const onMouseMove = (moveEvent: MouseEvent) => {
        const delta = moveEvent.clientY - startY;
        let newS1 = startSplit1;
        let newS2 = startSplit2;

        if (dividerIndex === 0) {
          newS1 = startSplit1 + delta;
        } else {
          newS2 = startSplit2 + delta;
        }

        const [cs1, cs2] = clamp(newS1, newS2, totalH);
        setSplit1(cs1);
        setSplit2(cs2);
      };

      const onMouseUp = () => {
        document.removeEventListener("mousemove", onMouseMove);
        document.removeEventListener("mouseup", onMouseUp);
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
      };

      document.addEventListener("mousemove", onMouseMove);
      document.addEventListener("mouseup", onMouseUp);
      document.body.style.cursor = "row-resize";
      document.body.style.userSelect = "none";
    },
    [clamp],
  );

  // ── Derive panel heights ──────────────────────────────
  // Before initialization, return equal thirds (or 0 if container not measured yet)
  let heights: [number, number, number];
  if (split1 === null || split2 === null || containerHeight === 0) {
    const third = containerHeight > 0 ? Math.floor((containerHeight - 2 * DIVIDER_HEIGHT) / 3) : 0;
    heights = [third, third, third];
  } else {
    heights = [
      split1,
      split2 - split1 - DIVIDER_HEIGHT,
      containerHeight - split2 - DIVIDER_HEIGHT,
    ];
  }

  // ── Divider props ─────────────────────────────────────
  const handleProps = useCallback(
    (index: 0 | 1): DividerHandleProps => ({
      onMouseDown: handleMouseDown(index),
      style: {
        height: DIVIDER_HEIGHT,
        flexShrink: 0,
      },
      className:
        "cursor-row-resize bg-slate-700/40 hover:bg-indigo-500/40 transition-colors",
    }),
    [handleMouseDown],
  );

  return { heights, handleProps };
}
