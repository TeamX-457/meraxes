export default function Card({ items }) {
  return (
    <div className="mx-auto mt-10 grid max-w-6xl grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
      {items.map((item) => {
        const IconComponent = item.icon;

        return (
          <div
            key={item.id}
            className="group rounded-[2rem] border border-white/65 bg-white/72 p-7 shadow-[0_18px_40px_rgba(15,23,42,0.07)] backdrop-blur-xl transition duration-300 hover:-translate-y-1 hover:shadow-[0_28px_65px_rgba(15,23,42,0.12)] dark:border-white/10 dark:bg-white/6"
          >
            <div className="mb-16 flex h-12 w-12 items-center justify-center rounded-2xl bg-secondary text-secondary-foreground shadow-lg shadow-black/10 dark:bg-white dark:text-slate-950">
              <IconComponent size={20} strokeWidth={2} />
            </div>

            <h3 className="mb-3 font-heading text-3xl text-secondary transition group-hover:text-primary dark:text-white dark:group-hover:text-cyan-300">
              {item.title}
            </h3>
            <p className="font-body text-sm leading-7 text-secondary/68 dark:text-white/68">
              {item.description}
            </p>
          </div>
        );
      })}
    </div>
  );
}
