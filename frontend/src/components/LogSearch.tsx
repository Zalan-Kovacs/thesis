import { useState } from 'react';

interface LogHit {
  _source: {
    timeStamp: string;
    service: string;
    severity: string;
    message: string;
  };
}

export default function LogSearch() {
  const [query, setQuery] = useState('');
  const [logs, setLogs] = useState<LogHit[]>([]);
  const [loading, setLoading] = useState(false);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await fetch(`/api/logs/search?q=${encodeURIComponent(query)}`);
      const data = await res.json();
      if (data.hits && data.hits.hits) {
        setLogs(data.hits.hits);
      }
    } catch (err) {
      console.error("Hiba a keresés során:", err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ margin: '20px 0' }}>
      <form onSubmit={handleSearch}>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Keresés a logokban..."
          style={{ padding: '8px', width: '300px', marginRight: '8px' }}
        />
        <button type="submit" style={{ padding: '8px 16px' }}>Keresés</button>
      </form>

      {loading && <p>Keresés folyamatban...</p>}

      <ul style={{ listStyle: 'none', padding: 0, marginTop: '16px' }}>
        {logs.map((item, index) => (
          <li key={index} style={{ padding: '6px 0', borderBottom: '1px solid #ddd' }}>
            <strong>[{item._source.severity}]</strong> {item._source.message}
          </li>
        ))}
      </ul>
    </div>
  );
}