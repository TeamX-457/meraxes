# Meraxes — Design System & Style Guide

> **Platform:** Chatbot builder & embedding platform
> **Theme system:** Light/Dark via `.dark` class on `<body>`
> **CSS framework:** Tailwind CSS v4 (Browser build) with custom `@theme` config
> **Icons:** Lucide + Font Awesome 7

---

## 1. Brand Identity

| Element | Value |
|---|---|
| Product name | Meraxes |
| Tagline | CHATBOT PLATFORM |
| Logo mark | `fa-solid fa-code` in a rounded square, blue background |
| Logo shadow | `0 12px 25px rgba(30, 157, 241, 0.32)` |

---

## 2. Color Tokens

All colors are defined as CSS variables via Tailwind's `@theme` block and must not be hardcoded.

### Light Mode (default)

| Token | Value | Usage |
|---|---|---|
| `--color-background` | `#e7e9ea` | Page background |
| `--color-foreground` | `#000000` | Text, icons |
| `--color-primary` | `#1e9df1` | CTAs, active states, logo, nav markers |
| `--color-primary-foreground` | `#ffffff` | Text on primary |
| `--color-secondary` | `#0f1419` | Secondary surfaces |
| `--color-secondary-foreground` | `#ffffff` | Text on secondary |
| `--color-accent-background` | `#e3ecf6` | Sidebar, card backgrounds |
| `--color-accent-foreground` | `#1e9df1` | Accent text/icons |

### Dark Mode (`.dark` class on `<body>`)

| Token | Value | Usage |
|---|---|---|
| `--color-background` | `#000000` | Page background |
| `--color-foreground` | `#e7e9ea` | Text, icons |
| `--color-primary` | `#1c9cf0` | CTAs, active states |
| `--color-accent-background` | `#061622` | Sidebar, card backgrounds |
| `--color-secondary` | `#f0f3f4` | Secondary surfaces |
| `--color-secondary-foreground` | `#0f1419` | Text on secondary |

### Opacity Scale (foreground tints)

Applied as Tailwind opacity modifiers on `text-foreground` and `bg-foreground`:

| Usage | Class example | Approximate opacity |
|---|---|---|
| Primary text | `text-foreground/85` | 85% |
| Body text | `text-foreground/80` | 80% |
| Nav labels (default) | `text-foreground/58` | 58% |
| Muted labels | `text-foreground/50` | 50% |
| Disabled / subtle | `text-foreground/35` | 35% |
| Very subtle | `text-foreground/25` | 25% |
| Border / divider | `border-foreground/10` | 10% |
| Section divider | `bg-foreground/6` | 6% |
| Hover background | `bg-foreground/5` | 5% |

---

## 3. Typography

### Font Families

| Token | Primary (custom) | Fallback | Usage |
|---|---|---|---|
| `--font-heading` | `Canela` | `Instrument Serif` | Logotype, section headers, display text |
| `--font-body` | `Neue-Montreal` | `Inter` | All UI text, nav labels, buttons, captions |

> **Note:** `Canela` and `Neue-Montreal` are custom/licensed fonts loaded via `/frontend/assets/style.css`. `Instrument Serif` and `Inter` are Google Fonts fallbacks.

### Type Scale

| Role | Class | Notes |
|---|---|---|
| Logotype | `font-heading text-[2rem] leading-none` | Product name in sidebar |
| Section label | `font-heading text-[13px] tracking-[0.28em]` | All-caps workspace labels |
| Platform tagline | `font-body text-[10px] tracking-[0.35em]` | Below logo, uppercase spaced |
| Nav label | `font-body text-[14px]` | Sidebar navigation items |
| Button text | `font-body text-[14px] font-light tracking-wide` | Theme toggle button |
| Caption / subtext | `font-body text-xs` | Workspace description |

---

## 4. Layout

### Shell Structure

```
<body>                          → bg-accent-background
  .min-h-screen.lg:flex         → root flex shell
    <aside>                     → sidebar (23% width, min 300px, full height)
      [logo area]
      [workspace header]
      <ul> nav items </ul>
      [footer / theme toggle]
    </aside>
    [main content area]         → flex-1 (not yet in template)
```

### Sidebar Specs

| Property | Value |
|---|---|
| Width | `lg:w-[23%] lg:min-w-[300px]` |
| Height | `lg:h-[100dvh]` |
| Background | `bg-accent-background` |
| Right border | `border-r border-foreground/10` |
| Padding (logo zone) | `px-8 py-5` |
| Padding (section header) | `px-8 pt-7 pb-3` |
| Nav list padding | `px-3 pb-4` |

---

## 5. Navigation Items

### Anatomy

Each `<li>` nav item is a flex row with four layers:

```
<li .nav-item>
  <span .nav-marker>      ← left edge active indicator (vertical bar)
  <span .nav-icon-wrap>   ← icon container (fixed w-5)
  <span .nav-label>       ← text label
```

### States

| State | Background | Label opacity | Icon opacity | Marker |
|---|---|---|---|---|
| Default | transparent | `text-foreground/58` | `text-foreground/25` | `opacity-0` |
| Hover | `bg-foreground/5` | `text-foreground/90` | `text-foreground/72` | `opacity-0` |
| Active | — | `text-foreground/90` | `text-foreground` | `opacity-100`, `bg-primary` |

### Nav Marker (active indicator)

```
absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-r-sm bg-primary
transition duration-200
```

A 2px-wide vertical pill anchored to the left edge of the sidebar panel (not the `<li>` padding).

### Nav Item Base Classes

```
group relative flex cursor-pointer items-center gap-4
rounded-2xl px-5 py-3
transition duration-200 ease-out
hover:bg-foreground/5
```

### Dividers Between Nav Groups

```html
<div class="mx-5 my-2 h-px bg-foreground/6"></div>
```

---

## 6. Iconography

### Icon Libraries

| Library | Usage | Load method |
|---|---|---|
| Lucide | Primary UI icons (nav, actions) | `unpkg.com/lucide@latest` → `lucide.createIcons()` |
| Font Awesome 7 | Brand / decorative (logo mark) | cdnjs stylesheet |

### Icon Sizing

```
h-[15px] w-[15px]       → standard nav icons
text-[15px]             → Lucide icons using font sizing
text-sm                 → FA icons inside logo mark
```

### Icon Color Pattern

Icons inside `.nav-icon-wrap` inherit from the wrapper:
- Default: `text-foreground/25`
- Hover: `text-foreground/72` (via `group-hover`)
- Active: `text-foreground opacity-100`

---

## 7. Buttons

### Theme Toggle Button

```
font-body w-full rounded-lg px-8 py-2
text-[14px] font-light tracking-wide
text-foreground/75
transition duration-200
hover:bg-foreground/5 hover:text-foreground
```

Placed in the sidebar footer, full width, ghost style. No border, no background at rest.

---

## 8. Effects & Motion

### Logo Shadow (Primary Glow)

```css
box-shadow: 0 12px 25px rgba(30, 157, 241, 0.32);
```

Applied to the logo mark container. Recreate this effect for any prominent primary-colored element.

### Transitions

All interactive elements use:
```
transition duration-200 ease-out
```

For color/opacity shifts on hover. Do not use `ease-in-out` or longer durations for nav interactions.

### Backdrop blur (sidebar)

```
backdrop-blur-sm
```

Applied to the sidebar `<aside>` for glass-like depth on overlapping content.

---

## 9. Borders & Dividers

| Usage | Class |
|---|---|
| Sidebar right edge | `border-r border-foreground/10` |
| Logo area bottom | `border-b border-foreground/10` |
| Sidebar footer top | `border-t border-foreground/10` |
| Nav group separator | `h-px bg-foreground/6` (inside `mx-5 my-2`) |

---

## 10. Dark Mode

Dark mode is toggled by adding/removing the `.dark` class on `<body>` (via `#toggleTheme` button). All color tokens automatically remap — no component-level `dark:` overrides should be needed if tokens are used consistently.

```js
// Pattern (inferred)
document.getElementById('toggleTheme').addEventListener('click', () => {
  document.body.classList.toggle('dark');
});
```

---

## 11. Design Principles

1. **Token-first.** Never hardcode colors. Always reference `--color-*` tokens via Tailwind utilities.
2. **Opacity for hierarchy.** Foreground tints (`/10`, `/25`, `/58`, `/85`) create depth without new color values.
3. **Subtle motion.** Transitions are `200ms ease-out` — fast and purposeful, never decorative for its own sake.
4. **Left-edge active states.** Navigation active indicators live on the container's left border, not within the item's padding box.
5. **Font pairing is identity.** `Canela` (display) + `Neue-Montreal` (body) define the brand voice. Never substitute with system fonts in production builds.
6. **Group-based hover.** Use Tailwind's `group` / `group-hover:` pattern for coordinating icon + label + marker state changes from a single parent hover.

---

## 12. File Conventions

| Path | Purpose |
|---|---|
| `/frontend/assets/style.css` | Custom fonts (`Canela`, `Neue-Montreal`), base resets |
| `/frontend/assets/index.js` | Page behavior, theme toggle, nav active state logic |
| Tailwind config | Inline `<style type="text/tailwindcss">` block in each HTML file |