import { useState } from 'react'
import reactLogo from './assets/react.svg'
import viteLogo from './assets/vite.svg'
import heroImg from './assets/hero.png'
import './App.css'
import Steps from './ReubenComponents/Steps'

function App() {
  const [count, setCount] = useState(0)

  return (
   <div>
    <Steps/>
   </div>
  )
}

export default App
