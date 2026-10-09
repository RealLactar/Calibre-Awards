# Official CWA HTML fixtures

Captured 2026-10-08 by direct HTTPS retrieval from the CWA. These are extracted
HTML sections, not reconstructed representative markup. Newlines were inserted
between adjacent tags for review. Tests also remove that whitespace to exercise
minified live pagination. Complete raw responses remain outside the repository
in the task work directory; no tests/logs are packaged.

- page-1.html: https://thecwa.co.uk/past-winners/?past_winners_awards%5B0%5D=gold
- page-N.html (2–16): https://thecwa.co.uk/past-winners/page/N/?past_winners_awards%5B0%5D=gold
  (N is the actual number). Retain section.books and nav.pagination, including
  titles, author credits, distinction/year and individual result links.
- predecessor.html: https://thecwa.co.uk/past-winners/?past_winners_awards%5B0%5D=gold-crossed-herrings
  Retain section.books and any pagination (none in the captured response).
- home.html: https://thecwa.co.uk/awards-and-competitions/the-daggers/gold-dagger/
- detail.html: https://thecwa.co.uk/past-winners/the-death-of-us/
- supplement-2021.html: https://thecwa.co.uk/past-winners/we-begin-at-the-end/
- detail-1955.html: https://thecwa.co.uk/past-winners/the-little-walls/
- detail-1963.html: https://thecwa.co.uk/past-winners/the-spy-who-came-in-from-the-cold/
- undated.html: https://thecwa.co.uk/past-winners/bluebird-bluebird/

Home/detail fixtures retain the original main element. Header/footer, scripts
and outside-page assets are omitted. Images/links inside retained sections
remain intact. Yearless Bluebird and truncated John le Carr credits are
intentional official evidence, not invented test errors. The archive has
188 cards; merged production coverage is 194 distinct records including
72 winners 1955–2026, 90 Shortlisted, 29 Longlisted and 3 Highly Commended.
Historical candidate coverage is partial. Synthetic mutations in tests are
explicitly separate from these source-grounded fixtures.

Build 018 pagination reproduction: shifting-page-N.html contains the same
books/pagination sections from a second actual filtered archive retrieval
(N=2–12), with the same URLs as page-N.html. No tags or records were invented.
recover-SLUG.html retains the main element from
https://thecwa.co.uk/past-winners/SLUG/ for the eight omitted records. These
individual pages were fetched again and their explicit fields agreed with
the reviewed identities. The shifted archive alone yields 191 distinct rows;
recovering the eight reviewed omissions yields 199, including five previously
unseen shortlist entries. This is evidence of unstable page boundaries, not
a claim of complete historical candidate coverage.

le-carre-bibliography.html: official author bibliography fetched 2026-10-09
with HTTP 200 from https://johnlecarre.com/books/the-spy-who-came-in-from-the-cold.
The original main element is retained when present, otherwise the full HTML.
It identifies John le Carré and September 1963 for this exact novel. It is
primary evidence for the scoped alias; CWA fixture credits remain unchanged.

Finalization normalized bibliography-fixture line endings and trailing whitespace;
parsed text and primary evidence remain unchanged.
