import {
  LayoutTemplate,
  MessageSquare,
  Zap,
  Code2,
  ShieldCheck,
  Shuffle,
} from "lucide-react";
import Card from "./Card";

 const features = [
  {
    id: 1,
    title: "Industry templates",
    description:
      "Start from ecommerce, finance, healthcare, SaaS, or general baselines.",
    icon: LayoutTemplate,
  },
  {
    id: 2,
    title: "Custom Q&A",
    description: "Add your own questions and answers — retrain in seconds.",
    icon: MessageSquare,
  },
  {
    id: 3,
    title: "Local neural models",
    description:
      "Intent classifier + FAQ matcher. No external LLM keys required.",
    icon: Zap,
  },
  {
    id: 4,
    title: "One-line embed",
    description: "Copy a script tag, drop before </body>, ship.",
    icon: Code2,
  },
  {
    id: 5,
    title: "Self-hosted",
    description: "Your data, your hardware. Single-tenant local tool.",
    icon: ShieldCheck,
  },
  {
    id: 6,
    title: "Hybrid mode",
    description: "FAQ first, then intent fallback — best of both worlds.",
    icon: Shuffle,
  },
];
export default function Features() {
  return (
    <section className="px-2 pt-24 text-secondary dark:text-white sm:px-0">
      <div className="mx-auto max-w-6xl space-y-4">
        <p className="font-body text-xs uppercase tracking-[0.32em] text-secondary/45 dark:text-white/45">
          Capabilities
        </p>
        <h2 className="max-w-4xl font-heading text-4xl leading-tight tracking-[-0.03em] sm:text-6xl lg:text-7xl">
          Built for makers who ship.
        </h2>
        <p className="max-w-2xl font-body text-base leading-7 text-secondary/65 dark:text-white/65 sm:text-lg">
          Everything you need to take a chatbot from idea to embed code on a customer's website
        </p>
      </div>

      <Card items={features} />
    </section>
  );
}
