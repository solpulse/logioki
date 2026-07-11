---
name: Plasma Cinematic
colors:
  surface: '#111415'
  surface-dim: '#111415'
  surface-bright: '#373a3b'
  surface-container-lowest: '#0c0f10'
  surface-container-low: '#191c1d'
  surface-container: '#1d2021'
  surface-container-high: '#282a2b'
  surface-container-highest: '#333536'
  on-surface: '#e1e2e4'
  on-surface-variant: '#bec8d1'
  inverse-surface: '#e1e2e4'
  inverse-on-surface: '#2e3132'
  outline: '#88929a'
  outline-variant: '#3e484f'
  surface-tint: '#84cfff'
  primary: '#84cfff'
  on-primary: '#00344c'
  primary-container: '#3daee9'
  on-primary-container: '#003f5a'
  inverse-primary: '#00658e'
  secondary: '#c5c6ca'
  on-secondary: '#2e3134'
  secondary-container: '#494c4f'
  on-secondary-container: '#babcbf'
  tertiary: '#c5c7c9'
  on-tertiary: '#2e3133'
  tertiary-container: '#a2a4a7'
  on-tertiary-container: '#373a3c'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#c7e7ff'
  primary-fixed-dim: '#84cfff'
  on-primary-fixed: '#001e2e'
  on-primary-fixed-variant: '#004c6c'
  secondary-fixed: '#e1e2e6'
  secondary-fixed-dim: '#c5c6ca'
  on-secondary-fixed: '#191c1f'
  on-secondary-fixed-variant: '#44474a'
  tertiary-fixed: '#e1e2e5'
  tertiary-fixed-dim: '#c5c7c9'
  on-tertiary-fixed: '#191c1e'
  on-tertiary-fixed-variant: '#444749'
  background: '#111415'
  on-background: '#e1e2e4'
  surface-variant: '#333536'
typography:
  headline-lg:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 24px
    letterSpacing: -0.01em
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-md:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.05em
  label-sm:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '500'
    lineHeight: 14px
  mono-md:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  sidebar-left: 280px
  sidebar-right: 320px
  gutter: 1rem
  container-padding: 1.25rem
  stack-gap: 0.75rem
  control-inner-gap: 0.5rem
---

## Brand & Style

This design system reimagines the KDE ecosystem for high-end professional media production. The brand personality is **precise, cinematic, and immersive**, moving away from standard desktop utility toward a focused creative suite.

The aesthetic utilizes a **Modern-Corporate** base infused with **Glassmorphism**. Key characteristics include:
- **Depth-First Architecture:** Using translucent layers and background blurs to maintain context while focusing on the active task.
- **Premium Utility:** Balancing the high density required for camera controls with generous, intentional whitespace to prevent cognitive overload.
- **Atmospheric Immersion:** A deep, "lights-out" environment that makes the video content the primary source of light and focus.

## Colors

The palette is anchored in **Breeze Dark** DNA but pushed into deeper, more neutral territory to support professional color-grading tasks.

- **Primary (Plasma Blue):** Used strictly for active states, primary buttons, and focus rings. It provides the "electrical" energy of the UI.
- **Surface Hierarchy:** 
    - `background_deep`: The base layer of the application shell.
    - `tertiary`: The sidebars and secondary containers.
    - `surface_glass`: Used for floating overlays, tooltips, and temporary control panels over the video feed.
- **Neutrals:** Grays are slightly desaturated to ensure they do not introduce a color cast when the user is adjusting camera white balance or hue.

## Typography

The system uses **Inter** for its exceptional legibility at small sizes, which is critical for dense control panels. 

- **Hierarchy:** Section headers use `headline-md` to clearly demarcate control groups (e.g., "Light Adjustments").
- **Labels:** Use `label-md` for slider titles and input fields to ensure high scannability in a dense UI.
- **Monospacing:** For technical data (bitrate, resolution, frame timing), use **JetBrains Mono** to prevent layout jitter as numbers fluctuate.
- **Rendering:** All text should use `-webkit-font-smoothing: antialiased` to maintain sharpness against dark backgrounds.

## Layout & Spacing

This design system utilizes a **Structured Three-Pane Layout** compliant with KDE's Kirigami patterns for desktop.

- **Navigation Pattern:**
    - **Left Sidebar:** Global sources, preset management, and scene switching. Uses a fixed width for stability.
    - **Center Pane:** The "Canvas." Fluid width that centers the video feed, using `background_deep` to frame the content.
    - **Right Sidebar:** Detailed Inspector. Slightly wider than the left to accommodate sliders, toggle groups, and histograms.
- **Grid:** A 4px baseline grid governs all internal component spacing.
- **Responsive Behavior:** Below 1024px, the sidebars collapse into "Drawers" accessible via a top toolbar, prioritizing the video preview.

## Elevation & Depth

Visual hierarchy is established through a combination of **Tonal Layers** and **Subtle Blurs**, creating a "physical" feel without skeuomorphism.

- **Level 0 (Base):** `#0e1012`. The application frame.
- **Level 1 (Sidebars):** `#1b1e20`. Recessed or flush with the frame, separated by a 1px border (`#2d3136`).
- **Level 2 (Cards/Groups):** `#232629`. Used for grouping related controls (e.g., "Color Correction" block).
- **Level 3 (Overlays/Popups):** Semi-transparent `surface_glass` with a 20px backdrop blur and a soft, 15% opacity drop shadow.
- **Borders:** Instead of heavy shadows, use 1px inner borders for depth. Top-edge borders should be slightly lighter than bottom-edge borders to simulate a top-down light source.

## Shapes

The shape language is **refined and consistent**, using 8px as the standard radius to strike a balance between professional precision and modern approachability.

- **Standard Elements (Buttons, Inputs):** 8px (`rounded-md`).
- **Containers (Cards, Sidebars):** 12px (`rounded-lg`) to create a softer "nesting" effect.
- **Media Thumbnails:** 4px radius to maximize content visibility while removing harsh corners.
- **Active Indicators:** Vertical pills (fully rounded) on the far left of active sidebar items.

## Components

### Buttons
- **Primary:** Plasma Blue background, white text. No gradient. 1px inner highlight on the top edge.
- **Secondary:** Transparent background with a 1px border of `neutral-400`. High-translucency hover state.
- **Action Icons:** 32x32px hit area. Icons should be "Breeze-symbolic" style (thin, consistent stroke).

### Control Inputs
- **Sliders:** The track uses a dark neutral track; the filled portion uses Plasma Blue. The handle is a 14px white circle with a subtle drop shadow.
- **Input Fields:** Darker than the container background. Focus state is a 2px Plasma Blue glow.
- **Toggle Switches:** Compact "pill" style. Active state uses Plasma Blue background with a white circular nub.

### Lists & Trees
- **Source List:** High density. Hover state uses a subtle `rgba(255,255,255,0.05)` highlight. Active state uses a 4px vertical blue line on the left.

### Cards & Sections
- **Grouping:** Use thin separator lines (`#2d3136`) or subtle background shifts rather than heavy borders to keep the UI feeling "light" despite the dark theme.
- **Collapsible Sections:** Headers use `label-md` with a chevron icon to the right, allowing users to hide complex adjustments.

### Video Overlays
- **HUD elements:** High-blur glassmorphism backgrounds. Use white text with a subtle black text-shadow to ensure legibility regardless of the video content underneath.