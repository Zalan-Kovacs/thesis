import { useState } from "react";

interface LogHit {
  _source: {
    timeStamp: string;
    service: string;
    severity: string;
    message: string;
  };
}

export default function LogSearch() {
  const [loading, setLoading] = useState(false);
  const [q, setQ] = useState<string>("");
  const [service, setService] = useState<string>("");
  const [severity, setSeverity] = useState<string>("");
  const [dateFrom, setDateFrom] = useState<string>("");
  const [dateTo, setDateTo] = useState<string>("");
  const [logs, setLogs] = useState<
    Array<{ _id: string; _source: LogHit["_source"] }>
  >([]);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    const params = new URLSearchParams();
    if (q != "") params.append("q", q.trim());
    if (service != "") params.append("service", service.trim());
    if (severity != "") params.append("severity", severity.trim());
    if (dateFrom != "") params.append("dateFrom", dateFrom.trim());
    if (dateTo != "") params.append("dateTo", dateTo.trim());

    try {
      const res = await fetch(`/api/logs/search?${params.toString()}`);
      const data = await res.json();
      if (Array.isArray(data)) setLogs(data);
    } catch (err) {
      console.error("Error during search:", err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ margin: "20px 0" }}>
      <form onSubmit={handleSearch}>
        <input
          type="text"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search in logs"
        />
        <input
          type="text"
          value={service}
          onChange={(e) => setService(e.target.value)}
          placeholder="Service"
        />
        <label htmlFor="sev">Severity</label>
        <select
          name="severity"
          id="sev"
          value={severity}
          onChange={(e) => setSeverity(e.target.value)}
        >
          <option value="">All severities</option>
          <option value="info">[INFO]</option>
          <option value="warning">[WARNING]</option>
          <option value="error">[ERROR]</option>
        </select>
        <label htmlFor="dateFrom">From:</label>
        <input
          id="dateFrom"
          type="datetime-local"
          value={dateFrom}
          onChange={(e) => setDateFrom(e.target.value)}
        />
        <label htmlFor="dateTo">To:</label>
        <input
          id="dateTo"
          type="datetime-local"
          value={dateTo}
          onChange={(e) => setDateTo(e.target.value)}
        />
        <button type="submit">Search</button>
      </form>

      {loading && <p>Searching...</p>}

      <ul>
        {logs.map((item, index) => (
          <li key={item._id}>
            <small>{item._source.timeStamp}</small> |
            <strong> [{item._source.service}]</strong>
            <span> [{item._source.severity}] </span>
            {item._source.message}
          </li>
        ))}
      </ul>
    </div>
  );
}
