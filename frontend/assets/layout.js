// layout.js
// Call renderLayout() on every page, passing a config object for page-specific header content.
// Example: renderLayout({ title: "Chatbot Platform", subtitle: "Embed on any website", activeNav: "my-bots" })

const NAV_ITEMS = [
  {
    id: "my-bots",
    icon: "ChartNetwork",
    label: "My bots",
    group: 1,
  },
  {
    id: "analytics",
    icon: "chart-column",
    label: "Analytics",
    group: 1,
  },
  {
    id: "create-bot",
    icon: "plus",
    label: "Create bot",
    group: 1,
  },
  {
    id: "customer-questions",
    icon: "MessageSquare",
    label: "Customer questions",
    group: 2,
  },
  {
    id: "test-chat",
    icon: "message-circle",
    label: "Test chat",
    group: 2,
  },
  {
    id: "embed",
    icon: "ChevronsLeftRightEllipsis",
    label: "Embed on website",
    group: 3,
  },
  {
    id: "image-studio",
    icon: "Images",
    label: "Image studio",
    group: 3,
  },
];

function buildNavItem(item, isActive) {
  return `
    <li
      data-nav-id="${item.id}"
      class="nav-item group relative flex cursor-pointer items-center gap-4 rounded-2xl px-5 py-3 transition duration-200 ease-out hover:bg-foreground/5 ${isActive ? "active" : ""}"
    >
      <span class="nav-marker absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-r-sm bg-primary transition duration-200 ${isActive ? "opacity-100" : "opacity-0"}"></span>
      <span class="nav-icon-wrap flex w-5 justify-center transition duration-200 ${isActive ? "text-primary" : "text-foreground/25 group-hover:text-foreground/72"}">
        <i data-lucide="${item.icon}" class="h-[15px] w-[15px] text-foreground"></i>
      </span>
      <span class="nav-label font-body text-[14px] transition duration-200 ${isActive ? "text-foreground/90" : "text-foreground/58 group-hover:text-foreground/90"}">
        ${item.label}
      </span>
    </li>
  `;
}

function buildNavList(activeNav) {
  let html = "";
  let currentGroup = null;

  for (const item of NAV_ITEMS) {
    if (currentGroup !== null && item.group !== currentGroup) {
      html += `<div class="mx-5 my-2 h-px bg-foreground/6"></div>`;
    }
    currentGroup = item.group;
    html += buildNavItem(item, item.id === activeNav);
  }

  return html;
}

export function renderLayout({
  title = "",
  subtitle = "",
  activeNav = "",
} = {}) {
  // Inject the aside + header shell before the existing <main>
  const main = document.querySelector("main");
  if (!main) {
    console.error("[layout.js] No <main> element found on page.");
    return;
  }

  const wrapper = document.createElement("div");
  wrapper.className = "min-h-screen lg:flex";

  wrapper.innerHTML = `
    <!-- ASIDE / SIDEBAR -->
    <aside class="border-foreground/10 flex bg-accent-background text-[color:var(--color-foreground)] lg:h-[100dvh] lg:w-[23%] lg:min-w-[300px] flex-col border-r backdrop-blur-sm">
      <!-- Logo -->
      <div class="flex items-center gap-3 border-b border-foreground/10 px-8 py-5">
        <div class="flex h-10 w-10 items-center justify-center rounded-full bg-primary shadow-[0_12px_25px_rgba(30,157,241,0.32)]">
          <i class="fa-solid fa-code !text-white text-sm opacity-100"></i>
        </div>
        <div class="flex flex-col">
          <h1 class="font-heading text-[2rem] leading-none text-foreground/85">Meraxes</h1>
          <p class="font-body text-[10px] tracking-[0.35em] text-foreground/35">CHATBOT PLATFORM</p>
        </div>
      </div>

      <!-- Workspace label -->
      <div class="px-8 pt-7 pb-3">
        <h2 class="font-heading text-[13px] tracking-[0.28em] text-foreground/50">WORKSPACE</h2>
        <p class="mt-1 font-body text-xs text-foreground/80">Embed on any website</p>
      </div>

      <!-- Nav -->
      <ul class="flex flex-1 flex-col gap-1 px-3 pb-4" id="nav-list">
        ${buildNavList(activeNav)}
      </ul>

      <!-- Theme toggle -->
      <div class="border-t border-foreground/10 p-3">
        <button
          id="toggleTheme"
          class="font-body w-full rounded-lg px-8 py-2 text-[14px] font-light tracking-wide text-foreground/75 transition duration-200 hover:bg-foreground/5 hover:text-foreground"
        >
          Switch theme
        </button>
      </div>
    </aside>

    <!-- MAIN COLUMN -->
    <div class="flex flex-col lg:w-[77%]" id="page-column">
      <!-- HEADER / TOPBAR -->
      <header class="flex justify-between px-4 pb-4 pt-8">
        <div>
          <h1 class="font-heading text-5xl text-foreground" id="layout-title">${title}</h1>
          <p class="font-body opacity-60 text-foreground" id="layout-subtitle">${subtitle}</p>
        </div>
      </header>
      <!-- Page content slot -->
      <div id="layout-content-slot"></div>
    </div>
  `;

  // Wrap the body content in the new shell
  document.body.className = "bg-accent-background antialiased";
  document.body.innerHTML = "";
  document.body.appendChild(wrapper);

  // Move the original <main> into the content slot
  document.getElementById("layout-content-slot").replaceWith(main);

  // Re-init Lucide icons (they were wiped when we rebuilt the DOM)
  if (window.lucide) lucide.createIcons();

  // Theme toggle
  initTheme();
}

function initTheme() {
  const btn = document.getElementById("toggleTheme");
  if (!btn) return;

  // Restore saved theme
  if (localStorage.getItem("theme") === "dark") {
    document.documentElement.classList.add("dark");
  }

  btn.addEventListener("click", () => {
    document.documentElement.classList.toggle("dark");
    localStorage.setItem(
      "theme",
      document.documentElement.classList.contains("dark") ? "dark" : "light",
    );
  });
}
