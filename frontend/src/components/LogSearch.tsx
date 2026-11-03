import { useState, useEffect } from "react";

interface LogHit {
  _id: string;
  _score?: number;
  _source: {
    timeStamp: string;
    service: string;
    severity: string;
    message: string;
  };
}

interface SuggestionItem {
  resolution: string;
  author: string;
  service?: string;
  score: number;
  original_pattern: string;
}

interface LogSearchProps {
  token: string | null;
}

interface SavedPattern {
  id: number;
  name: string;
  q: string | null;
  service: string | null;
  severity: string | null;
  date_from: string | null;
  date_to: string | null;
}

interface SearchHistory {
  id: number;
  q: string | null;
  service: string | null;
  severity: string | null;
  created_at: string;
}

export default function LogSearch({ token }: LogSearchProps) {
  const [loading, setLoading] = useState(false);
  const [q, setQ] = useState<string>("");
  const [service, setService] = useState<string>("");
  const [severity, setSeverity] = useState<string>("");
  const [dateFrom, setDateFrom] = useState<string>("");
  const [dateTo, setDateTo] = useState<string>("");
  const [logs, setLogs] = useState<LogHit[]>([]);
  const [history, setHistory] = useState<SearchHistory[]>([]);
  const [patterns, setPatterns] = useState<SavedPattern[]>([]);
  const [patternName, setPatternName] = useState("");
  const [showSavePattern, setShowSavePattern] = useState(false);

  const [suggestions, setSuggestions] = useState<
    Record<string, SuggestionItem[] | null>
  >({});
  const [loadingSuggestionId, setLoadingSuggestionId] = useState<string | null>(
    null,
  );

  // Megoldás mentése
  const [resolvingId, setResolvingId] = useState<string | null>(null);
  const [resolutionDrafts, setResolutionDrafts] = useState<
    Record<string, string>
  >({});

  const fetchHistoryAndPatterns = async () => {
    if (!token) return;
    try {
      const [histRes, pattRes] = await Promise.all([
        fetch("/api/logs/history", {
          headers: { Authorization: `Bearer ${token}` },
        }),
        fetch("/api/logs/patterns", {
          headers: { Authorization: `Bearer ${token}` },
        }),
      ]);
      if (histRes.ok) setHistory(await histRes.json());
      if (pattRes.ok) setPatterns(await pattRes.json());
    } catch (err) {
      console.error("Profil adatok betöltési hiba:", err);
    }
  };

  useEffect(() => {
    fetchHistoryAndPatterns();
  }, [token]);

  const applyFilters = (target: {
    q?: string | null;
    service?: string | null;
    severity?: string | null;
    date_from?: string | null;
    date_to?: string | null;
  }) => {
    setQ(target.q || "");
    setService(target.service || "");
    setSeverity(target.severity || "");
    setDateFrom(target.date_from || "");
    setDateTo(target.date_to || "");
  };

  const handleSavePattern = async () => {
    if (!patternName.trim() || !token) return;
    try {
      const res = await fetch("/api/logs/patterns", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          name: patternName.trim(),
          q: q.trim(),
          service: service.trim(),
          severity: severity.trim(),
          dateFrom: dateFrom.trim(),
          dateTo: dateTo.trim(),
        }),
      });
      if (res.ok) {
        setPatternName("");
        setShowSavePattern(false);
        fetchHistoryAndPatterns();
      }
    } catch (err) {
      alert("Hiba a minta mentése során.");
    }
  };

  const handleDeletePattern = async (id: number) => {
    if (!token) return;
    await fetch(`/api/logs/patterns/${id}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
    fetchHistoryAndPatterns();
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    if (token) {
      fetch("/api/logs/history", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          q: q.trim(),
          service: service.trim(),
          severity: severity.trim(),
          dateFrom: dateFrom.trim(),
          dateTo: dateTo.trim(),
        }),
      }).then(() => fetchHistoryAndPatterns());
    }

    const params = new URLSearchParams();
    if (q != "") params.append("q", q.trim());
    if (service != "") params.append("service", service.trim());
    if (severity != "") params.append("severity", severity.trim());
    if (dateFrom != "") params.append("dateFrom", dateFrom.trim());
    if (dateTo != "") params.append("dateTo", dateTo.trim());

    const endpoint =
      q.trim() !== "" ? "/api/logs/hybrid-search" : "/api/logs/search";

    try {
      const res = await fetch(`${endpoint}?${params.toString()}`);
      const data = await res.json();

      if (!res.ok) {
        setLogs([]);
        alert(
          `Search error (${res.status}): ${data.detail || JSON.stringify(data)}`,
        );
        return;
      }

      if (Array.isArray(data)) {
        setLogs(data);
      } else {
        setLogs([]);
      }
    } catch (err) {
      console.error("Error during search:", err);
      alert("Network error during search.");
    } finally {
      setLoading(false);
    }
  };

  const handleFetchSuggestion = async (logId: string, message: string) => {
    setLoadingSuggestionId(logId);
    try {
      const res = await fetch(
        `/api/logs/knowledge/suggest?message=${encodeURIComponent(message)}&threshold=1.30&limit=3`,
      );
      const data = await res.json();
      setSuggestions((prev) => ({
        ...prev,
        [logId]: data.match ? data.suggestions : null,
      }));
    } catch (err) {
      console.error("Nem sikerült lekérni a javaslatokat:", err);
    } finally {
      setLoadingSuggestionId(null);
    }
  };

  const handleSaveToKnowledgeBase = async (log: LogHit) => {
    const resolution = resolutionDrafts[log._id]?.trim();
    if (!resolution || !token) return;

    try {
      const res = await fetch("/api/logs/knowledge/resolve", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          problem_message: log._source.message,
          service: log._source.service,
          resolution,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Didn't save.");

      alert("Saved to Knowledge Base");
      setResolvingId(null);
      setResolutionDrafts((prev) => ({ ...prev, [log._id]: "" }));
      handleFetchSuggestion(log._id, log._source.message);
    } catch (err) {
      alert(err instanceof Error ? err.message : "ERROR");
    }
  };

  return (
    <div>
      {token && (
        <div
          style={{
            marginBottom: "1rem",
            borderBottom: "1px solid #444",
            paddingBottom: "1rem",
          }}
        >
          <div>
            <strong>Saved patterns: </strong>
            {patterns.length === 0 ? (
              <small>There are no saved patterns.</small>
            ) : (
              patterns.map((p) => (
                <span key={p.id} style={{ marginRight: "8px" }}>
                  <button type="button" onClick={() => applyFilters(p)}>
                    {p.name}
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDeletePattern(p.id)}
                  >
                    x
                  </button>
                </span>
              ))
            )}
            <button
              type="button"
              onClick={() => setShowSavePattern(!showSavePattern)}
              style={{ marginLeft: "8px" }}
            >
              {showSavePattern ? "Cancel" : "Save pattern"}
            </button>
          </div>

          {showSavePattern && (
            <div style={{ marginTop: "6px" }}>
              <input
                type="text"
                placeholder="Pattern name..."
                value={patternName}
                onChange={(e) => setPatternName(e.target.value)}
              />
              <button
                type="button"
                onClick={handleSavePattern}
                disabled={!patternName.trim()}
              >
                Save
              </button>
            </div>
          )}

          <div style={{ marginTop: "8px" }}>
            <label htmlFor="history-select">
              <strong>History: </strong>
            </label>
            <select
              id="history-select"
              defaultValue=""
              onChange={(e) => {
                const item = history.find(
                  (h) => h.id === Number(e.target.value),
                );
                if (item) applyFilters(item);
              }}
            >
              <option value="" disabled>
                Loading search history...
              </option>
              {history.map((h) => (
                <option key={h.id} value={h.id}>
                  {h.q ? `"${h.q}"` : "(empty)"} | {h.service || "*"} | [
                  {h.severity || "ALL"}]
                </option>
              ))}
            </select>
          </div>
        </div>
      )}
      <form onSubmit={handleSearch}>
        <input
          type="text"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search..."
        />
        <div className="grid">
          <input
            type="text"
            value={service}
            onChange={(e) => setService(e.target.value)}
            placeholder="Service"
          />
          <select
            value={severity}
            onChange={(e) => setSeverity(e.target.value)}
          >
            <option value="">All severities</option>
            <option value="INFO">[INFO]</option>
            <option value="WARNING">[WARNING]</option>
            <option value="ERROR">[ERROR]</option>
          </select>
          <input
            type="datetime-local"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
          />
          <input
            type="datetime-local"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
          />
        </div>
        <button type="submit">Search</button>
      </form>

      {loading && <p>Searching...</p>}

      <div style={{ marginTop: "1.5rem" }}>
        {logs.map((item) => {
          const itemSuggestions = suggestions[item._id];
          return (
            <article
              key={item._id}
              style={{ marginBottom: "1.2rem", padding: "1.2rem" }}
            >
              <header
                style={{
                  marginBottom: "0.5rem",
                  display: "flex",
                  justifyContent: "space-between",
                }}
              >
                <div>
                  <small>{item._source.timeStamp}</small> |{" "}
                  <strong> [{item._source.service}]</strong> |{" "}
                  <span> [{item._source.severity}] </span>
                </div>
                <div>
                  {item._score !== undefined && (
                    <span style={{ color: "var(--pico-muted-color)" }}>
                      (Score: {item._score.toFixed(4)})
                    </span>
                  )}
                </div>
              </header>
              <code>{item._source.message}</code>

              <div>
                {itemSuggestions && itemSuggestions.length > 0 ? (
                  <div
                    style={{
                      marginTop: "1rem",
                      borderLeft: "3px solid var(--pico-primary)",
                      paddingLeft: "1rem",
                    }}
                  >
                    <span>
                      Relevant known solutions ({itemSuggestions.length}{" "}
                      result):
                    </span>

                    {itemSuggestions.map((sug, idx) => (
                      <div
                        key={idx}
                        style={{
                          margin: "0.5rem 0",
                          background: "var(--pico-card-background-color)",
                          padding: "0.5rem",
                          borderRadius: "4px",
                        }}
                      >
                        <div>
                          <strong>#{idx + 1} Solution</strong>{" "}
                          <span>(Similarity: {sug.score.toFixed(4)})</span>
                        </div>
                        <p style={{ margin: "0.25rem 0" }}>{sug.resolution}</p>
                        <small style={{ color: "var(--pico-muted-color)" }}>
                          Original pattern: <em>"{sug.original_pattern}"</em> |
                          Author: @{sug.author}
                        </small>
                      </div>
                    ))}

                    <button
                      type="button"
                      className="secondary outline"
                      onClick={() =>
                        setSuggestions((prev) => {
                          const next = { ...prev };
                          delete next[item._id];
                          return next;
                        })
                      }
                    >
                      Close
                    </button>
                  </div>
                ) : itemSuggestions === null ? (
                  <div style={{ marginTop: "0.5rem" }}>
                    <small>
                      There are no solutions to the given threshold (1.30).
                    </small>
                    <button
                      type="button"
                      className="secondary outline"
                      style={{ marginLeft: "0.5rem" }}
                      onClick={() =>
                        setSuggestions((prev) => {
                          const next = { ...prev };
                          delete next[item._id];
                          return next;
                        })
                      }
                    >
                      Close
                    </button>
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={() =>
                      handleFetchSuggestion(item._id, item._source.message)
                    }
                    disabled={loadingSuggestionId === item._id}
                  >
                    {loadingSuggestionId === item._id
                      ? "Searching..."
                      : "Searching solutions"}
                  </button>
                )}

                {token && (
                  <button
                    type="button"
                    className="outline"
                    onClick={() =>
                      setResolvingId(resolvingId === item._id ? null : item._id)
                    }
                  >
                    {resolvingId === item._id ? "Cancel" : "Add new solution"}
                  </button>
                )}
              </div>

              {resolvingId === item._id && (
                <div>
                  <input
                    type="text"
                    placeholder="Solution to resolve error..."
                    value={resolutionDrafts[item._id] || ""}
                    onChange={(e) =>
                      setResolutionDrafts({
                        ...resolutionDrafts,
                        [item._id]: e.target.value,
                      })
                    }
                  />
                  <button
                    type="button"
                    onClick={() => handleSaveToKnowledgeBase(item)}
                    disabled={!resolutionDrafts[item._id]?.trim()}
                  >
                    Save
                  </button>
                </div>
              )}
            </article>
          );
        })}
      </div>
    </div>
  );
}
