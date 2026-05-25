import { useState } from 'react'
import reactLogo from './assets/react.svg'
import viteLogo from './assets/vite.svg'
import heroImg from './assets/hero.png'
import './App.css'
import Steps from './ReubenComponents/Steps'
import Control from './ReubenComponents/Control'
import Ready from './ReubenComponents/Ready'

function App() {
  const [count, setCount] = useState(0)

  return (
   <div>
    <Steps/>
    <Control/>
    <Ready/>
   </div>
  )
}

export default App
