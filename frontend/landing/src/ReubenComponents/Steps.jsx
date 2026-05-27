import { Boxes, Code, Settings } from "lucide-react";

const Steps = () => {
  const instructions = [
    {
      id: "01",
      heading: "Pick a template",
      body: "Choose the closest industry basleine for your bot",
      icon: Boxes,
    },
    {
      id: "02",
      heading: "Tune and add Q & A",
      body: "Drop in custom questions, control speed and threshold",
      icon: Settings,
    },
    {
      id: "03",
      heading: "Embed anywhere",
      body: "Copy the script tag and paste anywhere",
      icon: Code,
    },
  ];

  return (
    <div className="flex flex-col justify-center gap-10 p-5 md:h-screen h-full ">
      <h1 className="text-foreground text-6xl font-heading">
        Three steps to live.
      </h1>

      <div className="grid md:grid-cols-3 gap-7">
        {instructions.map((instruction) => (
          <div
            key={instruction.id}
            className="w-full h-60 text-primary grid  justify-between rounded-xl p-5 outline bg-white/72 dark:bg-white/6"
          >
            <div className="flex items-center justify-between">
              <h1 className="text-5xl font-serif text-foreground dark:text-primary">
                {instruction.id}
              </h1>
              {}
            </div>

            <p className="text-foreground font-body text-3xl">
              {instruction.heading}
            </p>

            <h3 className="text-lg text-foreground font-body">
              {instruction.body}
            </h3>
          </div>
        ))}
      </div>
    </div>
  );
};

export default Steps;
