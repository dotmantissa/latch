# Latch visual system and interaction specification

This token plan was written before any frontend code or brand asset. Seed1793714516810191212 was drawn from the system timestamp. The independent draws are preserved in [DESIGN_ROLLS.json](../DESIGN_ROLLS.json). No generic axis was retained by default and no reroll was needed.

## Five rolls and their justification

| Axis | Roll | Decision | Reason tied to Latch |
| --- | --- | --- | --- |
| Palette | 3 of 6 | Oxblood and warm limestone | A restrained document palette gives an approval tool gravity without the usual blue SaaS theme. Warm paper keeps long source review comfortable. |
| Layout | 5 of 5 | Wide document stage and compact request rail | Evidence needs width. The request list stays compact while source, comparison and action share the main reading stage. No marketing hero/card grid. |
| Type | 2 of 5 | Manrope body with DM Serif Display for request names and grand totals | The grotesk keeps controls precise; the serif marks the consequential decision and gives the product an editorial voice. |
| Motion | 1 of 3 | Response to action only | A review tool should explain the user's action, not move for decoration. Nothing animates on first page load or while idle. |
| Structural device | 1 of 4 | A latch seam separating evidence from release | The single memorable element makes authority visible: reviewed terms meet a controlled final action. It is never a false claim that every quote is safe. |

Short token plan: limestone#F6F2EB, paper#FFFCF7, ink#24201F, oxblood#742F3A. Dark canvas#181618, paper#211E20, ink#F3EEE8, accent#E5A4AD. Manrope14/16/18 for body/navigation, DM Serif Display28/36 for request titles and totals. Layout: a compact request rail sits beside a wide document workbench with source evidence and a quiet, persistent release margin.

Banned-pattern check: no centered hero with three features, all-caps tracked labels, emoji, em dash fragments, decorative arrow suffixes, decorative numbered markers, repeated soft-shadow cards, ambient motion or generic fade/slide entrances. The one expressive device is the latch seam. Shadows are used only to establish an actual overlay layer. The layout is a working document, not a collection of cards.

## Tokens

Authoritative machine-readable values: [DESIGN_TOKENS.json](../DESIGN_TOKENS.json). Light: canvas#F6F2EB, surface#FFFCF7, subtle#EEE8DE, text#24201F, muted#665E5A, divider#D9D0C4, controlBorder#8C8179, accent#742F3A, accentHover#5B202B, accentText#FFFCF7, accentWash#F2E3E5, success#285E48, warning#80551C, danger#9C302C, info#355C7A. Dark: canvas#181618, surface#211E20, subtle#2B2528, text#F3EEE8, muted#BDB0AA, divider#4C4147, controlBorder#93838A, accent#E5A4AD, accentHover#F0BBC2, accentText#32151C, accentWash#3C252C, success#9ECBB6, warning#E4C38C, danger#FFB4AB, info#ACCAE4.

Functional text must meet4.5:1 and essential control/focus boundaries3:1. Decorative dividers are not control boundaries. Never use an accent wash as body text. Each status pairs text/icon with color. Focus is a2 px accent outline with2 px offset and sufficient contrast on each surface. Use native focus-visible behavior. Source: [WCAG contrast](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html).

Spacing scale4,8,12,16,20,24,32,40,48,64. Controls have6 px radius; source paper2 px; modal10 px; pill status 999 px only where a status is actually a compact badge. No universal rounded box. Main row height56 px with24 px icons/44 px targets,16 px cell padding, minimum line height1.5. Reference footnotes13 px minimum. Dense tables retain14 px type and tabular numerals, never10 px.

Manrope weights400/500/600/700; do not fake bold. DM Serif Display regular for title/total only. Table money uses Manrope with tabular numbers; grand total may use serif outside a column. Avoid all-uppercase text transformations. Self-host approved font files with their OFL licenses; use system fallback immediately and font-display:swap. Limit loaded files, subset only after retaining license and language coverage. No Google Fonts runtime request. Native brand icon is not a font glyph.

## Information architecture

Public `/` is a restrained editorial explanation with a working-app entry, a short product promise, honest source limits and a real service status link. No fake activity, testimonial, savings counter or fabricated sample. Primary CTA is Open Latch; secondary is How it works. The compact branded header, a document illustration from the actual logo geometry and one reading column are sufficient; the workbench is the visual centerpiece shown only with real data and consent.

`/sign-in` contains one account form, visible show/hide-password control and honest access instructions. No social-login affordance unless implemented. `/requests` shows request names, owner, updated time, truthful status, total where known and one New request action. Search/filter are local over the fetched authorized list until scale requires server query. No meaningless metric cards above the work.

`/requests/new` is a short worksheet: request name, delivery deadline as an actual date plus timezone, currency/budget, three required-item rows, and up to three approved supplier-page links. The user confirms specifications/quantity basis. Inline source validation distinguishes unsupported address, unavailable source and invalid field. Use visible Save draft then Inspect offers; autosave is not implied until a persisted save is acknowledged.

`/requests/:id` is the workbench. Header shows request name, owner, current version, saved time and status. Left rail is224 px wide on desktop, listing requests and a New request action. The main stage has a comparison ledger; selecting a source-linked field opens evidence beside it. The release margin is288–320 px with budget/deadline, selected complete candidate, review count and the latch action. Do not shrink the source image to preserve three columns; collapse the request rail first.

`/requests/:id/changes/:comparisonId` shows the actual before/after supplier terms and resulting cost/eligibility changes. Unchanged fields stay visually quiet. Header states what needs attention in ordinary text. Reviewing a new source version does not preserve a prior approval.

`/releases/:id` is a readable immutable receipt with approved request, selected supplier, cost, sources, observed times, approval identity, last recheck and limitation. Show Download packet and View source history. Use the same brand and document typography. No extra confirmation is needed merely to download an already released record.

`/settings` has Light/Dark/System theme, timezone and session information. No unimplemented preference toggles. `/status` reports public service availability without exposing worker versions, infrastructure addresses, secrets or queue contents.

Document titles: Latch; Requests | Latch; New request | Latch; Review request | Latch; Changed terms | Latch; Purchase record | Latch. Never include private buyer names/amounts in document titles or social tags.

## Workbench interactions

The comparison ledger lists required items as rows and suppliers as groups. Every amount states its price basis where needed: Each, Pack of10, Quantity to buy, Shipping, Tax included, Stated delivery. Incomplete totals display Not complete, not$0 or a misleading lowest-price highlight. Known quoted subtotal is a secondary labeled value. Candidate radio selection is enabled only for complete feasible offers with required checks; include the reason when disabled.

A field row has value, status text and View source. Selecting it reveals a trusted raster capture, exact supporting words and reviewed-value form. Source zoom supports fit-width, zoom in/out and open full image; preserve the active field and document scroll position. Keyboard selection must not trap the user in the image. The screenshot is supplier content, not app copy and must be clearly framed as such.

The requester can Check this term, Mark unclear or Correct value. Corrections require a reason and source reference; the UI shows original and corrected values, not an overwritten history. Confirmation count refers to actual reviewed critical fields. Do not provide one-click Confirm everything. A required exclusion cannot be dismissed as a cosmetic annotation.

The release margin shows exactly one primary action appropriate to state: Inspect offers, Continue review, Approve this version, Check terms and release, Review changes, or View purchase record. The seam uses a small horizontal bolt and a document edge, not a giant lock illustration. Approving moves the bolt by6 px over160ms after server acknowledgement, not before; a source change withdraws it once and reveals the change notice. Status text remains authoritative if motion is disabled.

Approval opens a summary dialog with selected supplier, confirmed total, quantity/delivery and scope statement. Button: Approve this version. A new source version gets a separate review; no repeated modal on each ordinary field click. Release begins real recapture with textual per-source progress, actual elapsed time and Cancel. No fake percentages, generated thinking text or simulated browser cursor.

If source content changes, keep the old approval visible as Earlier approval with a timestamp, never active. The diff links every material change to both captures and the recalculated result. The user reviews/approves the new version, then a new unchanged recheck permits release. If one source fails, show Retry source and Export draft with explicit stale status. Removing an unavailable supplier creates a new request/comparison version and requires new review.

## Responsive layout

At>=1440 px use224 px rail, flexible main stage min640 px,304 px release margin and24 px gaps. At1024–1439 collapse request rail to72 px icon navigation with accessible names; use main stage plus288 px release margin. Evidence selection replaces half the stage using adjustable divider only if both parts remain readable; persist divider width per device, not per source.

At768–1023 hide rail behind a labeled Requests button, put release summary after ledger, and open evidence in a full-height panel with focus restoration. At<=767 use a single document column. Supplier groups become tabs with item rows retaining units and exception reasons; do not squeeze the wide table. The release summary is in normal flow with a bottom action region above safe-area insets, never covering the last row or keyboard. Evidence opens a full-screen sheet with Back to comparison and preserved selected field. No horizontal page overflow at 320 px or200% zoom. Content order is same meaningfully in DOM across breakpoints.

At touch widths use44 px minimum targets. Editable row controls must not rely on hover. Search/new-request/settings remain available through clearly labeled navigation. Screen readers announce actual job-state changes in a polite live region, not every streaming token. Errors receive focus after submission and link to fields.

## Theme, motion and accessibility

Theme toggle has explicit Light, Dark and System options, visible names and a current-state indication. Default follows OS on first visit, then the user's saved local preference. Apply a small CSP-hashed inline bootstrap before paint to avoid flash; no credentials or remote request. Respect OS changes only in System mode. Canvas, source frame, receipt/print styles and logos use documented variants. Supplier screenshot colors remain original; do not invert evidence.

Motion only follows actions: evidence panel resize180ms, tab underline120ms, dialog entry opacity100ms, latch bolt160ms. Easing cubic-bezier(.2,.8,.2,1), no spring bounce, lift-on-hover, parallax, ambient glow or section entrances. Reduced-motion disables transforms and sets transitions to0ms; focus and text feedback remain. Honor reduced-data by not auto-downloading full-resolution captures. Data loading may show a static shaped skeleton and actual stage text; it must not invent completion.

Use semantic landmarks, native buttons/forms/tables, associated labels, persistent help text and correctly named dialog primitives. Dialog traps/restores focus and closes on Escape except when a server action is in progress; Cancel remains available when safe. Always permit navigation away while durable jobs continue. No icon-only irreversible actions. Decimal money input accepts a documented locale then normalizes server-side; display uses Intl.NumberFormat with explicit currency. UTC storage, local absolute timestamp plus tooltip of exact UTC; no ambiguous02/03 dates.

## Icons and brand placement

Use lucide-react with explicitly imported icons: FileText, Search, PanelLeft, Plus, ExternalLink, Check, CircleAlert, CircleHelp, RefreshCw, X, ChevronDown, Download, Sun, Moon, Monitor, LogOut, ArrowLeft and Settings after verifying exports in the installed version.16/20 px icons,1.75 px stroke, consistent baseline. Decorative icons aria-hidden; icon buttons have accessible names. No emoji or custom faux-icons made from Unicode. [Lucide React](https://lucide.dev/guide/react)

Use the Latch vector mark at navigation/start/login, page metadata icon, loading/error shells and receipt header. Wordmark on wide screens; standalone mark on compact nav. Do not use the logo as a status icon: a released mark does not certify every fact. Mark clear space equals its stem width; minimum 16 px for symbol,88 px for wordmark; do not stretch or add shadow. Assets and theme rules are indexed in [assets/brand/README.md](../assets/brand/README.md).

## Copy system

Canonical user text lives in [COPY.json](../COPY.json), then is imported into the future UI. No emoji, em dash, unnecessary hyphens, AI promotion, “magic,” inflated certainty or repeated arrows. Human warmth belongs in low-risk empty/success states. Warnings about money/terms remain precise. No jokes about lost money, security or approval mistakes.

Examples: “Nothing waiting on you. Enjoy the quiet.” for an empty queue; “The terms changed while you were away.” for a revision; “Docking stations are missing from this offer.” for an exclusion; “We could not check this source. Your approval is still on hold.” for failed recapture. Use “Purchase record created” only after durable commit. Never “Order placed.” The README follows the same prose constraints.

UI copy lint checks our catalog, titles, metadata and accessible names. User/supplier text is untrusted source content; preserve punctuation verbatim for evidence and do not rewrite it to satisfy our copy lint. That exception is an evidence-integrity requirement, not permission for marketing copy violations.

## Visual acceptance

Review real running flows at 320,390,768,1024,1440 and1920 px, both themes,200% zoom and reduced motion. Check before/after actual actions: form error, source capture, field review, incomplete offer, approval, recapture change, failed source, successful release, export, expired session, worker interruption. Run axe and keyboard checks plus human screenshot review. Compare against this specification, not only against a generated snapshot. Save truthful capture artifacts privately with consent; no mocked success screenshots or invented rows.
