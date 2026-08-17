# Fonts

Self-hosted on purpose: no third party sees the site's visitors, and the pages
keep working when a CDN disappears. Fourteen files, about 320 kB in total, all
under the SIL Open Font Licence. **Commit them** — they are part of the site.

## Getting them

```sh
./assets/fonts/get-fonts.sh
```

Needs `npm` on the PATH. Nothing is installed and no `node_modules` is created:
the script fetches three [Fontsource](https://fontsource.org/) packages into a
temporary directory, copies out the fourteen woff2 files and cleans up.

## Doing it by hand

Download these three packages from npm, unpack each one, and take the files
from `package/files/`:

| Package | Files needed |
|---|---|
| `@fontsource/spectral` | `spectral-latin{,-ext}-{400,600}-normal.woff2`, `spectral-latin{,-ext}-400-italic.woff2` |
| `@fontsource/source-sans-3` | `source-sans-3-latin{,-ext}-{400,600}-normal.woff2` |
| `@fontsource/ibm-plex-mono` | `ibm-plex-mono-latin{,-ext}-{400,600}-normal.woff2` |

Rename them as `get-fonts.sh` does — `site.css` refers to the short names, for
example `spectral-latin-400-normal.woff2` becomes `spectral-regular.woff2`, and
the `latin-ext` variant becomes `spectral-regular-ext.woff2`.

## Why two subsets

`latin` covers ordinary English text. `latin-ext` carries the accents that
conference venues actually need: Tōkyō, Kraków, Xi'An, Almería, Reykjavík. Each
face declares a `unicode-range`, so a reader whose page has no accented venue
never downloads the second file.

## If the files are missing

Nothing breaks. The stacks in `site.css` fall back to system faces, and the
site looks ordinary rather than broken.
