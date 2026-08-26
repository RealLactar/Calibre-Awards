# Calibre Awards

Calibre Awards adds a **Check Awards** button to Calibre's single-book Edit
Metadata window. It searches supported literary-award sources, displays
matching results, and can optionally write selected awards to a Calibre
field.

**First public beta / preview — version 0.1.0**

Coverage will expand during the 0.x preview line. Please treat this release
as a preview and report mismatches.

## Supported sources

The plugin currently checks:

- Pulitzer Prizes
- Nebula Awards
- Hugo Awards
- Locus Awards via the Science Fiction Awards Database (SFADB)
- World Fantasy Awards
- Nobel Prize in Literature / NobelPrize.org

Category coverage is limited to the literary work awards each source
currently advertises in the plugin. Anthology, editor, artist, and publisher
awards are not supported where those fall outside the advertised work
categories.

Open **Calibre Awards** from the Calibre toolbar (or menu) for the
**Supported Award Sources** dialog. That list is the current category and
scope catalog.

## How it works

1. Open **Edit Metadata** for one book.
2. Click **Check Awards**.
3. The plugin checks the sources you have enabled.
4. Matching results are shown for review.
5. If write-back is enabled, you may select results to write.

Lookup requires internet access. If one source fails, results from the other
enabled sources are still shown. Checking awards does not change book
metadata by itself.

## Qualification

When a source publishes an explicit ordinal rank (for example 3rd place),
the plugin uses the Preferences setting **Highest explicit ordinal rank to
include**. The default cutoff is 5. Raising it to 20 allows an explicit
19th-place result to qualify.

Only ranks published by the source are used. Visual or list order is never
treated as a rank. Unranked Winner, Finalist, and Nominee statuses keep
their award-specific rules; not every finalist qualifies.

## Possible author matches

Author matching is conservative. The plugin does not treat similar names as
the same person.

One implemented case is an omitted middle initial. For example:

- Calibre: Allen M. Steele
- Source: Allen Steele

That can appear as a **Possible Author Match**. Such a result is visually
marked, starts **unchecked** even if its award rank otherwise qualifies, and
is included for write-back only if you check it. Confirming it does **not**
change the Calibre Authors field.

## Preferences

Open **Preferences → Plugins → Calibre Awards → Customize plugin**.

**Award sources.** Enable or disable individual sources.

**Qualification and award output.** Rank cutoff is 1–100 (default 5).

**Award output template.** Supported placeholders:

- `<placement>`
- `<year>`
- `<award>`
- `<category>`

Default:

`<placement> - <year> <award> - <category>`

You may omit placeholders or add literal text.

**Restore rank & output defaults** restores only the rank cutoff and output
template. It does not reset source selection or write-back settings.

**Write-back** is optional and off by default. You choose a destination
custom column and append or replace. Append skips award values that already
match an existing entry (case-insensitive). Selected awards are applied to
the Edit Metadata form; Calibre's normal **OK** / **Cancel** still decides
whether those metadata changes are saved.

## Known limitations

- Pulitzer.org may temporarily block automated retrieval. Other enabled
  sources continue running.
- Hugo explicit ordinal placement is available only where the plugin has
  statistics-backed official ranking data. Visual or list order is never
  treated as a rank.
- Locus omitted-middle-initial differences may appear as a Possible Author
  Match and require confirmation.
- Award websites can change structure and temporarily break a source.
- Anthology, editor, and other unsupported non-work categories are outside
  this preview.

## Installation

Install from the **public release ZIP**, not from a Git checkout.

1. In Calibre, open **Preferences → Plugins**.
2. Choose **Load plugin from file**.
3. Select `Calibre-Awards-0.1.0.zip`.
4. Restart Calibre if it asks you to.

Advanced users can install the same ZIP from a command prompt:

```text
calibre-customize -a Calibre-Awards-0.1.0.zip
```

## Upgrading

Load a newer Calibre Awards ZIP the same way (**Preferences → Plugins →
Load plugin from file**). Calibre replaces the installed plugin with the
ZIP you load.

This plugin stores preferences in Calibre's configuration directory, not
inside the ZIP. Loading a newer ZIP updates the plugin code; existing
preferences are typically kept. A future release will say so if a setting
cannot be migrated.

## Uninstall

**Preferences → Plugins**, select **Calibre Awards**, then **Remove plugin**.

## Requirements

- Calibre 9.13.0 or later
- Windows, macOS, or Linux (as declared by the plugin)
- Internet connection during award lookup

## Privacy

This plugin does not use an AI service, does not require an API key, and
does not require an external user account. It does not implement telemetry.
Award sites you query will see ordinary HTTPS requests during lookup.

## Feedback

This is a beta / preview. Please report problems at:

https://github.com/RealLactar/Calibre-Awards/issues

Useful reports include book title, author, the award or source involved,
what the plugin returned, and what you expected.

## License

Calibre Awards is licensed under [GPL-3.0-or-later](LICENSE).
