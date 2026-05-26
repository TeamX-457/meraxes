import Navbar from "./components/Navbar";
import Hero from "./components/Hero";
import Aurora from "../components/Aurora";
import Features from "./components/Features";

import Steps from "./ReubenComponents/Steps";
import Control from "./ReubenComponents/Control";
import Ready from "./ReubenComponents/Ready";

export default function App() {
  return (
    <main className="relative min-h-screen overflow-hidden bg-background text-foreground">
      <div className="absolute inset-0 z-0 h-64 blur-sm">
        <Aurora
          colorStops={["#2563eb", "#B497CF", "#5227FF"]}
          blend={1.5}
          amplitude={1.0}
          speed={1}
        />
      </div>
      <div className="relative mx-auto flex min-h-screen w-full max-w-7xl flex-col px-4 pb-16 sm:px-6 lg:px-8">
        <Navbar />
        <Hero />
        <Features />
        <Steps />
        <Control />
        <Ready />
      </div>
    </main>
  );
}
