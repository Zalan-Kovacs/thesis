import { useEffect, useState } from 'react'
import Health from './components/Health'
import LogSearch from './components/LogSearch'
import reactLogo from './assets/react.svg'
import viteLogo from './assets/vite.svg'
import heroImg from './assets/hero.png'
import './App.css'

function App() {
  const [count, setCount] = useState(0)
  const [health, setHealth] = useState(null);

  useEffect(() => {
    fetch("/api/health")
    .then(res=>res.json())
    .then(data=>setHealth(data))
  },[])

  return (
    <>
      <section id="center">
        
      </section>
      <section>
        <Health health = {health} />
      </section>

      <section>
        <h2>LogSearch</h2>
        <LogSearch />
      </section>
      

    </>
  )
}

export default App
