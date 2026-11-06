# Latch identity

The mark combines the letter L with a horizontal bolt meeting a keeper. It represents a reviewed request reaching a controlled release point. It is an original vector construction, not a shield, padlock emoji or stock icon.

The current user palette is pink#FF9D9C, grey#BFBFBF and charcoal#171717. Light wordmarks use charcoal, dark wordmarks use pink, and tab/install icons use a charcoal mark on pink.

Use [mark-light.svg](mark-light.svg) on light surfaces and [mark-dark.svg](mark-dark.svg) on dark surfaces. [mark-mono.svg](mark-mono.svg) inherits currentColor when embedded as an inline vector. Do not expect currentColor in a separately loaded image to inherit the parent page color.

The outlined [wordmark-light.svg](wordmark-light.svg) and [wordmark-dark.svg](wordmark-dark.svg) render without font installation. Their lettering comes from licensed Manrope at weight 600. Font files, licenses and source hashes are retained under assets/fonts and [ASSET_SOURCES.json](../ASSET_SOURCES.json).

[preview.png](preview.png) is a brand proof showing the actual assets in both themes. It is not a mockup of a working application.

| Asset | Use |
| --- | --- |
| Symbol SVG variants | Navigation, sign in, receipt, loading and error shells |
| Outlined wordmark SVG variants | Full header, landing and printable receipt |
| [favicon.svg](../icons/favicon.svg) | Main browser tab icon |
| [favicon.ico](../icons/favicon.ico) | Browser compatibility at 16, 32 and 48 pixels |
| [icon-180.png](../icons/icon-180.png) | Apple touch icon |
| [icon-192.png](../icons/icon-192.png), [icon-512.png](../icons/icon-512.png) | Browser install metadata |
| [maskable-192.png](../icons/maskable-192.png), [maskable-512.png](../icons/maskable-512.png) | Safe maskable install icons |
| [safari-pinned-tab.svg](../icons/safari-pinned-tab.svg) | Safari pinned mask with explicit accent color |

Maintain clear space at least equal to the symbol stem. Symbol minimum 16 pixels; wordmark minimum 88 pixels. Keep the original aspect ratio. Do not add bevel, gradient, shadow, rotation or a surrounding generic shield. Brand color is not an approval status. A logo on the receipt does not certify supplier truth.

Future frontend integration must link the SVG favicon, ICO fallback,180pixel Apple icon and install manifest with separate any/maskable entries. Set title and theme-color from the real theme, use standalone display only after offline behavior is honest, and never cache private API/evidence through a service worker. No application installability is claimed by the presence of icon files.

The logo is a prepared identity for this project. Name, domain and trademark availability have not been cleared by this task.
