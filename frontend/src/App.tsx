import { useEffect, useState } from "react";
import Auth from "./components/Auth";
import Health from "./components/Health";
import LogSearch from "./components/LogSearch";
import LogLoad from "./components/LogLoad";
import "./App.css";

function App() {
  const [token, setToken] = useState<string | null>(() =>
    localStorage.getItem("token"),
  );
  const [health, setHealth] = useState(null);
  const [activeView, setActiveView] = useState<string>("load");

  useEffect(() => {
    fetch("/api/health")
      .then((res) => res.json())
      .then((data) => setHealth(data));
  }, []);

  return (
    <main className="container">
      <nav>
        <ul>
          <li>
            <strong>Log Assistant</strong>
          </li>
        </ul>
        <ul>
          <li>
            <select
              id="view-select"
              value={activeView}
              onChange={(e) => setActiveView(e.target.value)}
            >
              <option value="search">LogSearch</option>
              <option value="load">LogLoad</option>
              <option value="health">Health</option>
            </select>
          </li>
        </ul>
      </nav>

      <Auth token={token} setToken={setToken} />

      {activeView === "health" && <Health health={health} />}
      {activeView === "load" && <LogLoad />}
      {activeView === "search" && <LogSearch token={token} />}
    </main>
  );
}

export default App;
