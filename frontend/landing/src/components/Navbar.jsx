import { BotIcon } from "lucide-react";
import { useTheme } from "../context/ThemeContext";

const navlinks = ["Features", "How it works", "Stack"];

export default function Navbar() {
  const { theme, toggleTheme } = useTheme();

  return (
    <nav className="sticky top-0 z-30 pt-4 sm:pt-6">
      <div className="flex items-center justify-between rounded-[2rem] border border-white/55 bg-white/70 px-4 py-3 text-secondary shadow-[0_20px_60px_rgba(15,23,42,0.08)] backdrop-blur-xl dark:border-white/10 dark:bg-white/5 dark:text-white sm:px-6">
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-primary  text-secondary-foreground dark:text-white shadow-lg shadow-black/10">
            <BotIcon className="h-5 w-5" />
          </div>
          <div>
            <p className="font-heading text-2xl leading-none sm:text-3xl">
              Meraxes
            </p>
            <p className="font-body text-xs uppercase tracking-[0.3em] text-secondary/55 dark:text-white/55">
              Local AI runtime
            </p>
          </div>
        </div>

        <div className="hidden items-center gap-1 rounded-full border border-black/5 bg-black/[0.03] p-1 dark:border-white/10 dark:bg-white/[0.04] lg:flex">
          {navlinks.map((link) => (
            <a
              key={link}
              href="#"
              className="rounded-full px-4 py-2 font-body text-sm text-secondary/70 transition hover:bg-white hover:text-secondary dark:text-white/70 dark:hover:bg-white/10 dark:hover:text-white"
            >
              {link}
            </a>
          ))}
        </div>

        <div className="flex items-center gap-2 font-body">
          <button
            onClick={toggleTheme}
            className="rounded-full border border-black/8 px-3 py-2 text-sm text-secondary/75 transition hover:border-black/15 hover:bg-black/[0.04] hover:text-secondary dark:border-white/10 dark:text-white/75 dark:hover:bg-white/10 dark:hover:text-white"
          >
            {theme === "dark" ? "Light" : "Dark"}
          </button>
          <button className="hidden rounded-full px-3 py-2 text-sm text-secondary/70 transition hover:text-secondary dark:text-white/70 dark:hover:text-white sm:inline-flex">
            Login
          </button>
          <button className="rounded-full bg-primary px-4 py-2.5 text-sm text-secondary-foreground shadow-lg shadow-black/10 transition hover:scale-[1.02] dark:bg-white dark:text-slate-950">
            Get Started
          </button>
        </div>
      </div>
    </nav>
  );
}
