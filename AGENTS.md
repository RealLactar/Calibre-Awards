# Calibre Awards — Agent Rules

## Project Purpose

Calibre Awards is a functional Calibre GUI plugin that checks a book against multiple literary-award sources from the single-book Edit Metadata dialog, presents qualified/review results, and can optionally write selected formatted award values to a configured custom field.

Source coverage is intentionally expandable. The plugin must remain accessible from Calibre's single-book Edit Metadata window without modifying Calibre's installed source files.

## Architectural Rules

1. Award retrieval, award qualification, output formatting, Calibre GUI integration, and write-back must remain separate components.

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

- Calibre 9.13.0
- Calibre embedded Python 3.14.6
- System Python 3.14.6
- Build/test tooling includes `calibre-customize` and `calibre-debug`
