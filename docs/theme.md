# Theme System

The app supports light/dark mode via Streamlit 1.55's built-in theme toggle. Custom colors are applied in `src/scripts/theme.py` using `apply_theme()`, which injects CSS and a small JS snippet.

## How it works

- **`light-dark()` CSS function**: All custom colors use `light-dark(light-val, dark-val)`. Streamlit sets `color-scheme` on `[data-testid="stApp"]`, and the browser resolves `light-dark()` automatically.
- **`_COLOR_SCHEME_SYNC` JS**: A MutationObserver watches `stApp` for class changes and copies the `color-scheme` value to `<html>`. This is needed because portaled elements (selectbox dropdowns) are rendered outside `stApp` and wouldn't otherwise inherit the scheme.
- **`config.toml`**: Defines light/dark palette (backgrounds, text, sidebar) under `[theme.light]` / `[theme.dark]`. `primaryColor = "#003056"` (NOCCCD navy).
- **Dataframe theming**: Streamlit 1.55 exposes `dataframeBorderColor` and `dataframeHeaderBackgroundColor` in `config.toml`. These feed directly into glide-data-grid's React props — CSS variable overrides or JS monkey-patches will NOT work because the canvas reads from React props, not CSS vars.

## Gotchas (Streamlit 1.55)

- **Portaled dropdowns**: Baseweb selectbox dropdowns are portaled to the document root, outside `stApp`. They don't inherit `color-scheme`, so `light-dark()` won't work without the `_COLOR_SCHEME_SYNC` observer. Dropdown text color needs a separate `stSelectboxVirtualDropdown` rule since it can't be scoped to a sidebar/main ancestor.
- **Selector names**: `stVerticalBlockBorderWrapper` doesn't exist in 1.55. Use `[data-testid="stColumn"] [data-testid="stVerticalBlock"]` for card styling.
- **Progress bar fill**: The fill bar is `[data-testid="stProgress"] [role="progressbar"] > div > div > div` (triple-nested div). Targeting `[role="progressbar"]` itself only styles the container track.
- **Sidebar text color**: Sidebar forces white text via `config.toml`. Selectbox widgets inside the sidebar inherit white, but the dropdown menu is portaled out, so it needs its own color rule.
- **Dataframe canvas**: `st.dataframe()` uses glide-data-grid which renders to a `<canvas>` element. CSS cannot style canvas content. The only way to customize gridline color, header background, and text colors is through `config.toml` theme keys (`dataframeBorderColor`, `dataframeHeaderBackgroundColor`, `textColor`). Header text color and index column text color are derived from `textColor` at 60% and 80% opacity respectively — there is no independent control.
- **Card border scoping**: The `[data-testid="stColumn"] [data-testid="stVerticalBlock"]` selector matches both Home page cards and tab metric columns. Home cards already get borders from `st.container(border=True)`, so adding `border` to this generic selector creates a double border. Use `:has([data-testid="stMetric"])` to scope border/padding/radius to metric columns only. Setting `border-color` alone is insufficient — `border-style` defaults to `none`, so use the full `border: 1px solid ...` shorthand.
- **Expanding crosstab tables**: The MIS SP tabs use `_build_expandable_crosstab()` which renders HTML tables via `st.markdown(unsafe_allow_html=True)`. Header styling uses `var(--secondary-background-color, #555)` but this CSS variable doesn't resolve inside `st.markdown()` HTML, so it falls back to `#555` (dark grey) in both modes. The `theme.py` overrides fix this — `.grid-row.header` and `.sub-table thead th` are globally targeted with `light-dark()` to set proper light/dark backgrounds and text colors. Reuse `_build_expandable_crosstab()` for future tabs that need expandable pivot tables.
- **Banded HTML tables**: The Seat Count Report uses `.sc-banded` CSS class for grouped banded tables rendered via `st.markdown(unsafe_allow_html=True)`. Styled in `theme.py` with `light-dark()` for department headers (`.dept-header`), course headers (`.course-header`), subtotal rows (`.subtotal-row`, `.dept-total`), and fill rate coloring (`.sc-fillrate-high/med/low`). Each division is wrapped in `st.expander()`. Reuse this pattern for future banded/grouped reports.

## Color palette reference

| Element | Light | Dark |
|---------|-------|------|
| Headings | `#003056` (navy) | `#FFFFFF` |
| Card bg | `#E8E8E8` | `#000000` |
| Card border (metrics) | `#AAAAAA` | `rgba(255,255,255,0.2)` |
| Progress fill | `#003056` (navy) | `#3D9DF3` (bright blue) |
| Body text | `#000000` | `#FFFFFF` |
| Dataframe border | `#888888` | (default) |
| Dataframe header bg | `#E8E8E8` | (default) |
| Crosstab header bg | `#E8E8E8` | `#555` |
| Crosstab header text | `#000000` | `#FFFFFF` |
| Dropdown separator | `#444444` | `#AAAAAA` |
| Banded dept header | `#D6E4F0` | `#1A3A5C` |
| Banded course header | `#F0F4F8` | `#2D3748` |
| Fill rate high (>=80%) | `#D4EDDA` | `#1B4D3E` |
| Fill rate med (50-80%) | `#FFF3CD` | `#4D3F00` |
| Fill rate low (<50%) | `#F8D7DA` | `#4D1F24` |

## NOCCCD brand colors

Official district color palette used in BOT charts and reports:

| Color | HEX | RGB | Usage |
|-------|-----|-----|-------|
| Green | `#50b913` | 80, 185, 19 | Cypress College |
| Blue | `#0081b7` | 0, 129, 183 | General accent |
| Light Blue | `#5faed3` | 95, 174, 211 | Male, Multiethnic |
| Dark Teal | `#004062` | 0, 64, 98 | NOCE |
| Teal | `#00b3a0` | 0, 179, 16 | Filipino |
| Teal/Aqua | `#50b9c3` | 80, 185, 195 | NOCCCD Unduplicated, Hispanic, Non-Binary, Not First-Gen |
| Teal Blue | `#007a94` | 0, 122, 148 | Asian, Female, First-Gen, Amer Indian/AK Native |
| Grey | `#575a5d` | 87, 90, 93 | Pacific Islander |
| Sand Yellow | `#fbde81` | 251, 222, 129 | Available accent |
| Golden Yellow | `#ffdd00` | 255, 209, 0 | Available accent |
| Orange | `#f99d40` | 249, 157, 64 | Fullerton College, Black/African American, Unknown (gender) |

## Adding themed elements

1. Use `light-dark(light-val, dark-val)` for all color properties
2. Always add `!important` — Streamlit's inline styles have high specificity
3. If colors look wrong, inspect the DOM with Playwright (`browser_snapshot`) to find the actual element and its test-id
4. Portaled elements (dropdowns, dialogs) need rules without ancestor scoping — they live at the document root
5. Add new CSS rules to `THEME_CSS` in `theme.py`; no changes needed to `apply_theme()`
