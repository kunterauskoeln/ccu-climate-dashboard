import { EventSourcePolyfill } from "event-source-polyfill";

// Same-origin by default (nginx proxies /api → backend).
// Override for local dev with VITE_API_URL=http://localhost:8000
const API = import.meta.env.VITE_API_URL ?? "/api";

export function subscribeToHeatingEvents(onEvent: (data: unknown) => void) {
  const es = new EventSourcePolyfill(`${API}/events/heating`);

  es.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      onEvent(data);
    } catch (e) {
      console.error("Invalid SSE data", e);
    }
  };

  return () => es.close();
}
