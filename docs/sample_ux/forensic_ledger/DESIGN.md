```markdown
# Design System Specification: The Forensic Ledger

## 1. Overview & Creative North Star
The objective of this design system is to transform dense, clinical financial data into an authoritative investigative narrative. We are moving away from the "generic SaaS dashboard" and toward a **"Forensic Ledger"** aesthetic—a high-end editorial experience that feels like a digital version of a meticulously organized investigator's case file.

**Creative North Star: The Precision Instrument.**
This system utilizes intentional asymmetry, layered depth, and sophisticated typography to command trust. We avoid the "boxed-in" feeling of traditional banking software. Instead, we use breathing room and tonal shifts to guide the investigator's eye toward anomalies and evidence.

---

## 2. Color & Surface Architecture
The palette is rooted in deep, authoritative Navies (`primary`) and Slates (`secondary`), punctuated by surgical strikes of functional color.

### The "No-Line" Rule
To achieve a premium feel, **1px solid borders are prohibited for sectioning.** We define boundaries through background color shifts.
- **Canvas:** Use `surface` (#faf8ff) as the base.
- **Sectioning:** Use `surface-container-low` to define large content areas.
- **Nesting:** Place `surface-container-lowest` (pure white) cards on top of `surface-container-low` backgrounds to create a soft, natural lift.

### Surface Hierarchy & Layering
Treat the UI as a series of physical layers. 
- **Backdrop:** `surface`
- **Primary Workspace:** `surface-container-low`
- **Active Evidence Cards:** `surface-container-lowest`
- **Sidebars/Navigation:** `surface-container-high` or `surface-dim`

### The "Glass & Gradient" Rule
Standard flat colors feel "out-of-the-box." To elevate the experience:
- **Hero Actions/CTAs:** Use a subtle linear gradient from `primary` (#002046) to `primary-container` (#1b365d) at a 135-degree angle.
- **Overlays/Modals:** Use `surface_variant` with a 70% opacity and a `20px` backdrop-blur to create a "frosted glass" effect, ensuring the data underneath remains visible but softened.

---

## 3. Typography
The system uses a tri-font strategy to balance authority, readability, and technical precision.

- **Display & Headlines (Manrope):** Chosen for its geometric, modern authority. Used for page titles and high-level summaries. It signals a premium, editorial voice.
- **Body & Data (Inter):** The workhorse. Optimized for dense tables and bank statements. Inter’s tall x-height ensures that complex numbers are legible even at `body-sm`.
- **Forensic Accents (Space Grotesk):** Used for all `label` tokens. This monospaced-leaning sans-serif should be used for raw transaction IDs, timestamps, and "forensic" metadata to give the system a technical, "coded" soul.

---

## 4. Elevation & Depth
We eschew traditional drop shadows in favor of **Tonal Layering**.

- **The Layering Principle:** Depth is achieved by stacking. A `surface-container-highest` element placed on a `surface-container` naturally "pops" without a shadow.
- **Ambient Shadows:** If a floating element (like a context menu) is required, use a shadow with a 24px blur and 4% opacity, tinted with `on-surface` (#131b2e). This mimics natural light rather than digital noise.
- **The "Ghost Border":** For data-heavy tables where containment is legally required, use a 1px border using `outline-variant` (#c4c6cf) at **15% opacity**. It should be felt, not seen.

---

## 5. Components

### Tables & Data Grids
*The core of the analysis tool.*
- **No Dividers:** Forbid horizontal and vertical lines. Use `body-sm` in `surface-container-low` for zebra-striping rows.
- **Alignment:** Financial values must be tabular-numeric (Inter) and right-aligned. Transaction IDs use `label-sm` (Space Grotesk).
- **Status Cells:** Use `tertiary_container` (Emerald) for credits and `error_container` (Ruby) for debits, but only as a subtle background tint (20% opacity) with high-contrast text.

### Buttons
- **Primary:** Gradient fill (`primary` to `primary-container`), `md` (0.375rem) roundedness. 
- **Secondary:** `surface-container-highest` background with `primary` text. No border.
- **Tertiary:** `label-md` typography with no background; use `surface-tint` for the text color.

### Input Fields
- **Style:** Use `surface-container-highest` as the background fill. 
- **Focus State:** Instead of a thick border, use a 2px "Ghost Border" of `primary` at 40% opacity and a subtle 4px outer glow.
- **Labels:** Always use `label-sm` (Space Grotesk) in `on-surface-variant` for that technical, forensic feel.

### Forensic Evidence Cards
- **Construction:** `surface-container-lowest` background, `xl` (0.75rem) roundedness, and a 15% opacity `outline-variant` Ghost Border.
- **Header:** Use a `surface-container-high` strip at the top of the card to house the "Evidence ID" in Space Grotesk.

---

## 6. Do’s and Don’ts

### Do
- **Do** use `Space Grotesk` for any data that feels "raw" or "unfiltered" (e.g., UUIDs, raw CSV strings).
- **Do** use white space as a separator. If you think you need a line, try adding 16px of padding instead.
- **Do** use `tertiary` (Emerald) and `error` (Ruby) sparingly. If the whole screen is red, nothing is an error.

### Don't
- **Don't** use pure black (#000000) for text. Use `on-surface` (#131b2e) to maintain a premium, deep-navy ink feel.
- **Don't** use standard Material Design shadows. They are too "heavy" for a professional forensic tool. 
- **Don't** use rounded corners larger than `xl` (0.75rem). We want the system to feel "precise" and "sharp," not "bubbly" or "social."
- **Don't** use high-contrast dividers. If a visual break is needed, use a 4px gap of the `surface` background color.

---

## 7. Interaction States
- **Hover:** Shift the background from `surface-container-low` to `surface-container-high`.
- **Selected:** Use a 4px vertical "intent bar" on the left side of the element using the `primary` color.
- **Disabled:** Reduce opacity of the entire component to 38%; do not change the color to a "dead" grey. Maintain the navy tonal integrity.```