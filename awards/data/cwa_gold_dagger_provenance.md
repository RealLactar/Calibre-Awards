# CWA Gold Dagger — reviewed official coverage

Reviewed 2026-10-08. All evidence below is the Crime Writers’ Association's
own HTML. No outside winner list or invented translations are used.

## Retrieval and identity

- Award home: https://thecwa.co.uk/awards-and-competitions/the-daggers/gold-dagger/
- Main filtered archive: https://thecwa.co.uk/past-winners/?past_winners_awards%5B0%5D=gold
- Pages 2–16 follow https://thecwa.co.uk/past-winners/page/2/?past_winners_awards%5B0%5D=gold
  (replace 2 with the explicit page number). Pagination and canonical filtered
  next links are validated, including the final page.
- Predecessor archive: https://thecwa.co.uk/past-winners/?past_winners_awards%5B0%5D=gold-crossed-herrings
- Missing-from-listing 2021 winner supplement: https://thecwa.co.uk/past-winners/we-begin-at-the-end/

The award home explicitly dates the original **Crossed Red Herrings Award**
to 1955 and its renaming to **Gold Dagger** to 1960. Predecessor result pages
use **Crossed Herrings Dagger**, retained in source details. Modern sponsorship
is displayed as **KAA Gold Dagger**; these names form the same main award.
Earlier translated works remain eligible main-award records: the home says
the separate translation award began in 2006. No separate translation award,
Silver, Diamond, Steel, New Blood, Historical, non-fiction Gold or other Dagger
is included. Only explicitly labelled main-award work records are parsed;
author biographies and their other awards are not used.

## Verified inventory and limitations

Sixteen archive pages contain 188 cards, including two repeated identities
and one undated card. The predecessor adds five winners; the 2021 detail
adds Chris Whitaker's We Begin at the End; the home supplies the explicit
2026 shortlist and 13-book longlist. After identity/status deduplication:

| Distinction | Distinct records |
| --- | ---: |
| Winner | 72 |
| Shortlisted | 90 |
| Longlisted | 29 |
| Highly Commended | 3 |
| Total | 194 |

Winner coverage is contiguous **1955–2026**, one per year. Candidate coverage
is **partial and uneven, 2004–2026**; completeness is claimed only for the
reviewed winner years and the captured candidate inventory, not all historical
shortlists/longlists. The 2026 winner is The Death of Us by Abigail Dean:
https://thecwa.co.uk/past-winners/the-death-of-us/
The first winner is The Little Walls by Winston Graham:
https://thecwa.co.uk/past-winners/the-little-walls/

Known official-data gaps:
- Bluebird, Bluebird by Attica Locke is labelled Shortlisted but has no award
  year in either archive or detail. It is excluded without guessing:
  https://thecwa.co.uk/past-winners/bluebird-bluebird/
- The 1963 winner The Spy Who Came in from the Cold credits **John le Carr**
  in both archive and detail. That exact truncated name is preserved; the verified alias below resolves the standard author spelling: https://thecwa.co.uk/past-winners/the-spy-who-came-in-from-the-cold/
- The archive omits the 2021 winner card; its dated individual result is fetched
  explicitly on every cold retrieval.

## Validation, matching and policy

The reviewed coverage manifest records per-year/distinction minimum counts.
Every reviewed winner year is required, all advertised pages must be retrieved,
and replacement cannot lose any previously accepted identity or demote its
distinction, including later published years. Calendar rollover alone does
not require unpublished results. Future explicit candidates can be accepted
without inventing a winner. Failed/incomplete updates retain validated prior
cache and pending requests. Existing runtime guards provide invocation-local
budgets, TTL reconsideration, failure cooldown and generation-safe publication.

Titles/authors use exact normalized matching, not fuzzy matching. CWA's own
SA Cosby / S. A. Cosby initial variants are normalized. Translators, publisher
columns and judges are not authors. Winners supersede repeated candidate
rows; Shortlisted supersedes Longlisted. All ranks are None. Winners qualify
and start checked; Shortlisted, Longlisted and Highly Commended remain REVIEW
and unchecked. Historical award labels are preserved in source details.

## Fixtures versus live checks

The tests/fixtures/cwa_gold_dagger README documents official captured HTML
sections. Tests are offline and include synthetic malformed/future variations.
Live production retrieval and desktop/Qt checks are reported separately in
the completion report; fixture tests do not establish current live availability.

## Pagination instability correction (Build 018)

A second live retrieval from Calibre's embedded Python returned 191 distinct
records before validation. Eight reviewed identities were absent and five
previously unseen shortlist entries appeared, despite all 16 pages being
retrieved. The archive's year ordering is not sufficient to keep books fixed
at pagination boundaries. The eight missing entries were individually verified
again on official result pages, producing 199 distinct records in that run.
This does not establish complete candidate history.

The reviewed manifest now also requires exact work identities and distinctions,
not merely aggregate counts. Retrieval fills omissions from their live official
individual result URLs, verifying title, author, year, award and distinction.
Previously cached additional identities receive the same recovery. It never
creates lookup results from manifest data alone. If recovery fails or changes
identity/distinction, retrieval remains incomplete and valid saved fallback and
pending requests survive. Existing Build 017 caches remain usable; no schema
change or discard of historical data is required. Announcement-only longlist
entries must remain in the live announcement, because no individual official
result URL was provided.

## Verified author alias (Build 019, reviewed 2026-10-09)

The author’s official bibliography identifies The Spy Who Came in from the
Cold, Author: John le Carré, Published: September 1963:
https://johnlecarre.com/books/the-spy-who-came-in-from-the-cold
The publisher independently credits the same title to John le Carré:
https://www.penguin.co.uk/books/179112/the-spy-who-came-in-from-the-cold-by-carre-john-le/9780241978955
(Penguin Essentials paperback ISBN 9780241978955, published 4 August 2016).
The current official bibliography was retrieved with HTTP 200; its HTML
is captured as le-carre-bibliography.html for evidence.

The lookup alias accepts John le Carré only for the 1963 Winner, exact title,
Gold Dagger label, original John le Carr credit and exact official CWA result
URL https://thecwa.co.uk/past-winners/the-spy-who-came-in-from-the-cold/.
It does not change global author normalization, other works, award years,
distinctions, URLs, stored cache records or the original source credit.
AwardResult.work_author remains John le Carr; the verified alias and evidence
are included in source details and the row tooltip. No cache migration is
needed. The alias is already confirmed by primary evidence, so it does not
create a manual identity-warning requirement. The winner stays checked.
