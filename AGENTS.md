# Calibre Awards — Agent Rules

## Project Purpose

Calibre Awards is a Calibre GUI plugin that discovers literary awards associated with a specific book or story.

The eventual plugin should be accessible from Calibre's single-book Edit Metadata window without modifying Calibre's installed source files.

## Architectural Rules

1. Award retrieval, award qualification, output formatting, and Calibre GUI integration must remain separate components.

2. Genre must never be treated as mutually exclusive. A work may belong to several applicable award families.

3. Major general literary awards must be searched independently of genre-specific awards.

4. Never infer an ordinal rank from terms such as finalist, shortlist, nominee, honor book, or runner-up.

5. Preserve the award organization's actual terminology.

6. Every award result must retain its source and source URL when available.

7. Individual award-source parsers must never directly modify Calibre metadata.

8. Network requests must never block Calibre's GUI thread.

9. Changes made from the Edit Metadata window must respect Calibre's normal OK and Cancel behavior.

10. The plugin must not modify Calibre's installed source files.

11. Undocumented Calibre internal APIs may be used for Edit Metadata integration only when necessary, and such usage must be isolated so it can be repaired if Calibre changes internally.

12. Initial development must favor small, independently testable steps over implementing the entire plugin at once.

13. Do not add dependencies, frameworks, source files, or architectural components unless explicitly requested or clearly required by the current task.

14. Do not change these architectural rules without explicit instruction.

## Development Environment

- Windows 10
- Calibre 9.13.0
- Calibre embedded Python 3.14.6
- System Python 3.14.6
- Repository root: `C:\Users\apt\Git\Calibre-Awards`
- Build/test tooling includes `calibre-customize` and `calibre-debug`

## Current Development Goal

The first proof of concept will be a normal installable Calibre plugin that can place a Check Awards button in the single-book Edit Metadata dialog without altering Calibre's installed files.

Initially, clicking that button only needs to prove that it can read the Title and Author currently displayed in the open Edit Metadata dialog.

Do not implement that proof of concept yet.
