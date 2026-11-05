export type AnalysisEvent = { event: string; data: Record<string, unknown> };
export const isRecord = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === 'object' && !Array.isArray(value);

/** Preserve useful partial results; empty placeholders never erase prior evidence. */
export function mergeResult<T extends object>(previous: T | undefined, incoming: T | undefined): T | undefined {
  if (!incoming) return previous;
  if (!previous) return { ...incoming };
  const output: Record<string, unknown> = { ...previous } as Record<string, unknown>;
  for (const [key, value] of Object.entries(incoming)) {
    const old = output[key];
    if (value == null || value === '') continue;
    if (Array.isArray(value)) {
      if (!value.length) continue;
      if (key.endsWith('citations') || key === 'production_artifact_ids' || key === 'confirmed_dashboards') {
        const identity = (item: unknown) => {
          if (!isRecord(item)) return String(item);
          if (key === 'confirmed_dashboards') return `${item.scene_id || ''}::${item.url || ''}`;
          if (key === 'read_knowledge_citations') return String(item.citation_id || item.url || item.title || '');
          return String(item.citation_id || item.resource_uuid || item.table_name || item.id || item.title || JSON.stringify(item));
        };
        const all = Array.isArray(old) ? [...old] : [];
        const seen = new Set(all.map(identity));
        for (const item of value) if (!seen.has(identity(item))) { seen.add(identity(item)); all.push(item); }
        output[key] = all;
      } else output[key] = value;
    } else output[key] = isRecord(old) && isRecord(value) ? mergeResult(old, value) : value;
  }
  return output as T;
}

export interface AnalysisState {
  messages: Record<string, string>;
  artifacts: Record<string, unknown>;
  interrupt?: Record<string, unknown>;
  status: string;
}
export const initialAnalysisState = (): AnalysisState => ({ messages: {}, artifacts: {}, status: 'idle' });
export function analysisReducer(state: AnalysisState, { event, data }: AnalysisEvent): AnalysisState {
  if (event === 'stream_snapshot') {
    const latest = isRecord(data.latest) ? data.latest : {};
    const messages = Object.fromEntries(Object.entries(isRecord(data.messages) ? data.messages : {}).filter((entry): entry is [string, string] => typeof entry[1] === 'string'));
    return { messages, artifacts: isRecord(data.artifacts) ? data.artifacts : {}, interrupt: isRecord(latest.interrupt) ? latest.interrupt : undefined,
      status: isRecord(latest.stream_terminal) ? String(latest.stream_terminal.status) : 'running' };
  }
  if (event === 'message_chunk' && typeof data.content === 'string') {
    const key = String(data.id || data.agent || 'answer');
    return { ...state, messages: { ...state.messages, [key]: (state.messages[key] || '') + data.content } };
  }
  if (event === 'agent_artifacts' && isRecord(data.artifacts)) return { ...state, artifacts: mergeResult(state.artifacts, data.artifacts)! };
  if (event === 'interrupt') return { ...state, interrupt: data, status: 'awaiting_input' };
  if (event === 'stream_started') return { ...state, status: 'running', interrupt: undefined };
  if (event === 'stream_terminal') return { ...state, status: String(data.status || 'interrupted') };
  return state;
}
