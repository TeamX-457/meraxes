import GradientText from "../../components/GradientText";
import MarqueeSlide from "./Marquee";

export default function Hero() {
  return (
    <section className="relative pt-10 text-secondary dark:text-white">
      <div className="mx-auto flex min-h-[calc(100vh-7rem)] max-w-6xl flex-col items-center justify-center gap-10 py-14 text-center sm:gap-12 sm:py-20">
        <div className="inline-flex items-center gap-3 rounded-full border border-white/70 bg-white/78 px-5 py-3 font-body text-sm text-secondary/80 shadow-[0_20px_45px_rgba(15,23,42,0.08)] backdrop-blur-xl dark:border-white/10 dark:bg-white/8 dark:text-white/80">
          <div className="h-2.5 w-2.5 rounded-full bg-primary shadow-[0_0_16px_rgba(34,197,94,0.65)]"></div>
          <p>Self hosted neural training is live now</p>
        </div>

        <div className="max-w-5xl space-y-6 px-2">
          <h1 className="font-heading text-5xl leading-[0.95] tracking-[-0.04em] sm:text-7xl lg:text-[8.5rem]">
            Train AI on
            <span className="block pt-2">
              <GradientText
                colors={["#2563eb", "#38bdf8", "#c084fc"]}
                animationSpeed={6}
                showBorder={false}
                className="italic"
              >
                your business model
              </GradientText>
            </span>
          </h1>
          <p className="mx-auto max-w-2xl font-body text-base leading-7 text-secondary/68 dark:text-white/68 sm:text-lg">
            Meraxes trains local intent classifiers and FAQ matchers from your
            own templates. Build, tune, embed - No API Keys, no LLM bills
          </p>
        </div>

        <div className="flex flex-col items-center gap-4 sm:flex-row sm:justify-center">
          <button className="w-full rounded-full bg-primary px-7 py-3.5 font-body text-sm font-semibold tracking-wide text-secondary-foreground shadow-[0_24px_60px_rgba(15,23,42,0.18)] transition hover:-translate-y-0.5 hover:shadow-[0_28px_70px_rgba(15,23,42,0.22)]  dark:text-white sm:w-auto">
            Start Training
          </button>
          <button className="w-full rounded-full border border-black/10 bg-white/60 px-7 py-3.5 font-body text-sm font-semibold text-secondary transition hover:border-black/20 hover:bg-white dark:border-white/12 dark:bg-white/6 dark:text-white dark:hover:bg-white/10 sm:w-auto">
            Open Dashboard
          </button>
        </div>

        <div className="grid w-full max-w-4xl grid-cols-1 gap-4 px-2 sm:grid-cols-3">
          <div className="rounded-[1.75rem] border border-white/65 bg-white/72 p-5 text-left shadow-[0_18px_40px_rgba(15,23,42,0.07)] backdrop-blur-xl dark:border-white/10 dark:bg-white/6">
            <p className="font-body text-xs uppercase tracking-[0.26em] text-secondary/45 dark:text-white/45">
              Deploy mode
            </p>
            <p className="mt-3 font-heading text-3xl">Self-hosted</p>
          </div>
          <div className="rounded-[1.75rem] border border-white/65 bg-white/72 p-5 text-left shadow-[0_18px_40px_rgba(15,23,42,0.07)] backdrop-blur-xl dark:border-white/10 dark:bg-white/6">
            <p className="font-body text-xs uppercase tracking-[0.26em] text-secondary/45 dark:text-white/45">
              Training cycle
            </p>
            <p className="mt-3 font-heading text-3xl">Seconds, not days</p>
          </div>
          <div className="rounded-[1.75rem] border border-white/65 bg-white/72 p-5 text-left shadow-[0_18px_40px_rgba(15,23,42,0.07)] backdrop-blur-xl dark:border-white/10 dark:bg-white/6">
            <p className="font-body text-xs uppercase tracking-[0.26em] text-secondary/45 dark:text-white/45">
              Billing model
            </p>
            <p className="mt-3 font-heading text-3xl">Zero LLM tax</p>
          </div>
        </div>
      </div>

      <MarqueeSlide />
    </section>
  );
}
