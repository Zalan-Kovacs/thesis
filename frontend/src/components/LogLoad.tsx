import { useState } from "react";

export default function LogLoad() {
  const [service, setService] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [previewLine, setPreviewLine] = useState<string>("");

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
  return (
    <div style={{ margin: "20px 0" }}>
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
        <select name="separator" id="sep">
          <option value=" ">" "</option>
          <option value=";">";"</option>
          <option value=",">","</option>
          <option value="\t">"\t"</option>
        </select>
        <button type="submit">Preview</button>
      </form>
      {previewLine && (
        <div style={{ marginTop: "15px" }}>
          <h4>First row:</h4>
          <pre
            style={{ background: "#f4f4f4", padding: "10px", color: "#000" }}
          >
            {previewLine}
          </pre>
        </div>
      )}
    </div>
  );
}
