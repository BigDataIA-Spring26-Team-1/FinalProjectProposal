const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(
  /\/$/,
  "",
);

export async function fetchDashboardSnapshot(signal, options = {}) {
  const { forceRefresh = false } = options;
  const query = new URLSearchParams();
  if (forceRefresh) {
    query.set("force_refresh", "true");
  }

  const endpoint = query.size
    ? `${API_BASE_URL}/api/dashboard?${query.toString()}`
    : `${API_BASE_URL}/api/dashboard`;
  const response = await fetch(endpoint, { signal });
  if (!response.ok) {
    throw new Error(`Dashboard API returned ${response.status}`);
  }

  return response.json();
}

export async function fetchRagStatus(signal, options = {}) {
  const { forceRefresh = false } = options;
  const query = new URLSearchParams();
  if (forceRefresh) {
    query.set("force_refresh", "true");
  }

  const endpoint = query.size
    ? `${API_BASE_URL}/api/rag/status?${query.toString()}`
    : `${API_BASE_URL}/api/rag/status`;
  const response = await fetch(endpoint, { signal });
  if (!response.ok) {
    throw new Error(`RAG API returned ${response.status}`);
  }

  return response.json();
}

export async function rebuildRagIndex() {
  const response = await fetch(`${API_BASE_URL}/api/rag/reindex`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error(`RAG reindex API returned ${response.status}`);
  }

  return response.json();
}

export async function sendChatQuestion(payload) {
  const response = await fetch(`${API_BASE_URL}/api/chat`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(`Chat API returned ${response.status}`);
  }

  return response.json();
}
