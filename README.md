# Calibre Awards

**0.3.0 beta** — a preview release. Coverage and matching will keep changing
during the 0.x line. Please report mismatches.

Calibre Awards looks up literary awards for one book from Calibre's
single-book **Edit Metadata** window. It is not a finished 1.0 product.

## What it does

Calibre Awards adds a **Check Awards** button to Calibre's **single-book
Edit Metadata** dialog.

Check Awards searches the award sources you have enabled, using the book's
**Title** and **Author**. **Series** is used where a source supports series
awards. Matching results are shown for review. You can optionally write
selected award values into a configured Calibre custom column. If no
executable award source is enabled, **Check Awards** is hidden in Edit
Metadata.

Network lookup runs outside the GUI thread, so Calibre stays responsive while
sources are checked.

The toolbar or menu **Calibre Awards** action does **not** look up the
current book. It opens the **Supported Award Sources** information dialog.
Book lookup happens only from **Check Awards** in Edit Metadata.

## Supported awards

The plugin currently has **30 executable award sources**. Category coverage
is limited to the literary work awards each source currently advertises in
the plugin. Anthology, editor, artist, publisher, and similar non-work
honors are omitted where they fall outside those categories.

Open **Calibre Awards** from the Calibre toolbar or menu for the
**Supported Award Sources** dialog. That list is the current category and
scope catalog.

| Award source | Coverage | Results returned |
| --- | --- | --- |
| Pulitzer Prizes | Novel 1918–1947 (official Novel category from 1917; 1917 had no award); Fiction 1948–2026 | Winner; Fiction Finalist from 1980 |
| Nebula Awards | Core fiction archive from 1965; Andre Norton Award from 2005; poetry where the archive includes it | Winner; Nominated |
| Hugo Awards | Regular archive from 1953 (no regular 1954 page; that year is Retro-only) | Winner; Finalist; explicit Best Novel rank only for curated official-statistics years; series awards where supported |
| Locus Awards | Ranked literary categories from the Science Fiction Awards Database (SFADB) annual archive | Explicit ordinal ranks; the Preferences rank cutoff decides which ranks qualify |
| World Fantasy Awards | Novel and Short Fiction from 1975; Novella from 1982; Collection from 1988 | Winner; Nominee |
| Balrog Award | ISFDB public copy, award years 1979–1985; 1984–1985 literary records winner-only | Winner; Nomination (review) |
| Bram Stoker Awards | Publication-year cycles from 1987 through the latest completed cycle (verified through 2025) | Winner; Final Ballot works as Finalist |
| Edgar Awards | Bibliographic mystery and crime categories from 1946 | Winner; Nominee |
| Romantic Novel of the Year Awards | Winners from 1960 where the current archive includes them; official shortlists from 2018 | Winner; Shortlisted |
| Nobel Award | Nobel Prize in Literature laureate archive | Author-level Winner; official motivation shown in Check Awards; eight reviewed motivation citations are annotations, not book-level Wins |
| The Booker Prize | 1969–present | Winner; Shortlisted |
| International Booker Prize | Official Winner and Shortlisted translated works, 2016–2026 | Winner; Shortlisted |
| Wolfson History Prize | Official book-award archive from 1972; official shortlists from 2017 | Winner; Shortlisted |
| Deutscher Buchpreis | 2005–present | Winner; Shortlisted |
| Prix Goncourt | Winners from 1903; Finalists from 2018 | Winner; Finalist (official 3ème sélection) |
| Miles Franklin Literary Award | Production coverage from 2007 | Winner; Finalist when the archive labels the work Finalist, Shortlist, or Shortlisted |
| Women's Prize for Fiction | Winners from 1996 (including Orange Prize years under the current name); Shortlisted from 2017 | Winner; Shortlisted |
| National Book Critics Circle Awards | Winners from 1975; Finalists from 1976 | Winner; Finalist |
| PEN/Faulkner Award for Fiction | Winner and Finalist from 1981 | Winner; Finalist |
| PEN/Hemingway Award for Debut Novel | Winners from 1976; Finalists from 2026 | Winner; Finalist |
| International Prize for Arabic Fiction | Official English prize-year pages from 2020 | Winner; Shortlisted |
| Bad Sex in Fiction Award | Bundled reviewed book winners, 1993–2019; no network required | Winner |
| Diagram Prize for Oddest Title of the Year | 42 bundled annual winners with credited identities, 1979–2025 | Winner |
| John Newbery Medal | 1930–2026 | Winner; Honor |
| Dublin Literary Award | Official annual archive from 1996, including former International IMPAC Dublin years | Winner; Shortlisted; Longlisted; Nominated; no inferred rank; non-winners shown unchecked for REVIEW |
| Akutagawa Prize | Official winner history from 1935; nominations for rounds 162 and 175; reviewed English mappings | Winner; Nominated (unchecked REVIEW); original award year and half-year retained |
| Naoki Prize | Official winner history from 1935; round 175 nominations; five reviewed English mappings | Winner; Nominated (unchecked REVIEW) |
| Mao Dun Literature Prize | Reviewed editions 1–11 (1982–2023); edition 11 nominees; four English mappings | Winner; Honorary award; Nominated; scope confirmation for awarded volumes/revisions |
| Prix Médicis | Official French, foreign and essay winner history; 2026 first selection; four English mappings | Winner; Selected (REVIEW); specific-volume confirmation |

| CWA Gold Dagger | Main award winners 1955–2026, including the Crossed Red Herrings predecessor; partial candidate coverage 2004–2026 | Winner (checked); Shortlisted, Longlisted, Highly Commended (unchecked REVIEW); other Daggers excluded |

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
you disable it. If none are enabled, **Check Awards** is hidden in Edit
Metadata. **National Book Awards** has no enable checkbox because it
is currently unavailable.

**Refresh.** Each enabled source has a **Refresh** button. **Refresh all**
queues requests for the checked executable sources. The buttons show
**Refresh queued** when the request succeeds. Failed requests remain
available to retry. With unchanged selections, bulk retry processes only failed
sources. Changing selections includes newly checked sources and updates the
button label. Sources already queued in this Preferences session are skipped;
individual Refresh can request them again. Individual retry success also clears
that source's bulk failure state. Selecting or deselecting sources leaves saved
fallback and existing pending requests intact.
Refresh performs no network requests and does not change stored book awards.
The next background **Check Awards** lookup attempts the requested downloads
while retaining validated saved fallback. Bundled sources instead reload
their shipped archive; new coverage requires a plugin update.

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

You may omit placeholders or add literal text. **Category** is optional.
When a result has no category, that placeholder is left out. The formatted
value does not keep a fake category marker or a dangling separator.

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

**Refresh** retains saved data until a downloaded replacement has parsed and
validated successfully. Failed or invalid updates preserve the saved bytes
and timestamp, and remain pending for a later lookup. Requests persist
across restarts when disk caching is configured; without it, requests last
for the current process. Explicit requests bypass the normal one-source
stale-refresh budget. Locus author and annual entries complete independently;
failed or unvisited entries remain pending. Pulitzer's reviewed bundled
snapshot remains available. Diagram and Bad Sex in Fiction use no network.
Refresh is immediate and is not undone by Canceling Preferences.

If one award website fails, other award sources continue running.

Uncached network sources require an internet connection. Bundled sources
remain available offline.

## Known limitations

- **Pulitzer.** Pulitzer.org may block unattended retrieval with a browser
  challenge. The plugin does not bypass it. A reviewed snapshot of official
  Fiction and Novel award facts through 2026 is bundled as the reliable
  baseline. Live official refresh remains opportunistic when ordinary HTTP
  works. A failed refresh does not discard usable Pulitzer data. Finalist
  records follow Pulitzer's official Finalist terminology from 1980. This is
  not a Wikipedia, Wikidata, or other third-party runtime source.
- **National Book Awards.** Currently **Transport blocked**. Informational
  only; it cannot be enabled.
- **Edgar Awards.** Bibliographic mystery and crime categories from 1946.
  Award year is the ceremony year. Nominees are official announced slates
  and do not imply rank. Early years are often winner-only. Media, screen,
  stage, person, service, design, and Special Edgar categories are excluded.
- **Romantic Novel of the Year.** Winners from 1960 where the current
  archive includes them. That archive omits 1966 and 2011–2017. Official
  shortlists begin in 2018. Industry awards, person awards, and the Joan
  Hessayon Award are excluded.
- **International Booker Prize.** The modern work-level prize is covered from
  2016 through 2026. The 2005–2015 biennial Man Booker International Prize
  honoured an author's body of work rather than a single book and is not
  returned. Longlisted-only works are not returned. 2027 is not emitted yet:
  the official prize name changes to the Bukhman International Booker Prize
  and competitive results do not yet exist. Translator credit is stored in
  notes rather than as a separate award.
- **Wolfson History Prize.** Official book awards from 1972. The official
  archive omits 1988. Historical years may have more than one co-equal
  Winner. Official shortlists begin in 2017. Lifetime and
  distinguished-contribution honors are excluded. List order is not rank.
  The current cycle may list a shortlist before a Winner is announced.
- **International Prize for Arabic Fiction.** Official English coverage
  begins in 2020. The 2008–2019 archive has not been migrated to the current
  site. Official English spellings may differ from later translations.
- **PEN/Hemingway.** Winners from 1976. Finalists from 2026, when
  administration transferred to the PEN/Faulkner Foundation. Earlier
  Finalists, Runners-up, and Honorable Mentions are not returned.
- **Prix Goncourt.** Finalist coverage from the 2018 official third
  selection (3ème sélection). Earlier selection rounds are not returned.
- **Miles Franklin.** Production coverage from 2007. The 2025 nonwinning
  mixed shortlist/longlist page is not treated as a verified finalist list.
- **Women's Prize for Fiction.** Winner history from 1996. Shortlist
  coverage from 2017.
- **Newbery.** Current plugin coverage is 1930–2026.
  Historical ALA listing pages cover 1930–2023; official annual HTML announcements
  add all 2024–2026 Medal winners and Honor Books, cross-checked against ALA's
  March 2026 PDF. Cache schema 2 requires all six pages; old 1930–2023 caches
  remain usable historical fallback with an incomplete-coverage diagnostic.
  See awards/data/newbery_provenance.md. Years 1922–1929 remain excluded.
- **Longlists.** Several sources intentionally ignore longlist-only works.
- **Hugo.** Explicit ordinal ranks are available only for specifically
  transcribed official-statistics years, and only for Best Novel. List order
  is never rank.
- **Nebula / World Fantasy.** Nominated and Nominee results may be shown but
  are not automatically treated as qualifying by current policy.
- **Locus.** Matching is conservative. An omitted middle initial may appear
  as a Possible Author Match and require confirmation.
- **Nobel.** Nobel Prize in Literature results are author-level. Check Awards
  may show the official English motivation and unusual prize statuses such
  as declined or restricted. Works explicitly cited in a motivation are
  annotations; they are not books that themselves won the Nobel Prize.
  Editorial Nobel work lists are not harvested. Ordinary books by a laureate
  are not claimed to have won the prize.
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
3. Select `Calibre-Awards-0.3.0.zip`.
4. Restart Calibre if it asks you to.

Advanced users can install the same ZIP from a command prompt:

```text
calibre-customize -a Calibre-Awards-0.3.0.zip
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

Edgar Awards, Romantic Novel of the Year Awards, and the International
Booker Prize were not in 0.2.0. After an upgrade they start enabled, so
the first Check Awards search may take longer while those sources load.

## Uninstall

**Preferences → Plugins**, select **Calibre Awards**, then **Remove plugin**.

## Requirements / compatibility

- Calibre 6.0.0 or later
- Windows, macOS, or Linux (as declared by the plugin)
- Internet connection for uncached lookups
- No extra Python packages to install

Calibre Awards 0.3.0 beta requires Calibre 6.0.0 or later. The 0.3.0 beta
smoke test was performed using Calibre 9.15.0. That is not a claim that
only 9.15.0 is supported.

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

Balrog award data is retrieved from the public ISFDB copy at https://isfdb.stoecker.eu/ and is attributed to the ISFDB team under Creative Commons Attribution 4.0 (https://creativecommons.org/licenses/by/4.0/). The plugin parses and normalizes those records for matching.

Bad Sex in Fiction Award: bundled reviewed book winners, 1993–2019 (28 records, including joint 2019 winners). No shortlists or author lifetime honors. No network required; Refresh reloads the bundled archive. Historical secondary attribution and a corrected 1994/1995 date discrepancy are documented in awards/data/bad_sex_provenance.md.

Diagram Prize uses a reviewed historical archive with secondary-source attribution. Three early anonymous entries, no-award years, shortlists and anniversary honors are excluded. Refresh reloads the bundled archive; adding later winners requires a plugin update. See awards/data/diagram_provenance.md for provenance and title aliases.

Dublin includes the official archive's Nominated, Longlisted and Shortlisted books as REVIEW results, unchecked by default. The strongest status is shown once per work/year. A longlist is a larger candidate list narrowed down before the shortlist; Dublin's 2026 judging panel reduced 69 library nominations to a longlist of 20, then a shortlist of 6. Historical archive labels are retained. The official 2013 longlist is empty, so coverage for that year remains its winner and shortlist. Complete lists are retrieved through the same public GET endpoint used by the website, beyond annual-page previews. Dublin cache schema 2 refetches earlier winner/shortlist-only caches.

Akutagawa Prize uses the official Japanese winner archive. Initial reviewed coverage is 189 winning works across 175 rounds (1935–2026); 33 rounds explicitly have no award. Complete nomination announcements are included only for round 162 (2019 second half) and round 175 (2026 first half). Eleven winning works and one nominee have reviewed English title/name mappings; other entries require the original Japanese identity. No machine-generated title translations or automatic name romanization are used. Winners remain distinct from other books by the same author. Collections and expanded editions are not automatically credited with an included or earlier work's award. The official award year is retained even when a second-half result was announced the following January. Source details show the round, half-year, original identity and mapping evidence. Refresh updates the official archive and documented nomination pages; additional nomination rounds and English mappings require a plugin update. See awards/data/akutagawa_provenance.md.

Naoki Prize covers the official Japanese winner archive from 1935, with nominations currently limited to round 175 (2026 first half). Five reviewed English winning-work mappings are included: The Devotion of Suspect X, Honeybees and Distant Thunder, Woman on the Other Shore, The Little House and First Love. Nominees appear unchecked for REVIEW. Historical multi-story citations are preserved intact; translated collections and individual component stories are not automatically inferred. The separate High School Students’ Naoki Prize is excluded. See awards/data/naoki_provenance.md.

Mao Dun Literature Prize uses the official Chinese Writers Association archive: 51 regular winning works, two honorary awards and five non-winning nominees from edition 11 after deduplication. Award years (1982–2023) are distinct from eligibility periods and article publication dates. English mappings currently cover The Last Quarter of the Moon / Chi Zijian, Frog / Mo Yan, Someone to Talk To / Liu Zhenyun and Shadow of the Hunter / Su Tong. Honorary awards and nominees appear unchecked for REVIEW. Volume-specific and revised-edition records retain their complete scope and require confirmation; component volumes and unverified translations are not inferred. All eleven edition dates are reviewed metadata; new editions and nomination/mapping coverage require a plugin update. See awards/data/mao_dun_provenance.md.

Prix Médicis uses the official live winner table: French literature from 1958, foreign literature from 1970, and essay from 1985 (the archive omits essay winners for 1988 and 1993). Joint winners are preserved. Initial candidate coverage is the complete 2026 first selection (18 French and 17 foreign novels); Selected records retain the French selection terminology in their details and start unchecked for REVIEW. The Mars Room / Rachel Kushner, The Eight Mountains / Paolo Cognetti, Anil’s Ghost / Michael Ondaatje and We Do Not Part / Han Kang have verified English mappings; other entries require French source titles. No automatic translation or author-wide attribution. Specific volumes require identity confirmation. Refresh retains validated disk fallback on failure. Additional selection rounds and mappings require a reviewed update. See awards/data/medicis_provenance.md.


Reliability: Preferences Refresh clears idle RAM immediately and defers busy-source invalidation without waiting on network-held locks. Each lookup owns one optional stale-refresh budget, shared only with its source workers (including annual-page executors). Mutable network-backed sources reconsider observed RAM cache timestamps and pending requests. Failed optional attempts cool down for 60 seconds; budget-deferred attempts remain eligible next lookup, and explicit requests bypass the cooldown/budget. Bundled Diagram and Bad Sex archives have no network TTL and keep their reload-only behavior; Pulitzer retains its seed-first cold-start policy. Dublin requires reviewed coverage through 2026 and cannot replace a fuller saved archive with fewer years. Incomplete requested updates appear under Source update status even with no matching award rows. Edition/volume and author uncertainties display the factual identity note, with author evidence where different, and remain unchecked.

Reviewed English edition evidence and unresolved candidates for these four sources: [mapping review](awards/data/english_title_mapping_review_2026-10-07.md).

### CWA Gold Dagger coverage

The official CWA filtered archive, predecessor archive, 2021 individual result
and current award page supply 194 distinct records: 72 winners, 90 shortlisted,
29 longlisted and three Highly Commended entries. Winners cover every year
1955–2026; historical candidate lists are partial. The official award page
establishes continuity from the Crossed Red Herrings Award (1955–1959) to
Gold Dagger (1960 onward). Other Daggers are excluded. An undated Bluebird,
Bluebird entry is omitted, and the CWA's truncated 1963 author credit is
preserved, with a verified record-specific John le Carré alias. See awards/data/cwa_gold_dagger_provenance.md.

Official pagination can shift records between page boundaries. Missing reviewed
or previously cached entries are recovered from their live individual result
pages, with identity and distinction verified; the manifest supplies validation
evidence, not offline lookup results.

Coverage checks reject truncated retrieval and updates losing previously
accepted records. Valid fallback survives failed refreshes with source-level
diagnostics; fresh RAM/disk lookups avoid network requests. Unpublished future
cycles do not automatically become required when the calendar year changes.

Ordinary result rows show their checkbox and formatted award value. Hover over
the row or checkbox for source, scope, alias evidence and qualification details.
REVIEW labels remain visible and unchecked; actionable identity warnings and
source retrieval/coverage diagnostics remain visible. Tooltips and warnings
are never appended to the award-only metadata value.

### Build 019 desktop acceptance checkpoint (2026-10-09)

User-confirmed on Calibre 9.16.0: simplified winner and REVIEW rows,
checked winner defaults, unchecked REVIEW defaults, row/checkbox tooltips,
and these three successful desktop lookups:

| Title / Author | Confirmed result |
| --- | --- |
| The Death of Us / Abigail Dean | Checked 2026 winner; routine explanations in tooltip |
| Not Quite Dead Yet / Holly Jackson | Unchecked 2026 shortlist; visible REVIEW |
| The Spy Who Came in from the Cold / John le Carré | Checked 1963 winner; original CWA credit and scoped alias evidence in tooltip |

Previously confirmed Build 017 checks remain recorded: The Little Walls /
Winston Graham, The Death of Us / Abigail Dean, Not Quite Dead Yet / Holly
Jackson, and The Death of Us / Other Author (no match); award-only writeback,
including outer Edit Metadata Cancel. Build 018's The Invited no-error lookup
was also confirmed. No additional desktop confirmations are inferred, including
Preferences Refresh, the optional Mao Dun identity-warning case, or separate
OK/repeated-write checks.

Build 019 archive SHA-256:
`4b64759934bec6c75b0de86f01f4aa198e4c2353255bc3cffb465358b2dfd52f`.
All 73 allowlisted production files were reverified byte for byte against that
archive at finalization. Implementation files are unchanged from the reported
2,532-test passing suite; finalization adds this acceptance record and normalizes whitespace in the
non-production bibliography fixture, with unchanged parsed evidence.
Automated fixture, packaged Qt and live-source checks remain separate from
user desktop confirmations. The public release remains unchanged.
