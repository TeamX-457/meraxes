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
      aria-current="${isActive ? "page" : "false"}"
      class="nav-item group relative flex cursor-pointer items-center gap-4 rounded-2xl px-5 py-3 transition duration-200 ease-out hover:bg-foreground/5 ${isActive ? "active bg-foreground/7" : ""}"
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

function getStoredTheme() {
  try {
    return localStorage.getItem("theme");
  } catch {
    return null;
  }
}

function setStoredTheme(theme) {
  try {
    localStorage.setItem("theme", theme);
  } catch {
    // Ignore storage failures and keep the current in-memory theme.
  }
}

function setThemeState() {
  const savedTheme = getStoredTheme();
  const systemDark = window.matchMedia("(prefers-color-scheme: dark)").matches;

  if (savedTheme === "dark" || (!savedTheme && systemDark)) {
    document.documentElement.classList.add("dark");
  }
}

function syncThemeButtons() {
  const isDark = document.documentElement.classList.contains("dark");
  document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
    button.setAttribute("aria-pressed", String(isDark));
  });
}

function initThemeToggle() {
  const toggleButtons = document.querySelectorAll("[data-theme-toggle]");
  if (!toggleButtons.length) return;

  setThemeState();
  syncThemeButtons();

  toggleButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const isDark = document.documentElement.classList.toggle("dark");

      setStoredTheme(isDark ? "dark" : "light");
      syncThemeButtons();
    });
  });
}

function applyNavItemState(item, isActive) {
  const marker = item.querySelector(".nav-marker");
  const iconWrap = item.querySelector(".nav-icon-wrap");
  const label = item.querySelector(".nav-label");

  item.classList.toggle("bg-foreground/7", isActive);
  item.classList.toggle("active", isActive);
  item.setAttribute("aria-current", isActive ? "page" : "false");

  if (marker) {
    marker.classList.toggle("opacity-100", isActive);
    marker.classList.toggle("opacity-0", !isActive);
  }

  if (iconWrap) {
    iconWrap.classList.toggle("text-primary", isActive);
    iconWrap.classList.toggle("group-hover:text-primary", isActive);
    iconWrap.classList.toggle("text-foreground/25", !isActive);
    iconWrap.classList.toggle("group-hover:text-foreground/72", !isActive);
  }

  if (label) {
    label.classList.toggle("text-foreground", isActive);
    label.classList.toggle("group-hover:text-foreground", isActive);
    label.classList.toggle("text-foreground/58", !isActive);
    label.classList.toggle("group-hover:text-foreground/90", !isActive);
  }
}

function syncActiveNav(activeNav) {
  document.querySelectorAll("[data-nav-id]").forEach((item) => {
    applyNavItemState(item, item.dataset.navId === activeNav);
  });
}

let closeMobileMenu = () => {};

function initNavState(activeNav) {
  syncActiveNav(activeNav);

  document.querySelectorAll("[data-nav-id]").forEach((item) => {
    item.addEventListener("click", () => {
      syncActiveNav(item.dataset.navId);
      closeMobileMenu();
    });
  });
}

function initMobileMenu() {
  const drawer = document.querySelector("[data-layout-drawer]");
  const overlay = document.querySelector("[data-layout-overlay]");
  const openButtons = document.querySelectorAll("[data-layout-open-menu]");
  const closeButtons = document.querySelectorAll("[data-layout-close-menu]");
  if (!drawer || !overlay || !openButtons.length) return;

  const closeMenu = () => {
    drawer.classList.add("-translate-x-full");
    drawer.classList.remove("translate-x-0");
    overlay.classList.add("opacity-0", "pointer-events-none");
    overlay.classList.remove("opacity-100", "pointer-events-auto");
    document.body.style.overflow = "";
  };

  closeMobileMenu = closeMenu;

  const openMenu = () => {
    drawer.classList.remove("-translate-x-full");
    drawer.classList.add("translate-x-0");
    overlay.classList.remove("opacity-0", "pointer-events-none");
    overlay.classList.add("opacity-100", "pointer-events-auto");
    document.body.style.overflow = "hidden";
  };

  openButtons.forEach((button) => button.addEventListener("click", openMenu));
  closeButtons.forEach((button) => button.addEventListener("click", closeMenu));
  overlay.addEventListener("click", closeMenu);

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeMenu();
  });
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
  wrapper.className = "relative min-h-screen overflow-x-hidden text-foreground";
  wrapper.style.setProperty("--layout-sidebar-width", "clamp(300px, 23vw, 360px)");
  wrapper.style.setProperty("--layout-header-mobile-height", "5rem");
  wrapper.style.setProperty("--layout-header-desktop-height", "8.5rem");

  wrapper.innerHTML = `
    <div
      data-layout-overlay
      class="fixed inset-0 z-40 bg-black/40 opacity-0 pointer-events-none transition-opacity duration-300 lg:hidden"
      aria-hidden="true"
    ></div>

    <!-- MOBILE / DESKTOP SIDEBAR -->
    <aside
      data-layout-drawer
      class="fixed inset-y-0 left-0 z-50 flex w-[min(88vw,20rem)] -translate-x-full flex-col border-r border-foreground/10 bg-accent-background text-foreground shadow-[0_24px_60px_rgba(0,0,0,0.24)] transition-transform duration-300 ease-out lg:w-[var(--layout-sidebar-width)] lg:translate-x-0 lg:shadow-none"
    >
      <div class="flex items-center justify-between gap-3 border-b border-foreground/10 px-6 py-5 lg:justify-start lg:px-8">
        <div class="flex items-center gap-3">
          <div class="flex h-10 w-10 items-center justify-center rounded-full bg-primary shadow-[0_12px_25px_rgba(30,157,241,0.32)]">
            <i class="fa-solid fa-code !text-white text-sm opacity-100"></i>
          </div>
          <div class="flex flex-col">
            <h1 class="font-heading text-[2rem] leading-none text-foreground/85">Meraxes</h1>
            <p class="font-body text-[10px] tracking-[0.35em] text-foreground/35">CHATBOT PLATFORM</p>
          </div>
        </div>

        <button
          type="button"
          data-layout-close-menu
          class="inline-flex h-10 w-10 items-center justify-center rounded-full border border-foreground/10 bg-foreground/5 text-foreground/70 transition hover:bg-foreground/10 lg:hidden"
          aria-label="Close menu"
        >
          <i data-lucide="X" class="h-4 w-4"></i>
        </button>
      </div>

      <div class="px-6 pt-6 pb-3 lg:px-8 lg:pt-7">
        <h2 class="font-heading text-[13px] tracking-[0.28em] text-foreground/50">WORKSPACE</h2>
        <p class="mt-1 font-body text-xs text-foreground/80">Embed on any website</p>
      </div>

      <div class="flex-1 overflow-y-auto px-3 pb-4">
        <ul class="flex flex-col gap-1" id="nav-list">
          ${buildNavList(activeNav)}
        </ul>
      </div>

      <div class="border-t border-foreground/10 p-3">
        <button
          id="toggleTheme"
          data-theme-toggle
          class="font-body w-full rounded-lg px-8 py-2 text-[14px] font-light tracking-wide text-foreground/75 transition duration-200 hover:bg-foreground/5 hover:text-foreground"
          type="button"
        >
          Switch theme
        </button>
      </div>
    </aside>

    <!-- MAIN COLUMN -->
    <div class="relative flex min-w-0 min-h-screen w-full flex-col lg:pl-[var(--layout-sidebar-width)]">
      <header class="fixed left-0 right-0 top-0 z-100 border-b border-foreground/10 bg-accent-background backdrop-blur-sm lg:left-[var(--layout-sidebar-width)] lg:right-auto lg:w-[calc(100%-var(--layout-sidebar-width))] lg:border-0">
        <div class="flex items-center gap-4 px-4 py-4 sm:px-6 lg:hidden">
          <button
            type="button"
            data-layout-open-menu
            class="inline-flex h-11 w-11 items-center justify-center rounded-full border border-foreground/10 bg-foreground/5 text-foreground/80 transition hover:bg-foreground/10"
            aria-label="Open menu"
          >
            <i data-lucide="Menu" class="h-5 w-5"></i>
          </button>
          <div class="min-w-0 flex-1">
            <h1 class="truncate font-heading text-2xl leading-none text-foreground" id="layout-title-mobile">${title}</h1>
            <p class="mt-1 truncate font-body text-xs text-foreground/60" id="layout-subtitle-mobile">${subtitle}</p>
          </div>
        </div>

        <div class="hidden items-end justify-between gap-6 px-8 pt-8 pb-4 lg:flex">
          <div class="min-w-0">
            <h1 class="font-heading text-5xl leading-none text-foreground" id="layout-title">${title}</h1>
            <p class="mt-2 font-body text-sm text-foreground/60" id="layout-subtitle">${subtitle}</p>
          </div>
        </div>
      </header>

      <div class="flex-1 px-4 pb-8 pt-[var(--layout-header-mobile-height)] sm:px-6 sm:pb-10 lg:px-8 lg:pb-16 lg:pt-[var(--layout-header-desktop-height)]">
        <div id="layout-content-slot" class="mx-auto w-full max-w-7xl"></div>
      </div>
    </div>
  `;

  // Wrap the body content in the new shell
  document.body.className = " text-foreground bg-secondary-foreground antialiased overflow-x-hidden";
  document.body.innerHTML = "";
  document.body.appendChild(wrapper);

  // Move the original <main> into the content slot
  const contentSlot = document.getElementById("layout-content-slot");
  if (contentSlot) {
    main.classList.add("w-full", "min-w-0");
    contentSlot.appendChild(main);
  }

  // Re-init Lucide icons (they were wiped when we rebuilt the DOM)
  if (window.lucide) lucide.createIcons();

  // Theme toggle
  initThemeToggle();
  initNavState(activeNav);
  initMobileMenu();
}
