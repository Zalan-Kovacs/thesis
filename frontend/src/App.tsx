import { useEffect, useState } from "react";
import Health from "./components/Health";
import LogSearch from "./components/LogSearch";
import LogLoad from "./components/LogLoad";
import "./App.css";

function App() {
  const [health, setHealth] = useState(null);

  useEffect(() => {
    fetch("/api/health")
      .then((res) => res.json())
      .then((data) => setHealth(data));
  }, []);

  return (
    <>
      <section id="center"></section>
      <section>
        <Health health={health} />
      </section>

      <section>
        <h2>LogLoad</h2>
        <LogLoad />
      </section>
      <section>
        <h2>LogSearch</h2>
        <LogSearch />
      </section>
    </>
  );
}

export default App;
