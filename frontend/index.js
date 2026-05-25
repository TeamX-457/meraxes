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
toggleBtn.addEventListener("click", () => {
  const isDark = root.classList.toggle("dark");

  localStorage.setItem("theme", isDark ? "dark" : "light");
});