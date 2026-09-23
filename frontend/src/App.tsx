import { useEffect, useState } from "react";
import Health from "./components/Health";
import LogSearch from "./components/LogSearch";
import LogLoad from "./components/LogLoad";
import "./App.css";

function App() {
  const [health, setHealth] = useState(null);
  const [activeView, setActiveView] = useState<string>("load");

  useEffect(() => {
    fetch("/api/health")
      .then((res) => res.json())
      .then((data) => setHealth(data));
  }, []);

  return (
    <>
      <div style={{ marginBottom: "20px" }}>
        <label htmlFor="view-select" style={{ marginRight: "10px" }}>
          Menu:
        </label>
        <select
          id="view-select"
          value={activeView}
          onChange={(e) => setActiveView(e.target.value)}
        >
          <option value="health">Health</option>
          <option value="load">LogLoad</option>
          <option value="search">LogSearch</option>
        </select>
      </div>
      <section id="center"></section>
      {activeView === "health" && (
        <section>
          <Health health={health} />
        </section>
      )}

      {activeView === "load" && (
        <section>
          <h2>LogLoad</h2>
          <LogLoad />
        </section>
      )}

      {activeView === "search" && (
        <section>
          <h2>LogSearch</h2>
          <LogSearch />
        </section>
      )}
    </>
  );
}

export default App;
