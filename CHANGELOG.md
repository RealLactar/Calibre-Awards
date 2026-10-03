# Changelog

## Unreleased

### Added

- Refresh all enabled award sources with one confirmation in Preferences.
  Successful Refresh buttons show Refresh queued for the current preferences
  session; partial failures remain available for retry.

- Wolfson History Prize executable source, with Winner coverage from the
  official archive beginning in 1972 and official Shortlisted coverage
  from 2017

### Fixed

- Locus now reports SFADB hosting suspension pages as source failures instead
  of treating HTTP 200 responses with no award data as successful no-match
  lookups. Validated stale caches remain usable during failed refreshes.

## 0.3.0 beta - 2026-09-28

### Added

- Edgar Awards
- Romantic Novel of the Year Awards
- International Booker Prize
- Executable award-source count increased from 17 to 20
- Reviewed bundled Pulitzer Fiction/Novel snapshot, used when unattended
  retrieval is blocked
- Nobel Check Awards display of the official English prize motivation and
  of unusual prize statuses (declined, restricted)

### Changed

- Pulitzer cold start uses the reviewed official snapshot. Live refresh
  remains opportunistic. Pulitzer Refresh keeps last-known-good Pulitzer
  data and that snapshot.
- Nobel Literature results are always author-level. Works explicitly named
  in official motivations are citation annotations, not books that won the
  Nobel Prize.
- Nobel lookups follow additional API pages when needed. Saved Nobel cache
  from earlier releases is rebuilt.
- Category is optional in award output. A result with no category omits
  that placeholder and does not leave a fake marker or dangling separator.
- Preferences explains that Check Awards is hidden when no executable award
  sources are enabled.

### Fixed

- Progress-dialog Cancel explanation is no longer clipped
- Check Awards no longer appears when no executable sources are enabled
- Pulitzer Refresh confirmation and status text follow the Pulitzer source
  key rather than the display label

## 0.2.0 beta - 2026-09-01

### Added

Eleven new executable award sources since v0.1.1 (6 sources then, 17 now):

- John Newbery Medal
- The Booker Prize
- Deutscher Buchpreis
- Prix Goncourt
- Miles Franklin Literary Award
- Women's Prize for Fiction
- National Book Critics Circle Awards
- PEN/Faulkner Award for Fiction
- PEN/Hemingway Award for Debut Novel
- International Prize for Arabic Fiction
- Bram Stoker Awards

Also added:

- Persistent per-source award cache
- Per-source cache Refresh controls in Preferences
- National Book Awards unavailable / informational row (Transport blocked)
- Source-specific qualification rules required by the new awards
  (for example Honor, Shortlisted, and selected Finalist policies)

### Changed

- Executable award-source count increased from 6 to 17
- Preferences now includes per-source Refresh
- Award-source lists in Preferences and Supported Award Sources scroll
  more reliably as the catalog grew
- Nobel source label presented as Nobel Award

### Known limitations

- Pulitzer.org may block unattended retrieval; the plugin uses a reviewed
  official Fiction/Novel snapshot through 2026 and does not bypass browser
  challenges. Live official refresh remains opportunistic.
- National Book Awards is currently unavailable (Transport blocked)
- Some sources intentionally have partial historical finalist or shortlist
  coverage
- External website changes can temporarily affect lookups

See README.md for the full user-facing limitation list.

## 0.1.1 beta - 2026-08-26

- Support Calibre 6.0 and later

## 0.1.0 beta - 2026-08-25

First public beta / preview.

- Check Awards in the single-book Edit Metadata dialog
- Six executable sources: Pulitzer Prizes, Nebula Awards, Hugo Awards,
  Locus Awards, World Fantasy Awards, and Nobel Prize in Literature
- Optional write-back to a custom column
