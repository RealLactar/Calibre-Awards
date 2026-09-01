# Changelog

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

- Pulitzer.org may present an anti-automation challenge; the plugin does
  not bypass it
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
