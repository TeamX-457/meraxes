import {
  Marquee,
  MarqueeFade,
  MarqueeContent,
  MarqueeItem,
} from "./ui/marquee";

const items = [
  { name: "FAQ Matcher", icon: "\u269b" },
  { name: "Hybrid Mode", icon: "\u25b2" },
  { name: "One-Line Embed", icon: "\u2726" },
  { name: "Local Neural", icon: "\u25c6" },
  { name: "Intent Routing", icon: "\u2733" },
  { name: "Template Training", icon: "\u25a0" },
];

export default function MarqueeSlide() {
  return (
    <Marquee className="mt-8 overflow-hidden rounded-[2rem] border border-white/60 bg-white/70 py-2 shadow-[0_24px_60px_rgba(15,23,42,0.08)] backdrop-blur-xl dark:border-white/10 dark:bg-white/6">
      <MarqueeFade side="left" />
      <MarqueeContent speed={40} pauseOnHover>
        {items.map((item) => (
          <MarqueeItem
            key={item.name}
            className="flex items-center gap-3 px-5 py-3 font-body text-sm uppercase tracking-[0.26em] text-secondary/75 dark:text-white/75 sm:px-7"
          >
            <span
              aria-hidden="true"
              className="flex h-9 w-9 items-center justify-center rounded-full bg-secondary text-base text-secondary-foreground dark:bg-white dark:text-slate-950"
            >
              {item.icon}
            </span>
            <span>{item.name}</span>
          </MarqueeItem>
        ))}
      </MarqueeContent>
      <MarqueeFade side="right" />
    </Marquee>
  );
}
