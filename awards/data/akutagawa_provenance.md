# Akutagawa Prize provenance and initial scope

Reviewed 2026-10-04. Prize facts come from the Society for the Promotion of Japanese Literature and Bungeishunju, not from publisher author-wide award advertising.

## Official prize records

Winner archive: https://bungakushinko.or.jp/award/akutagawa/list.html
Prize description and two half-year cycles: https://bungakushinko.or.jp/award/index.html
Round 162 nomination announcement: https://books.bunshun.jp/articles/-/5210
Round 175 nomination announcement: https://books.bunshun.jp/articles/-/11012

Reviewed winner baseline: rounds 1–175, 1935–2026, 189 winning works and 33 rounds explicitly marked no award. The baseline round metadata in akutagawa_mappings.json validates year/half and minimum row counts without inventing award dates or rejecting joint winners as duplicates. Raw Japanese identities are retained. Only pronunciation spans explicitly marked small in the official winner markup are excluded from the matching title; the complete original label remains in source_title and displayed source details. A nominee whose original label matches the same-round winning record is shown once as Winner.

Nomination coverage is deliberately limited to the two complete announcements above, five candidates each, leaving eight Nominated results after winner deduplication. This is not a complete historical nomination archive and does not automatically grow when a later round is announced. First-party nomination announcements also discuss other prizes and earlier works in biographies; only the stated Akutagawa candidate-heading section is parsed.

## Reviewed title/name mappings

These identify particular works. They are not an author-wide list of award recipients. Official Japanese winner/nominee records establish the prize fact; the following primary sources establish English title/name correspondences. No machine translation, automatic romanization, guessed reordered names or unverified subtitles are added.

| Round | Japanese title / author | English title / author | Evidence |
|---|---|---|---|
| 130 | 蛇にピアス / 金原ひとみ | Snakes and Earrings / Hitomi Kanehara | https://www.penguin.co.uk/authors/202788/hitomi-kanehara ; https://cdn.penguin.co.uk/dam-assets/books/9781529955613/9781529955613-sample.pdf |
| 150 | 穴 / 小山田浩子 | The Hole / Hiroko Oyamada | https://www.ndbooks.com/book/the-hole-1/ |
| 151 | 春の庭 / 柴崎友香 | Spring Garden / Tomoka Shibasaki | https://pushkinpress.com/book/spring-garden/ |
| 153 | 火花 / 又吉直樹 | Spark / Naoki Matayoshi | https://pushkinpress.com/book/spark/ ; publisher/author announcement of the English Hibana: Spark edition, https://prtimes.jp/main/html/rd/p/000000013.000043732.html |
| 155 | コンビニ人間 / 村田沙耶香 | Convenience Store Woman / Sayaka Murata | https://groveatlantic.com/book/convenience-store-woman/ |
| 161 | むらさきのスカートの女 / 今村夏子 | The Woman in the Purple Skirt / Natsuko Imamura | https://www.waseda.jp/inst/wihl-annex/interviews-en/1240 ; https://www.faber.co.uk/product/9780571364688-the-woman-in-the-purple-skirt/ |
| 162 | デッドライン / 千葉雅也 | Deadline / Masaya Chiba | https://masayachiba.jp/masaya-chiba/biography/ |
| 164 | 推し、燃ゆ / 宇佐見りん | Idol, Burning / Rin Usami | https://www.harperlibrarybookclub.com/9780063213289/idol-burning/ |
| 169 | ハンチバック / 市川沙央 | Hunchback / Saou Ichikawa | https://www.penguinrandomhouse.com/books/768583/hunchback-by-saou-ichikawa-translated-by-polly-barton/ |

Deadline's author-published English title/name is supported. This mapping does not claim that a published English translation exists. The other eight entries are published English winning-work mappings. Translator names are never author aliases.

## Identity exclusions

Earthlings is not awarded simply because Sayaka Murata won for Convenience Store Woman. The Factory is not awarded simply because Hiroko Oyamada won for The Hole. Breasts and Eggs is deliberately not mapped: the English publisher describes an expanded novel developed from the earlier prize-winning novella, requiring separate identity review. Collections containing a winning story, such as English collections associated with Yoko Ogawa's Pregnancy Diary, are also excluded from automatic mappings. Original Japanese winning-work identities can still be looked up directly.

## Dates, UI and maintenance

Award year and half-year follow the official archive, not the January announcement or English translation publication year. The Hole returns the 2013 second-half award and Snakes and Earrings the 2003 second-half award. No ordinal rank is inferred. Winners qualify under the common qualifier; nominees are REVIEW and are unchecked by the existing dialog. Cache schema 1 is isolated to Akutagawa. Failed refresh keeps validated saved data and its pending request. The winner list can grow live; additional nominee announcements and English mappings require reviewed plugin updates.
