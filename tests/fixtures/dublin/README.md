# Dublin regression fixtures

Official public annual pages, complete candidate-list responses and prize-year sitemap fetched on 2026-10-04.

Source: https://dublinliteraryaward.ie/prize_years_type-sitemap.xml
Annual canonical URLs are retained in each fixture. Complete lists use the public GET endpoint called by the site's own `fz0_loadTheLibraryMod` JavaScript: `/wp-admin/admin-ajax.php?action=fz0_ajax_load_books_list_item_block&load_mode=ajax-load`, with the annual module's book-category IDs and `display_limit=-1`. No guessed status or ordinal rank.

These HTML files are structural extracts, not byte-for-byte raw pages. They retain factual titles, author names, year/status sections and identity links. Images, navigation, judges, reviews and library descriptions are omitted. Annual extracts combine the complete section response with its original heading and mark the resulting grid as unlimited. `2026-preview.html` preserves actual annual-page limit/filter attributes, while `2026-longlist-all.html` and `2026-nominated-all.html` preserve complete response cards for offline completion tests. Full raw captures remain in the task workspace.

3,608 distinct work/year records, 1996–2026, including 31 winners. Repeated entries retain the strongest published status: Winner > Shortlisted > Longlisted > Nominated. The 2026 full lists contain 69 nominees and 20 longlisted books, including the six shortlisted works. Nominated, Longlisted and Shortlisted results qualify for REVIEW and appear unchecked by default.

The official 2013 LONGLIST section and full-list response explicitly report no books found. Only its ten winner/shortlisted entries are covered; no missing nominations are fabricated. Other years retain the section labels currently published by the official annual archive, which vary historically.

English source title/author forms and spelling quirks are retained. Translators are not author aliases. The official author link for Felicia Berliner uses a named public WordPress author-post URL rather than the usual canonical author path.
