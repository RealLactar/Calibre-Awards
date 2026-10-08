# Newbery 2024–2026 provenance

Reviewed 2026-10-07 against official ALA HTML and the March 2026 cumulative PDF. Existing historical Drupal listings remain the source for 1930–2023; no 1922–1929 coverage or translation mappings were added.

Historical listing URLs (all HTTPS, ALA):
- https://www.ala.org/awards/books-media/john-newbery-medal-1 — 1930–1991, 278 records.
- https://www.ala.org/awards/books-media/john-newbery-medal — 1992–2003, 48 records.
- https://www.ala.org/awards/books-media/john-newbery-medal-2 — 2004–2023, 85 records.

Current HTML sources:
- https://www.ala.org/news/2024/01/american-library-association-announces-2024-youth-media-award-winners — 2024 Medal winner and five Honor Books.
- https://www.ala.org/news/2025/01/american-library-association-announces-2025-youth-media-award-winners — 2025 Medal winner and four Honor Books.
- https://www.ala.org/news/2026/01/american-library-association-announces-2026-youth-media-award-winners — 2026 Medal winner and four Honor Books.

Cross-check: https://www.ala.org/sites/default/files/2026-03/newbery-medals-honors-1922-present.pdf, page 1. All sixteen 2024–2026 titles, authors, years and Medal/Honor distinctions agree. Tests independently enumerate the PDF identities. PDF is verification evidence only; the runtime retrieves HTML. AwardResult.source_url for recent records points to the official annual announcement; historical records retain their /winner/... URL.

Authors are extracted only from explicit written by / written and illustrated by citations inside the bounded Newbery section. The neighboring Caldecott section is excluded. Illustrator credits (Shawn Harris, Junyi Wu, Daniel Miyares, Marcin Minor) are not Newbery author aliases. Creator spelling and accented names are preserved. No ranks are inferred; Winner and Honor retain their existing qualification policy and checked defaults, including the deliberate Newbery Honor exception.

Coverage: 427 records, 97 Medal winners and 330 Honors, covering every year 1930–2026 in the live retrieval checked on review date. The reviewed annual counts are fixed at 6/5/5, preventing missing Honors or newest-year omissions. New years require a separate reviewed extension.

Cache schema 2 validates all six source pages and complete 1930–2026 coverage. A schema-1 archive is accepted only as validated 1930–2023 fallback, treated as logically stale regardless of timestamp, never as complete current coverage. Failed/deferred updates retain historical bytes and emit one source diagnostic even with zero matches; explicit requests stay pending until replacement succeeds. Optional failures use the shared cooldown; subsequent eligible lookups retry without restarting. Successful schema-2 publication replaces the old archive. Existing refresh generations prevent superseded retrieval from consuming a newer request.

Live HTTP checks: all six official pages returned successfully through the production retrieval path; all three recent Medal winners and the 2026 Undead Fox Honor matched; illustrator-only negative queries returned no match. Fresh subsequent recent queries made no additional HTTP requests. Historical author confirmation remains lazy and RAM-only.
