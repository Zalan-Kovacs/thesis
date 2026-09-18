import { useState } from "react";

export default function LogLoad() {
  const [service, setService] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [previewLine, setPreviewLine] = useState<string>("");
  const [separator, setSeparator] = useState<string>(" ");
  const [fieldMapping, setFieldMapping] = useState<Record<number, string>>({});

  const handleFieldChange = (index: number, field: string) => {
    setFieldMapping((prev) => ({
      ...prev,
      [index]: field,
    }));
  };
  const handleIngest = async () => {
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);
    formData.append("service", service);
    formData.append("separator", separator);
    formData.append("mapping", JSON.stringify(fieldMapping));

    try {
      const response = await fetch("/api/logs/ingest", {
        method: "POST",
        body: formData,
      });

      const result = await response.json();
      alert(`Successful indexing: ${result.indexed_count} row.`);
    } catch (err) {
      console.error("Hiba az indexelés során:", err);
    }
  };
  const loadPreview = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!file) {
      alert("Choose a File!");
      return;
    }

    try {
      const formData = new FormData();
      formData.append("file", file);
      const response = await fetch("api/logs/preview", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`HTTP error: ${response.status}`);
      }

      const data = await response.json();
      setPreviewLine(data["First Line"] || "");
    } catch (err) {
      console.error("Error during the load of preview:", err);
    }
  };
  const tokens = previewLine
    ? separator === " "
      ? previewLine.trim().split(/\s+/)
      : previewLine.split(separator)
    : [];
  return (
    <div>
      <form onSubmit={loadPreview}>
        <input
          type="text"
          name="Service"
          id="svc"
          value={service}
          onChange={(e) => setService(e.target.value)}
          placeholder="Service"
          required
        />
        <input
          type="file"
          name="File"
          id="file"
          onChange={(e) => setFile(e.target.files?.[0] || null)}
          required
        />
        <select
          name="separator"
          id="sep"
          value={separator}
          onChange={(e) => setSeparator(e.target.value)}
        >
          <option value=" ">" "</option>
          <option value=": ">": "</option>
          <option value="; ">";"</option>
          <option value=", ">", "</option>
        </select>
        <button type="submit">Preview</button>
      </form>
      {previewLine && (
        <div>
          <h4>First row:</h4>
          <pre>{previewLine}</pre>
          <h4>Tokens ({tokens.length}):</h4>
          <div>
            {tokens.map((token, index) => (
              <div key={index}>
                <code>{token}</code>
                <select
                  value={fieldMapping[index] || "ignore"}
                  onChange={(e) => handleFieldChange(index, e.target.value)}
                >
                  <option value="ignore">Ignore</option>
                  <option value="timestamp">Timestamp</option>
                  <option value="severity">Severity</option>
                  <option value="message">Message</option>
                </select>
              </div>
            ))}
            <pre>{JSON.stringify(fieldMapping, null, 2)}</pre>
          </div>
        </div>
      )}
      {previewLine && (
        <button type="button" onClick={handleIngest}>
          Start Indexing
        </button>
      )}
    </div>
  );
}
