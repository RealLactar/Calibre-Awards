# Calibre Awards

**0.2.0 beta** — a preview release. Coverage and matching will keep changing
during the 0.x line. Please report mismatches.

Calibre Awards looks up literary awards for one book from Calibre's
single-book **Edit Metadata** window. It is not a finished 1.0 product.

## What it does

Calibre Awards adds a **Check Awards** button to Calibre's **single-book
Edit Metadata** dialog.

Check Awards searches the award sources you have enabled, using the book's
**Title** and **Author**. **Series** is used where a source supports series
awards. Matching results are shown for review. You can optionally write
selected award values into a configured Calibre custom column.

Network lookup runs outside the GUI thread, so Calibre stays responsive while
sources are checked.

The toolbar or menu **Calibre Awards** action does **not** look up the
current book. It opens the **Supported Award Sources** information dialog.
Book lookup happens only from **Check Awards** in Edit Metadata.

## Supported awards

The plugin currently has **17 executable award sources**. Category coverage
is limited to the literary work awards each source currently advertises in
the plugin. Anthology, editor, artist, publisher, and similar non-work
honors are omitted where they fall outside those categories.

Open **Calibre Awards** from the Calibre toolbar or menu for the
**Supported Award Sources** dialog. That list is the current category and
scope catalog.

| Award source | Coverage | Results returned |
| --- | --- | --- |
| Pulitzer Prizes | Novel 1918–1947; Fiction 1948–present | Winner; Fiction Finalist from 1980 |
| Nebula Awards | Core fiction archive from 1965; Andre Norton Award from 2005; poetry where the archive includes it | Winner; Nominated |
| Hugo Awards | Regular archive from 1953 (no regular 1954 page; that year is Retro-only) | Winner; Finalist; explicit Best Novel rank only for curated official-statistics years; series awards where supported |
| Locus Awards | Ranked literary categories from the Science Fiction Awards Database (SFADB) annual archive | Explicit ordinal ranks; the Preferences rank cutoff decides which ranks qualify |
| World Fantasy Awards | Novel and Short Fiction from 1975; Novella from 1982; Collection from 1988 | Winner; Nominee |
| Bram Stoker Awards | Publication-year cycles from 1987 through the latest completed cycle (verified through 2025) | Winner; Final Ballot works as Finalist |
| Nobel Award | Nobel Prize in Literature laureate archive | Normally an author-level Winner; a work is returned only when official material specifically cites it |
| The Booker Prize | 1969–present | Winner; Shortlisted |
| Deutscher Buchpreis | 2005–present | Winner; Shortlisted |
| Prix Goncourt | Winners from 1903; Finalists from 2018 | Winner; Finalist (official 3ème sélection) |
| Miles Franklin Literary Award | Production coverage from 2007 | Winner; Finalist when the archive labels the work Finalist, Shortlist, or Shortlisted |
| Women's Prize for Fiction | Winners from 1996 (including Orange Prize years under the current name); Shortlisted from 2017 | Winner; Shortlisted |
| National Book Critics Circle Awards | Winners from 1975; Finalists from 1976 | Winner; Finalist |
| PEN/Faulkner Award for Fiction | Winner and Finalist from 1981 | Winner; Finalist |
| PEN/Hemingway Award for Debut Novel | Winners from 1976; Finalists from 2026 | Winner; Finalist |
| International Prize for Arabic Fiction | Official English prize-year pages from 2020 | Winner; Shortlisted |
| John Newbery Medal | 1930–2023 | Winner; Honor |

**National Book Awards** is not an executable source. Preferences shows it
as unavailable (**Transport blocked**) because the current website presents
an automated-access challenge that the plugin does not bypass. It cannot be
enabled. This is the current site limitation, not a permanent product
decision.

## How to use it

1. Open **Edit Metadata** for one book.
2. Click **Check Awards**.
3. The plugin checks the sources you have enabled.
4. Matching results are shown for review.
5. If write-back is enabled, you may select results to write.

Checking awards does not change book metadata by itself. If one source
fails, results from the other enabled sources are still shown.

## Understanding results

The results dialog shows formatted award lines with checkboxes. It does not
label rows with internal decision names.

- Matches the plugin treats as qualifying for that source are **checked by
  default**.
- An explicit ordinal rank (for example 3rd place) qualifies when it is at
  or above the Preferences setting **Highest explicit ordinal rank to
  include**. The default cutoff is 5. Raising it to 20 allows an explicit
  19th-place result to qualify. Rank is used only when the source published
  that number. Visual or list order is never treated as a rank.
- **Winner** generally qualifies.
- Some formal distinctions such as **Finalist**, **Shortlisted**, or
  **Honor** qualify when that award's policy defines them as qualifying.
  Not every finalist or nominee automatically qualifies.
- Nominee- or finalist-style matches from awards without that kind of
  policy are still shown, but they are **not checked automatically**.
- When write-back is enabled, you can manually check any visible unchecked
  row if you want that value written.

### Possible author matches

Author matching is conservative. The plugin does not treat similar names as
the same person.

One implemented case is an omitted middle initial. For example:

- Calibre: Allen M. Steele
- Source: Allen Steele

That can appear as a **Possible Author Match**. Such a result is visually
marked, starts **unchecked** even if its award otherwise qualifies, and is
included for write-back only if you check it. Confirming it does **not**
change the Calibre Authors field.

## Writing awards to Calibre

Write-back is **optional** and **off by default**.

When enabled, selected awards are written to a **multiple-value text**
custom column. A names column is not supported.

**Append** (recommended) keeps existing entries and adds new selected
values. Duplicate formatted strings are skipped using a conservative
case-insensitive comparison.

**Replace** replaces the destination field's current values with the
selected awards.

The awards dialog writes to the Edit Metadata widget, not directly to the
library database. Calibre's Edit Metadata **OK** commits those changes.
Edit Metadata **Cancel** discards them along with other unsaved metadata
edits.

Visible unchecked matches can be checked and written if you choose. Write-back
is not limited to the rows the plugin checked automatically.

Calibre separates multiple-value text entries with commas. A generated
individual award value that contains a literal comma cannot be written
safely and is refused. The commas Calibre shows *between* values are not
part of any one stored award string.

## Preferences

Open **Preferences → Plugins → Calibre Awards → Customize plugin**.

**Award sources.** Enable or disable individual executable sources. **Select
All** and **Select None** change only the checkboxes in this dialog until
you apply preferences. A newly added executable source starts enabled unless
you disable it. **National Book Awards** has no enable checkbox because it
is currently unavailable.

**Refresh.** Each enabled source has a **Refresh** button. Refresh clears
that source's local cache. It does not contact the website. The next
**Check Awards** lookup rebuilds the cache.

**Qualification and award output.** Rank cutoff is 1–100 (default 5). It
applies only when a source provides an explicit numerical rank. Unranked
winners, finalists, and nominees keep their normal award-specific treatment.

**Award output template.** Supported placeholders:

- `<placement>`
- `<year>`
- `<award>`
- `<category>`

Default:

`<placement> - <year> <award> - <category>`

You may omit placeholders or add literal text.

**Placement** is the explicit ordinal rank when one exists (`1st`, `2nd`,
`3rd`, …). Otherwise it is the result status, such as Winner, Finalist,
Shortlisted, or Honor.

Examples with the default template:

- `Winner - 2020 Pulitzer Prize - Fiction`
- `Honor - 2003 Newbery Medal - Children's Literature`
- `3rd - 2015 Locus Award - Fantasy Novel`

Each award is a separate value in the multi-value Calibre field.

**Restore rank & output defaults** restores only the rank cutoff and output
template. It does not reset source selection or write-back settings.

**Write-back.** Optional. Choose the destination custom column and Append or
Replace.

## Cache and network behavior

The first lookup may download award archives from several websites and can
take longer than later lookups.

Calibre Awards stores a persistent local cache under Calibre's configuration
area so later searches can reuse previously downloaded award information.
Each source has its own cache. Cache persists across Calibre restarts.

**Refresh** in Preferences clears that source's cache. Refresh itself does
not contact the website; the next Check Awards request rebuilds it.

If one award website fails, other award sources continue running.

Uncached lookups require an internet connection.

## Known limitations

- **Pulitzer.** Pulitzer.org may present an anti-automation or browser
  challenge. The plugin does not bypass it. Cached data may still be used
  when available. Other sources continue.
- **National Book Awards.** Currently **Transport blocked**. Informational
  only; it cannot be enabled.
- **International Prize for Arabic Fiction.** Official English coverage
  begins in 2020. The 2008–2019 archive has not been migrated to the current
  site. Official English spellings may differ from later translations.
- **PEN/Hemingway.** Winners from 1976. Finalists only from 2026 in this
  release.
- **Prix Goncourt.** Finalist coverage from the 2018 official third
  selection (3ème sélection). Earlier selection rounds are not returned.
- **Miles Franklin.** Production coverage from 2007. The 2025 nonwinning
  mixed shortlist/longlist page is not treated as a verified finalist list.
- **Women's Prize for Fiction.** Winner history from 1996. Shortlist
  coverage from 2017.
- **Newbery.** Current plugin coverage is 1930–2023.
- **Longlists.** Several sources intentionally ignore longlist-only works.
- **Hugo.** Explicit ordinal ranks are available only for specifically
  transcribed official-statistics years, and only for Best Novel. List order
  is never rank.
- **Nebula / World Fantasy.** Nominated and Nominee results may be shown but
  are not automatically treated as qualifying by current policy.
- **Locus.** Matching is conservative. An omitted middle initial may appear
  as a Possible Author Match and require confirmation.
- **Nobel.** Normally an author-level award rather than a book award.
- **Translated or alternate titles.** Conservative matching can miss books
  whose Calibre title or author differs from the source's official form.
- **Website changes.** Award websites are external and may temporarily break
  a source.
- **Bram Stoker.** Final Ballot only. Preliminary ballot, recommendation
  lists, screenplay, other-media, and person or service honors are excluded.
- **Unsupported categories.** Anthology, editor, artist, publisher, and
  similar non-work honors are outside this preview where they are not in a
  source's advertised work categories.

## Installation

Install from the **public release ZIP**, not from a Git checkout.

1. In Calibre, open **Preferences → Plugins**.
2. Choose **Load plugin from file**.
3. Select `Calibre-Awards-0.2.0.zip`.
4. Restart Calibre if it asks you to.

Advanced users can install the same ZIP from a command prompt:

```text
calibre-customize -a Calibre-Awards-0.2.0.zip
```

## Upgrading

Load a newer Calibre Awards ZIP the same way (**Preferences → Plugins →
Load plugin from file**). Calibre replaces the installed plugin with the
ZIP you load.

This plugin stores preferences and cache in Calibre's configuration
directory, not inside the ZIP. Loading a newer ZIP updates the plugin code;
existing preferences are typically kept. You do not need to delete cache or
preferences for a normal upgrade. A future release will say so if a setting
cannot be migrated.

## Uninstall

**Preferences → Plugins**, select **Calibre Awards**, then **Remove plugin**.

## Requirements / compatibility

- Calibre 6.0.0 or later
- Windows, macOS, or Linux (as declared by the plugin)
- Internet connection for uncached lookups
- No extra Python packages to install

Calibre Awards 0.2.0 beta requires Calibre 6.0.0 or later. This release was
tested with Calibre 9.14.0. That is the version used for the 0.2.0 beta
smoke test, not a claim that only 9.14.0 is supported.

Check Awards uses Calibre's single-book Edit Metadata interface. A future
Calibre change to that window may require a plugin update.

## Privacy / network use

This plugin does not use an AI service, does not require an API key, and
does not require an external user account. It does not implement telemetry
or analytics.

Uncached lookups contact award-data websites over HTTPS. Some sources use
title, author, or series information when requesting pages. Award sites you
query will see ordinary HTTPS requests during lookup.

## Unofficial project / attribution

Calibre Awards is an unofficial third-party Calibre plugin. It is not
affiliated with or endorsed by Calibre's developers or the award
organizations and data sources it queries.

Award names and source content belong to their respective organizations.
The plugin retrieves publicly available award information from the sources
identified in this project. Most sources are official award sites; Locus
results currently come from the Science Fiction Awards Database (SFADB).

## Feedback / bugs

This is a beta / preview. Please report problems at:

https://github.com/RealLactar/Calibre-Awards/issues

Useful reports include:

- Calibre version
- Calibre Awards version
- book title and author
- the award or source involved
- what the plugin returned or any error text
- what you expected

Do not include passwords, API keys, or other private account information.

## License

Calibre Awards is licensed under [GPL-3.0-or-later](LICENSE).
