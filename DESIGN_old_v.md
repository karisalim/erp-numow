# 🎨 Cloud POS System — Design System (DESIGN.md)

**Version:** 2.0  
**Last Updated:** May 2026  
**Format:** Cross-tool compatible (Stitch, Claude Design, v0, Figma)

---

## 📋 Design System Overview

This DESIGN.md serves as the **single source of truth** for all UI/UX decisions across:

- POS PWA (Cashier)
- Admin Dashboard
- Customer Display
- Mobile Apps (Future)

**Key Principle:** All design artifacts (Stitch, Figma, code components) read and honor this file first.

---

## 🎯 Design Philosophy

### Core Principles

1. **Speed First** — Cashiers work under pressure. Every pixel must serve checkout speed.
2. **Keyboard Optimized** — Experienced cashiers don't use mice. Tab navigation, keyboard shortcuts.
3. **Minimal Cognitive Load** — One choice per screen. No complex decision trees.
4. **Hardware-Aware** — Barcode scanner always focused. Printer always ready.
5. **Accessible** — WCAG 2.1 AA standard minimum. Works with screen readers.
6. **Enterprise SaaS** — Calm, professional, trustworthy. Inspired by Stripe, Linear, Notion.

### Design Style Keywords

- **Calm** — No unnecessary animations
- **Modern** — Contemporary, clean aesthetic
- **Minimal** — Every element has purpose
- **Professional** — Trust-building design
- **Warm** — Human-centered, not sterile

### Inspired By

- Stripe Dashboard (simplicity)
- Linear (minimalism)
- Notion (visual hierarchy)
- Square POS (fast checkout)
- Foodics (restaurant-specific UX)

---

## 🎨 Color Palette

### Primitive Colors

These are the base colors. All UI uses semantic colors that reference these.

#### Neutrals (Grays)

| Name | Hex | Usage | Contrast Score |
|------|-----|-------|-----------------|
| neutral-50 | #FAFBFC | Lightest background | N/A |
| neutral-100 | #F3F4F6 | Page background | N/A |
| neutral-200 | #E5E7EB | Subtle border | N/A |
| neutral-300 | #D1D5DB | Standard border | N/A |
| neutral-400 | #9CA3AF | Disabled text | 4.5:1 |
| neutral-500 | #6B7280 | Secondary text | 7:1 |
| neutral-600 | #4B5563 | Primary text | 11:1 |
| neutral-700 | #374151 | Heading text | 14:1 |
| neutral-800 | #1F2937 | Darkest text | 17:1 |
| neutral-900 | #111827 | Very dark text | 19:1 |

#### Primary (Blue)

Used for actions, primary buttons, links

| Name | Hex | Usage |
|------|-----|-------|
| primary-50 | #EFF6FF | Subtle background |
| primary-100 | #DBEAFE | Light background |
| primary-500 | #3B82F6 | Primary button, links |
| primary-600 | #2563EB | Hover state |
| primary-700 | #1D4ED8 | Active/pressed state |

#### Success (Green)

Used for positive actions, confirmations

| Name | Hex |
|------|-----|
| success-500 | #10B981 |
| success-600 | #059669 |

#### Error (Red)

Used for destructive actions, errors

| Name | Hex |
|------|-----|
| error-500 | #EF4444 |
| error-600 | #DC2626 |

#### Warning (Amber)

Used for warnings, cautions

| Name | Hex |
|------|-----|
| warning-500 | #F59E0B |
| warning-600 | #D97706 |

#### Info (Cyan)

Used for informational messages

| Name | Hex |
|------|-----|
| info-500 | #06B6D4 |
| info-600 | #0891B2 |

---

### Semantic Colors

These reference primitives and have specific meanings

#### Background

| Token | Color | Usage |
|-------|-------|-------|
| `bg-primary` | neutral-50 | Main page background |
| `bg-secondary` | neutral-100 | Card backgrounds, surfaces |
| `bg-tertiary` | neutral-200 | Subtle backgrounds, hover states |
| `bg-overlay` | rgba(0,0,0,0.5) | Modal overlay |

#### Text

| Token | Color | Usage |
|-------|-------|-------|
| `text-primary` | neutral-900 | Headings, primary text |
| `text-secondary` | neutral-600 | Body text, descriptions |
| `text-tertiary` | neutral-500 | Secondary information |
| `text-disabled` | neutral-400 | Disabled elements |
| `text-inverse` | neutral-50 | Text on dark backgrounds |

#### Interactive

| Token | Color | Usage |
|-------|-------|-------|
| `interactive-primary` | primary-500 | Primary buttons, links |
| `interactive-primary-hover` | primary-600 | Hover state |
| `interactive-primary-active` | primary-700 | Pressed state |
| `interactive-danger` | error-500 | Delete, destructive actions |
| `interactive-success` | success-500 | Confirmations, success states |

#### Borders

| Token | Color | Usage |
|-------|-------|-------|
| `border-subtle` | neutral-200 | Light dividers |
| `border-default` | neutral-300 | Standard borders |
| `border-strong` | neutral-500 | Emphasized borders |

#### Status

| Token | Color | Usage |
|-------|-------|-------|
| `status-success` | success-500 | ✓ Items complete |
| `status-warning` | warning-500 | ⚠ Items need attention |
| `status-error` | error-500 | ✗ Items in error |
| `status-info` | info-500 | ℹ Informational |

---

## 🏗️ Token Architecture (Enterprise-Grade)

### Token Layering System

This system uses **3-layer token architecture** for consistency, theming, and maintainability.

```
Layer 1: PRIMITIVE TOKENS (Fixed values)
  ↓
  --color-blue-500: #3B82F6
  --space-4: 16px
  --shadow-md: 0 4px 6px rgba(0,0,0,0.08)
  
  ↓
Layer 2: SEMANTIC TOKENS (Meaning-based)
  ↓
  --color-action-primary: var(--color-blue-500)
  --color-bg-primary: var(--color-neutral-50)
  --space-component-padding: var(--space-4)
  
  ↓
Layer 3: COMPONENT TOKENS (Usage-specific)
  ↓
  --button-primary-bg: var(--color-action-primary)
  --card-padding: var(--space-component-padding)
  --card-shadow: var(--shadow-md)
```

### Why This Matters

✅ **Theming:** Change primitives, everything updates  
✅ **Whitelabel:** Swap brand colors for clients  
✅ **Runtime Switching:** Change theme without reload  
✅ **Future Branding:** Easy to extend  
✅ **AI Tooling:** Explicit contracts for code generation  

### Token Naming Convention

```
--{category}-{semantic}-{state}

Examples:
--color-action-primary
--color-text-disabled
--space-section-gap
--shadow-elevation-lg
--state-hover-opacity
```

---

## 📐 Shadow / Elevation System

Enterprise apps need explicit elevation hierarchy.

### Shadow Tokens

| Token | Value | Usage |
|-------|-------|-------|
| `--shadow-none` | none | Flat elements |
| `--shadow-sm` | 0 1px 2px rgba(0,0,0,0.05) | Subtle, borders |
| `--shadow-md` | 0 4px 6px rgba(0,0,0,0.08) | Cards, standard |
| `--shadow-lg` | 0 10px 15px rgba(0,0,0,0.12) | Modals, dropdowns |
| `--shadow-xl` | 0 20px 25px rgba(0,0,0,0.15) | Prominent overlays |

### Dark Mode Shadows

Dark mode needs adjusted shadows (lighter, not darker).

```css
/* Light mode */
--shadow-md: 0 4px 6px rgba(0,0,0,0.08);

/* Dark mode */
--shadow-md: 0 4px 6px rgba(0,0,0,0.25);
```

---

## 🔢 Z-Index Scale

**Never use arbitrary z-index values.** This prevents layering chaos.

| Token | Value | Layer | Usage |
|-------|-------|-------|-------|
| `--z-base` | 1 | Base | Normal content |
| `--z-sticky-header` | 10 | Sticky | Sticky headers, footers |
| `--z-dropdown` | 1000 | Interactive | Dropdown menus |
| `--z-sticky-modal` | 1020 | Sticky modal | Modals on top of modals |
| `--z-modal` | 1100 | Modal layer | Main modals, popovers |
| `--z-toast` | 1200 | Toast layer | Notifications, alerts |
| `--z-tooltip` | 1300 | Tooltip | Tooltips (always topmost) |

**Rule:** Never go above `--z-tooltip`. Never use values outside this scale.

---

## 🎯 State Tokens

### Hover / Active / Disabled

Instead of calculating states, use explicit tokens.

```css
/* OLD (BAD) */
opacity: 0.8;

/* NEW (GOOD) */
opacity: var(--state-disabled-opacity);
```

### State Token Library

| Token | Value | Usage |
|-------|-------|-------|
| `--state-hover-opacity` | 0.9 | Hover backgrounds |
| `--state-active-opacity` | 0.95 | Pressed buttons |
| `--state-disabled-opacity` | 0.5 | Disabled elements |
| `--state-focus-outline-width` | 2px | Focus ring |
| `--state-focus-outline-offset` | 2px | Focus ring offset |

### Interaction States by Color

```css
/* Primary button states */
--button-primary-default: var(--color-action-primary);
--button-primary-hover: var(--color-primary-600);
--button-primary-active: var(--color-primary-700);
--button-primary-disabled: var(--color-neutral-300);

/* Text at different opacities */
--text-default-opacity: 1;
--text-secondary-opacity: 0.7;
--text-disabled-opacity: 0.5;
```

---

## 📊 Data Density Modes

Enterprise systems need flexible density for power users vs. casual users.

### Three Modes

| Mode | Usage | User Type |
|------|-------|-----------|
| **Touch** | Tablet/mobile, large targets | Casual, mobile |
| **Comfortable** | Default, balanced | Most users |
| **Compact** | Power users, much data | Experienced cashiers, analysts |

### Token Variations by Mode

```css
/* Component sizing scales */

/* Touch mode (most spacing) */
--row-height-touch: 56px;
--input-height-touch: 48px;
--spacing-component-touch: 20px;

/* Comfortable mode (default) */
--row-height-comfortable: 40px;
--input-height-comfortable: 40px;
--spacing-component-comfortable: 16px;

/* Compact mode (power users) */
--row-height-compact: 32px;
--input-height-compact: 32px;
--spacing-component-compact: 12px;
```

### How It's Used

```html
<div data-density="comfortable">
  <!-- Uses comfortable tokens by default -->
</div>

<div data-density="compact">
  <!-- Uses compact tokens for power users -->
</div>
```

**POS-Specific:** Fast cashiers prefer compact mode. Slow periods use comfortable.

---

## 🔤 Typography System

### Font Families

```css
--font-heading: "Segoe UI", -apple-system, BlinkMacSystemFont, sans-serif;
--font-body: "Segoe UI", -apple-system, BlinkMacSystemFont, sans-serif;
--font-mono: "Monaco", "Courier New", monospace;
```

**Why Segoe UI?**
- System font (fast loading)
- Excellent legibility
- Native on Windows, good fallback on Mac/Linux
- Clean, modern appearance

### Font Sizes & Line Heights

| Token | Size | Line Height | Weight | Usage |
|-------|------|-------------|--------|-------|
| `display-large` | 40px | 48px | 600 | App title, hero |
| `display-medium` | 32px | 40px | 600 | Page title |
| `heading-1` | 28px | 36px | 600 | Section heading |
| `heading-2` | 24px | 32px | 600 | Subsection |
| `heading-3` | 20px | 28px | 600 | Sub-subsection |
| `body-large` | 18px | 28px | 400 | Important body |
| `body-default` | 16px | 24px | 400 | Main body text |
| `body-small` | 14px | 20px | 400 | Secondary text |
| `caption` | 12px | 16px | 500 | Captions, hints |
| `label` | 12px | 16px | 600 | Form labels, badges |
| `code` | 13px | 20px | 400 | Code/terminal text |

**Font Weight Scale:**
- 400 = Regular
- 500 = Medium
- 600 = Semibold
- 700 = Bold

### Reading Metrics

- **Letter spacing:** 0px (default), 0.5px (captions)
- **Min contrast ratio:** 4.5:1 (WCAG AA)
- **Max line length:** 80 characters (readability)

---

## 📏 Spacing & Sizing System

### Base Unit

**4px grid.** All spacing is multiple of 4.

```
4px, 8px, 12px, 16px, 20px, 24px, 32px, 40px, 48px, 64px, 80px, 96px
```

### Spacing Tokens

| Token | Value | Usage |
|-------|-------|-------|
| `space-1` | 4px | Tight spacing, icon gaps |
| `space-2` | 8px | Component internal spacing |
| `space-3` | 12px | Standard padding |
| `space-4` | 16px | Regular spacing |
| `space-5` | 20px | Component padding |
| `space-6` | 24px | Section spacing |
| `space-8` | 32px | Large spacing |
| `space-10` | 40px | Extra large |
| `space-12` | 48px | Major section gap |

### Component Padding

| Component | Padding | Example |
|-----------|---------|---------|
| Button (small) | 8px 12px | 32px height |
| Button (medium) | 12px 16px | 40px height |
| Button (large) | 16px 20px | 48px height |
| Card | 20px | All sides |
| Input field | 12px 16px | Inside input box |
| Page container | 24px | Outer margin |

---

## 🎛️ Sizing Tokens

### Widths

| Token | Value | Usage |
|-------|-------|-------|
| `w-full` | 100% | Full width |
| `w-screen` | 100vw | Viewport width |
| `max-w-md` | 448px | Small modal |
| `max-w-lg` | 512px | Standard modal |
| `max-w-xl` | 640px | Wide modal |

### Heights

| Token | Value | Usage |
|-------|-------|-------|
| `h-full` | 100% | Full height |
| `h-screen` | 100vh | Full viewport |
| `h-toolbar` | 64px | Top bar height |
| `h-sidebar` | calc(100vh - 64px) | Sidebar with header |

---

## 🧩 Component Library

### 1. Button

**Purpose:** Primary interaction element

**States:** Default, Hover, Active, Disabled, Loading

#### Variants

| Variant | Background | Text | Border | Usage |
|---------|-----------|------|--------|-------|
| **Primary** | primary-500 | text-inverse | None | Main actions |
| **Secondary** | bg-secondary | primary-500 | border-default | Alternative actions |
| **Tertiary** | transparent | primary-500 | None | Less important |
| **Danger** | error-500 | text-inverse | None | Delete, destructive |
| **Ghost** | transparent | text-secondary | None | Minimal, subtle |

#### Sizes

| Size | Height | Padding | Font | Usage |
|------|--------|---------|------|-------|
| **Small** | 32px | 8px 12px | body-small | Compact UI |
| **Medium** | 40px | 12px 16px | body-default | Standard |
| **Large** | 48px | 16px 20px | body-large | Primary CTAs |

#### Button Anatomy

```
┌─────────────────────────────────┐
│  [Icon] Label [Icon] [Badge]    │  ← padding-y: space-4
│                                  │  ← padding-x: space-5
└─────────────────────────────────┘
  ↑ border-radius: 8px
  ↑ font-weight: 600
  ↑ letter-spacing: 0px
```

#### Button Rules

- Never wider than 100% of container
- Icons (if present) are 16px for small, 20px for medium, 24px for large
- Always has visible focus state (outline or shadow)
- Disabled buttons: opacity 50%, cursor not-allowed
- Loading state: show spinner, disable click

---

### 2. Input Field

**Purpose:** Text, number, email, password entry

#### States

| State | Behavior |
|-------|----------|
| Idle | Border: subtle gray, background: white |
| Focus | Border: primary blue, shadow: subtle |
| Error | Border: error red, bg: error-50 |
| Disabled | Border: gray-300, opacity: 50% |
| Filled | Border: primary, value shown |

#### Input Anatomy

```
Label (optional)
↓
┌─────────────────────────────┐
│ [Icon] Input Text  [Icon]   │
└─────────────────────────────┘
Helper text / Error message (optional)
```

#### Sizing

| Size | Height | Padding | Font |
|------|--------|---------|------|
| Small | 32px | 8px 12px | body-small |
| Medium | 40px | 12px 16px | body-default |
| Large | 48px | 16px 20px | body-large |

#### Input Rules

- Min width: 200px (unless constrained)
- Border radius: 8px
- Placeholder text: text-tertiary, italic
- Always label for accessibility
- Helper text is caption size, secondary color

---

### 3. Card

**Purpose:** Container for grouped content

#### Anatomy

```
┌──────────────────────────────┐
│ Header (optional)            │ ← padding-top: space-5
│                              │
│ Content                      │ ← padding: space-5
│                              │
│ Footer (optional)            │ ← padding-bottom: space-5
└──────────────────────────────┘
  ↑ border-radius: 12px
  ↑ border: 1px solid border-default
  ↑ background: bg-secondary
  ↑ box-shadow: subtle
```

#### Card Variants

| Variant | Border | Shadow | Usage |
|---------|--------|--------|-------|
| Elevated | 1px subtle | medium | Main content |
| Flat | 1px default | none | Secondary |
| Ghost | none | none | Minimal |

#### Card Rules

- Standard padding: 20px
- Border radius: 12px
- Min width: 300px (unless different layout)
- Max width: 100% of container
- Dark mode: bg-secondary becomes darker gray

---

### 4. Modal / Dialog

**Purpose:** Focus attention on a specific task

#### Anatomy

```
┌────────────────────────────────────┐
│ × | Title                   [Icon] │  ← Header (space-5 padding)
├────────────────────────────────────┤
│                                    │
│ Content                            │  ← padding: space-6
│                                    │
├────────────────────────────────────┤
│ [Cancel] [Primary Action]          │  ← Footer (space-5 padding)
└────────────────────────────────────┘
```

#### Modal Sizes

| Size | Width | Usage |
|------|-------|-------|
| Small | 400px | Confirmations |
| Medium | 500px | Standard dialogs |
| Large | 640px | Forms, complex content |

#### Modal Rules

- Overlay: semi-transparent black (50% opacity)
- Border radius: 12px
- Animation: fade-in 200ms
- Closes on Escape key
- Focus trap (cannot tab out)
- Centered on screen

---

### 5. Sidebar Navigation

**Purpose:** Main navigation menu

#### Anatomy

```
┌─────────────────┐
│  BRAND          │ ← 64px height
├─────────────────┤
│ ⌂ Dashboard     │ ← nav-item: 44px height
│ 📦 Products     │
│ 💳 Sales        │
│ 📊 Reports      │
│                 │
│                 │
│ ⚙ Settings      │
└─────────────────┘
```

#### Navigation Item States

| State | Background | Text | Icon |
|-------|-----------|------|------|
| Idle | transparent | text-secondary | 20px gray |
| Hover | bg-tertiary | text-secondary | 20px gray |
| Active | primary-100 | primary-700 | 20px blue |

#### Sidebar Rules

- Width: 240px (desktop), hidden on mobile
- Border-right: 1px subtle
- Background: bg-primary
- Padding: space-4
- Font size: body-default
- Icons: 20px size
- Collapsible on small screens

---

### 6. Data Table

**Purpose:** Display and interact with data

#### Anatomy

```
┌─────────┬──────────┬─────────┬────────┐
│ Header  │ Header   │ Header  │ Action │
├─────────┼──────────┼─────────┼────────┤
│ Cell    │ Cell     │ Cell    │ ⋮      │
│ Cell    │ Cell     │ Cell    │ ⋮      │
│ Cell    │ Cell     │ Cell    │ ⋮      │
└─────────┴──────────┴─────────┴────────┘
```

#### Table Rules

- Header: bold, bg-secondary, border-bottom
- Cells: padding 12px vertical, 16px horizontal
- Striped rows: alternate bg-primary and bg-secondary
- Hover row: bg-tertiary
- Sorting: click column header
- Icons in action column: 16px, hover state
- Responsive: stack on mobile

---

### 7. Badge / Label

**Purpose:** Show status, tags, labels

#### Badge Variants

| Variant | Background | Text | Usage |
|---------|-----------|------|-------|
| Success | success-50 | success-700 | Completed |
| Error | error-50 | error-700 | Error state |
| Warning | warning-50 | warning-700 | Warning |
| Info | info-50 | info-700 | Information |
| Gray | neutral-100 | neutral-700 | Default |

#### Badge Sizes

| Size | Padding | Font | Usage |
|------|---------|------|-------|
| Small | 4px 8px | caption | Tight spaces |
| Medium | 6px 12px | label | Standard |

#### Badge Rules

- Border-radius: 4px (square) or 999px (pill)
- Always has text
- Optional icon (12px before text)
- Min width: 40px
- Max width: auto (content-based)

---

### 8. Dropdown Menu

**Purpose:** Compact multi-option selector

#### Anatomy

```
┌──────────────────┐
│ Selected Value ▼ │  ← Trigger button (40px)
└──────────────────┘
        │
        ▼
     ┌────────────┐
     │ Option 1   │
     │ Option 2   │
     │ Option 3   │
     └────────────┘
```

#### Dropdown Rules

- Opens on click
- Closes on selection, Escape, or click outside
- Max height: 300px (scroll if longer)
- Z-index: 1000 (above other content)
- Animation: fade-in 150ms
- Keyboard: arrow keys to navigate, Enter to select

---

### 9. Toast / Alert

**Purpose:** Temporary notifications

#### Toast Variants

| Type | Icon | Background | Text |
|------|------|-----------|------|
| Success | ✓ | success-500 | White |
| Error | ✕ | error-500 | White |
| Warning | ⚠ | warning-500 | Dark text |
| Info | ℹ | info-500 | White |

#### Toast Rules

- Position: bottom-right (desktop), bottom-center (mobile)
- Width: 400px (max)
- Padding: 16px
- Auto-dismiss after 4 seconds (error/warning 6 seconds)
- Can have close button (×)
- Stacks: multiple toasts stack vertically
- Z-index: 1100

---

### 10. Tabs

**Purpose:** Switch between content sections

#### Anatomy

```
┌──────────────────┬──────────────────┬──────────────────┐
│ Tab 1 (Active)   │ Tab 2            │ Tab 3            │
├──────────────────┼──────────────────┼──────────────────┤
│                                                         │
│ Content for active tab                                 │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

#### Tab Rules

- Active: bottom border primary-500 (2px)
- Inactive: text-secondary
- Hover: text-primary
- Padding: 12px 16px
- Min width: 100px
- Animation: slide indicator 200ms

---

## 📱 Responsive Design

### Breakpoints

| Breakpoint | Width | Device | Sidebar |
|-----------|-------|--------|---------|
| Mobile | <640px | Phone | Hidden |
| Tablet | 640px-1024px | iPad | Collapsed |
| Desktop | >1024px | Monitor | Visible |

### Mobile-First Approach

- Start mobile, add complexity for larger screens
- Touch targets: min 44px × 44px
- Font size: 16px min (prevents auto-zoom on iOS)
- Spacing: scale down on mobile (e.g., 24px → 16px)

### Container Sizes

| Container | Max Width | Padding |
|-----------|-----------|---------|
| Page | 1440px | 24px |
| Sidebar | 240px | 16px |
| Card | 100% | 20px |
| Input | 100% (max 400px) | 12px |

---

## 🌍 Internationalization (i18n) & RTL Support

### RTL (Right-to-Left) Strategy

**Critical for MENA/Arabic markets.** Not just text direction—entire layout flips.

#### What Flips in RTL

| Element | LTR | RTL |
|---------|-----|-----|
| Text | Left-aligned | Right-aligned |
| Images | Left side | Right side |
| Flex direction | `flex-direction: row` | Reversed |
| Padding | `padding-left` | `padding-right` |
| Icons | `arrow-left` | `arrow-right` (mirrored) |
| Sidebar | Left | Right |
| Modals | Left-aligned buttons | Right-aligned |

#### CSS Logical Properties (Best Practice)

Use logical properties instead of physical directions.

```css
/* OLD (breaks in RTL) */
padding-left: 20px;
margin-right: 10px;
float: left;

/* NEW (works in both) */
padding-inline-start: 20px;  /* Left in LTR, Right in RTL */
margin-inline-end: 10px;     /* Right in LTR, Left in RTL */
float: inline-start;         /* Adaptive */
```

#### Implementation

```html
<!-- At root -->
<html dir="ltr"> or <html dir="rtl">
  <body class="lang-en"> or <body class="lang-ar">
    ...
  </body>
</html>

<!-- CSS auto-flips -->
[dir="rtl"] .sidebar { right: 0; }
[dir="ltr"] .sidebar { left: 0; }
```

### Arabic Typography Rules

Arabic has unique requirements:

| Rule | Implementation |
|------|-----------------|
| **Font** | Use: Segoe UI, Droid Arabic, Arabic Typesetting |
| **Letter spacing** | Tighter than English (0px recommended) |
| **Line height** | Slightly taller (1.6x for readability) |
| **Diacritics** | Allow space for vowel marks |
| **Kerning** | System font handles it |
| **Mixed text** | Space between Arabic and English words |

```css
[lang="ar"] {
  font-family: 'Segoe UI', 'Droid Arabic Kufi', sans-serif;
  direction: rtl;
  text-align: right;
  letter-spacing: 0;
  line-height: 1.6;
}
```

### Icon Flipping Policy

Not all icons flip. Define which do:

#### Flip These Icons (Direction-specific)

- ➜ Arrow left/right
- ⟲ Rotate
- ⇄ Swap/exchange
- ↗ Diagonal directions
- ≡ Sort ascending/descending
- ⏮ Rewind/forward
- ⚙ Settings (might)

#### DON'T Flip These Icons (Universal)

- ✓ Checkmark
- ✕ Close/X
- 🔍 Search
- 📁 Files
- 💾 Save
- 🖨️ Print
- ⚠️ Warning
- ℹ️ Info
- ➕ Plus
- ➖ Minus

### Currency & Number Formatting

```javascript
// Arabic (Egypt)
new Intl.NumberFormat('ar-EG', {
  style: 'currency',
  currency: 'EGP',
}).format(1234.56);
// Output: ١٬٢٣٤٫٥٦ ج.م.‏

// English (Egypt)
new Intl.NumberFormat('en-EG', {
  style: 'currency',
  currency: 'EGP',
}).format(1234.56);
// Output: EGP 1,234.56
```

### Date Formatting

```javascript
// Arabic dates use Hijri calendar option
new Intl.DateTimeFormat('ar-EG', {
  calendar: 'islamic',
  year: 'numeric',
  month: 'long',
  day: 'numeric',
}).format(new Date());
// Output: ١٨ ذو القعدة ١٤٤٥
```

### Arabic Numbers in Receipt

```
English (Western):  1234567890
Arabic (Eastern):   ١٢٣٤٥٦٧٨٩٠
```

**POS Receipt Rule:** Always use language-specific numerals.

```css
[lang="ar"] {
  --digit-zero: '٠';
  --digit-nine: '٩';
  /* System handles numeric conversion */
}
```

### Text Truncation & Hyphenation

Arabic words are long. Plan for it.

```css
[lang="ar"] {
  word-break: break-word;
  hyphens: auto;
  text-align: justify; /* Better for long text */
}
```

### Tables in RTL

Headers flip, content flips, alignment mirrors.

```html
<!-- LTR -->
<table>
  <thead>
    <tr>
      <th>Item</th>
      <th>Price</th>
    </tr>
  </thead>
</table>

<!-- RTL (same markup, CSS handles it) -->
<table dir="rtl">
  <thead>
    <tr>
      <th>الصنف</th>
      <th>السعر</th>
    </tr>
  </thead>
</table>
```

### Forms in RTL

Labels, inputs, help text all right-align.

```css
[dir="rtl"] input,
[dir="rtl"] label {
  text-align: right;
}

[dir="rtl"] .form-help {
  text-align: right;
  margin-right: 0;
  margin-left: 0;
}
```

### I18n Checklist

- [ ] All text is in i18n strings (not hardcoded)
- [ ] Numbers use `Intl.NumberFormat`
- [ ] Dates use `Intl.DateTimeFormat`
- [ ] Icons have flip policy defined
- [ ] CSS uses logical properties
- [ ] Sidebar/layout responsive to dir attribute
- [ ] Arabic text tested with diacritics
- [ ] Receipt formatting locale-aware
- [ ] Database stores `lang` and `locale` per tenant
- [ ] Currency display respects locale

---

## ⌨️ Keyboard & Accessibility

### Keyboard Navigation

| Key | Action |
|-----|--------|
| Tab | Move to next element |
| Shift+Tab | Move to previous |
| Enter | Activate button/link |
| Escape | Close modal/dropdown |
| Arrow Keys | Navigate menu, tabs |

### Focus States

- **Outline:** 2px primary-500, 2px offset
- **Visible always:** even with mouse
- **High contrast:** passes WCAG AA

### Screen Reader Support

- All buttons have descriptive labels
- Images have alt text
- Form fields have associated labels
- Semantic HTML (not div soup)
- ARIA labels where needed

### Color Accessibility

- Never rely on color alone
- Success/error must also have icon
- Contrast: min 4.5:1 for text
- Color-blind friendly palette

---

## 🌓 Dark Mode

Dark mode inverts:

| Light | Dark |
|-------|------|
| bg-primary (light) | neutral-900 |
| bg-secondary (light gray) | neutral-800 |
| text-primary (dark) | neutral-50 |
| border-default (gray) | neutral-700 |

### Dark Mode Rules

- No pure black (#000) — use neutral-900
- No pure white (#FFF) — use neutral-50
- Increase contrast slightly (5:1 minimum)
- Preserve color semantics (primary still blue, etc.)
- Optional toggle in settings

---

## 🎬 Animations & Transitions

### Easing Curves

```
--ease-in: cubic-bezier(0.4, 0, 1, 1);
--ease-out: cubic-bezier(0, 0, 0.2, 1);
--ease-in-out: cubic-bezier(0.4, 0, 0.2, 1);
```

### Motion Durations

| Action | Duration | Easing |
|--------|----------|--------|
| Button hover | 150ms | ease-out |
| Dropdown open | 200ms | ease-out |
| Modal appear | 300ms | ease-out |
| Page transition | 300ms | ease-in-out |
| Loading spinner | 1s | linear |

### Rules

- **No distraction:** Avoid bouncy, playful animations
- **Purposeful:** Every animation communicates state
- **Quick:** <500ms for micro-interactions
- **Accessible:** Respect `prefers-reduced-motion` preference

---

## 📋 POS-Specific Components

### Receipt Preview

```
┌──────────────────────────┐
│       STORE NAME         │
├──────────────────────────┤
│ Item        Qty    Price │
│ Item 1      1    $10.00  │
│ Item 2      2    $20.00  │
├──────────────────────────┤
│ Subtotal:        $30.00  │
│ Tax (10%):       $3.00   │
│ TOTAL:          $33.00   │
├──────────────────────────┤
│ Cash        $40.00       │
│ Change       $7.00       │
├──────────────────────────┤
│ 2026-05-11 14:32:45      │
│ Cashier: Ahmed           │
│ Transaction #12345       │
└──────────────────────────┘
```

### POS Keypad (Optional)

```
┌───┬───┬───┐
│ 1 │ 2 │ 3 │
├───┼───┼───┤
│ 4 │ 5 │ 6 │
├───┼───┼───┤
│ 7 │ 8 │ 9 │
├───┼───┼───┤
│ 0 │ . │ ← │
├───┴───┴───┤
│   CLEAR   │
└───────────┘
```

Each key: 48px × 48px, large tap target

---

## 🎨 Design Assets & Tools

### Figma Setup

- **Team Library:** Brand colors, components, icons
- **Design System File:** Master components
- **Stitch Integration:** Auto-generate DESIGN.md updates
- **Variant Management:** All component states documented

### Icons

- **Library:** Feather Icons (open source)
- **Size:** 16px (small), 20px (medium), 24px (large)
- **Color:** Inherit from text color
- **Stroke:** 2px width

### Component Status

| Component | Status | Notes |
|-----------|--------|-------|
| Button | ✅ Ready | All variants finalized |
| Input | ✅ Ready | All states covered |
| Card | ✅ Ready | 3 variants |
| Modal | ✅ Ready | Animation defined |
| Sidebar | ✅ Ready | Responsive included |
| Table | ✅ Ready | Sorting/pagination |
| Badge | ✅ Ready | 5 variants |
| Dropdown | ✅ Ready | Keyboard nav |
| Toast | ✅ Ready | Auto-dismiss logic |
| Tabs | ✅ Ready | Swipe support |

---

## 📐 Design QA Checklist

Before shipping any component:

- [ ] All 4 color modes pass WCAG AA contrast
- [ ] Focus states are visible (outline 2px)
- [ ] Touch targets are 44px minimum
- [ ] Responsive: tested at 375px, 768px, 1440px
- [ ] Dark mode: verified
- [ ] Keyboard nav: Tab, Enter, Escape work
- [ ] Screen reader: labels are semantic
- [ ] Animation: <500ms, accessible
- [ ] Component: matches design system
- [ ] Naming: follows convention

---

## 🚀 How to Use This Document

### For Designers

1. Read this document first
2. Generate components in Stitch using color/size tokens
3. Export DESIGN.md from Stitch
4. Update this file with changes
5. Commit to Git for version control

### For Developers

1. Reference color/size tokens directly in code
2. Build components matching anatomy
3. Test accessibility before shipping
4. Use spacing scale for all padding/margins
5. Implement keyboard navigation per spec

### For AI Tools (Claude, v0, Stitch)

This file is your law. When generating UI:

1. Load this DESIGN.md first
2. Extract all tokens (colors, sizes, fonts)
3. Build components matching anatomy
4. Validate contrast and accessibility
5. Test responsive behavior

---

## 📊 Design System Metrics

| Metric | Target | Current |
|--------|--------|---------|
| Components in system | 15+ | 10 ✅ |
| WCAG AA Compliance | 100% | 95% |
| Component variants | 100+ | 80% |
| Mobile breakpoints | 3 | 3 ✅ |
| Accessibility audit score | >95 | 92 |

---

## 🔄 Version History

| Version | Date | Changes |
|---------|------|---------|
| 2.0 | May 2026 | Final MVP design system |
| 1.5 | Apr 2026 | Added POS-specific components |
| 1.0 | Mar 2026 | Initial design tokens |

---
