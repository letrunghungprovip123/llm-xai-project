"use client";

import { useCallback, useMemo, useState } from "react";

type CursorState = {
  epoch: object;
  cursor: string | undefined;
  history: Array<string | undefined>;
};

const emptyState = (epoch: object): CursorState => ({ epoch, cursor: undefined, history: [] });

export function useCursorPager(resetKey: string) {
  const epoch = useMemo(() => ({ resetKey }), [resetKey]);
  const [state, setState] = useState<CursorState>(() => emptyState(epoch));
  const current = state.epoch === epoch ? state : emptyState(epoch);

  const next = useCallback((nextCursor?: string | null) => {
    if (!nextCursor) return;
    setState((previous) => {
      const base = previous.epoch === epoch ? previous : emptyState(epoch);
      return { epoch, cursor: nextCursor, history: [...base.history, base.cursor] };
    });
  }, [epoch]);

  const back = useCallback(() => {
    setState((previous) => {
      const base = previous.epoch === epoch ? previous : emptyState(epoch);
      if (!base.history.length) return base;
      const history = [...base.history];
      const cursor = history.pop();
      return { epoch, cursor, history };
    });
  }, [epoch]);

  return { cursor: current.cursor, next, back, canBack: current.history.length > 0 };
}
