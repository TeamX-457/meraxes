const root = document.documentElement;
const toggleBtn = document.getElementById("toggleTheme");

// check saved preference first
const savedTheme = localStorage.getItem("theme");

// system preference fallback
const systemDark = window.matchMedia("(prefers-color-scheme: dark)").matches;

// apply theme on load
if (savedTheme === "dark" || (!savedTheme && systemDark)) {
  root.classList.add("dark");
}

// toggle button
if (toggleBtn) {
  toggleBtn.addEventListener("click", () => {
    const isDark = root.classList.toggle("dark");

    localStorage.setItem("theme", isDark ? "dark" : "light");
  });
}

const navItems = document.querySelectorAll(".nav-item");

function setActiveItem(activeItem) {
  navItems.forEach((item) => {
    const marker = item.querySelector(".nav-marker");
    const iconWrap = item.querySelector(".nav-icon-wrap");
    const label = item.querySelector(".nav-label");

    item.classList.remove("bg-foreground/7");
    marker.classList.remove("opacity-100");
    marker.classList.add("opacity-0");
    iconWrap.classList.remove("text-primary", "group-hover:text-primary");
    iconWrap.classList.add("text-foreground/25", "group-hover:text-foreground/72");
    label.classList.remove("text-foreground", "group-hover:text-foreground");
    label.classList.add("text-foreground/58", "group-hover:text-foreground/90");
  });

  const activeMarker = activeItem.querySelector(".nav-marker");
  const activeIconWrap = activeItem.querySelector(".nav-icon-wrap");
  const activeLabel = activeItem.querySelector(".nav-label");

  activeItem.classList.add("bg-foreground/7");
  activeMarker.classList.remove("opacity-0");
  activeMarker.classList.add("opacity-100");
  activeIconWrap.classList.remove(
    "text-foreground/25",
    "group-hover:text-foreground/72"
  );
  activeIconWrap.classList.add("text-primary", "group-hover:text-primary");
  activeLabel.classList.remove(
    "text-foreground/58",
    "group-hover:text-foreground/90"
  );
  activeLabel.classList.add("text-foreground", "group-hover:text-foreground");
}

navItems.forEach((item) => {
  item.addEventListener("click", () => setActiveItem(item));
});

if (navItems[0]) {
  setActiveItem(navItems[0]);
}
