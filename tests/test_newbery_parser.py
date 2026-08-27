"""Offline coverage for the Newbery listing and winner-byline parsers."""

from __future__ import annotations

import unittest
from pathlib import Path

from awards.sources.newbery import (
    ARCHIVE_MAX_YEAR,
    ARCHIVE_MIN_YEAR,
    ARCHIVE_URL_1992_2003,
    ARCHIVE_URLS,
    AWARD_NAME,
    CATEGORY,
    NewberySourceError,
    _author_from_byline,
    _parse_detail_author,
    _parse_listing_html,
    _titles_match,
)

FIXTURES = Path(__file__).resolve().parent / 'fixtures' / 'newbery'
LISTING_URL = ARCHIVE_URL_1992_2003


def _load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding='utf-8')


def _listing(html: str, source_url: str = LISTING_URL):
    return _parse_listing_html(html, source_url)


def _row(
    *,
    title: str,
    rank: str,
    href: str = '/winner/crispin-cross-lead',
    year_heading: str = '2003',
) -> str:
    return f"""
    <div class="accordion-item">
      <h3 class="accordion-item__heading"><button>{year_heading}</button></h3>
      <table class="views-table">
        <thead>
          <tr>
            <th class="views-field-title-1">Title</th>
            <th class="views-field-field-winner-rank">Year</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td class="views-field-title-1"><a href="{href}">{title}</a></td>
            <td class="views-field-field-winner-rank">{rank}</td>
          </tr>
        </tbody>
      </table>
    </div>
    """


def _detail_page(title: str, byline: str | None, body: str) -> str:
    byline_html = f'<p>{byline}</p>' if byline is not None else ''
    return f"""
    <h1>{title}</h1>
    <div class="font-bitter text-center">{byline_html}</div>
    <h2>About</h2>
    <p>{body}</p>
    """


class NewberyConstantsTests(unittest.TestCase):
    def test_award_identity_and_archive_bounds(self):
        self.assertEqual(AWARD_NAME, 'Newbery Medal')
        self.assertEqual(CATEGORY, "Children's Literature")
        self.assertEqual(ARCHIVE_MIN_YEAR, 1930)
        self.assertEqual(ARCHIVE_MAX_YEAR, 2023)
        self.assertEqual(len(ARCHIVE_URLS), 3)
        self.assertTrue(
            all(url.startswith('https://www.ala.org/') for url in ARCHIVE_URLS)
        )


class NewberyListingParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = _listing(_load_fixture('listing_2003_excerpt.html'))

    def _by_title(self, title: str):
        return [record for record in self.records if record.work_title == title]

    def test_winner_parses_once_with_normalized_status(self):
        matches = self._by_title('Crispin: The Cross of Lead')
        self.assertEqual(len(matches), 1)
        record = matches[0]
        self.assertEqual(record.award_year, 2003)
        self.assertIsInstance(record.award_year, int)
        self.assertEqual(record.status, 'Winner')
        self.assertEqual(
            record.detail_url,
            'https://www.ala.org/winner/crispin-cross-lead',
        )
        self.assertEqual(record.source_url, LISTING_URL)
        self.assertFalse(hasattr(record, 'rank'))

    def test_honor_parses_with_normalized_status(self):
        scorpion = self._by_title('The House of the Scorpion')
        self.assertEqual(len(scorpion), 1)
        self.assertEqual(scorpion[0].status, 'Honor')
        self.assertEqual(scorpion[0].award_year, 2003)
        self.assertEqual(
            scorpion[0].detail_url,
            'https://www.ala.org/winner/house-scorpion-0',
        )

    def test_honor_books_are_unranked_siblings(self):
        honors = [record for record in self.records if record.status == 'Honor']
        self.assertEqual(
            [record.work_title for record in honors],
            [
                'The House of the Scorpion',
                'Pictures of Hollis Woods',
                'Hoot',
            ],
        )
        for record in honors:
            self.assertFalse(hasattr(record, 'rank'))
            self.assertEqual(record.status, 'Honor')

    def test_blurb_and_mobile_year_field_are_not_the_title(self):
        crispin = self._by_title('Crispin: The Cross of Lead')[0]
        self.assertNotIn('Winner(s)', crispin.work_title)
        self.assertNotIn('Starr LaTronica', crispin.work_title)
        self.assertNotIn('Hyperion', crispin.work_title)

    def test_identical_duplicate_row_is_collapsed(self):
        titles = [record.work_title for record in self.records]
        self.assertEqual(titles.count('Crispin: The Cross of Lead'), 1)
        keys = [
            (
                record.award_year,
                record.status,
                record.work_title.casefold(),
                record.detail_url,
            )
            for record in self.records
        ]
        self.assertEqual(len(keys), len(set(keys)))

    def test_relative_detail_url_becomes_absolute(self):
        records = _listing(
            _row(title='Hoot', rank='2003 - Honor(s)', href='/winner/hoot-0')
        )
        self.assertEqual(records[0].detail_url, 'https://www.ala.org/winner/hoot-0')

    def test_runner_up_normalizes_to_honor_without_rank(self):
        records = _listing(
            _row(
                title='The Story of Mankind',
                rank='1930 - Runner-up(s)',
                href='/winner/story-mankind',
                year_heading='1930',
            )
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].status, 'Honor')
        self.assertEqual(records[0].award_year, 1930)
        self.assertFalse(hasattr(records[0], 'rank'))

    def test_accordion_year_conflict_fails_closed(self):
        html = _row(
            title='Crispin: The Cross of Lead',
            rank='1999 - Winner(s)',
            year_heading='2003',
        )
        with self.assertRaises(NewberySourceError) as caught:
            _listing(html)
        self.assertIn('does not match', str(caught.exception))

    def test_malformed_status_fails_closed(self):
        html = _row(
            title='Crispin: The Cross of Lead',
            rank='2003 - Finalist(s)',
        )
        with self.assertRaises(NewberySourceError) as caught:
            _listing(html)
        self.assertIn('malformed award status', str(caught.exception))

    def test_plain_winner_without_parentheses_fails_closed(self):
        html = _row(
            title='Crispin: The Cross of Lead',
            rank='2003 - Winner',
        )
        with self.assertRaises(NewberySourceError):
            _listing(html)

    def test_missing_title_fails_closed(self):
        html = """
        <h3 class="accordion-item__heading">2003</h3>
        <table class="views-table">
          <thead><tr><th class="views-field-title-1">Title</th>
          <th class="views-field-field-winner-rank">Year</th></tr></thead>
          <tbody>
            <tr>
              <td class="views-field-title-1"></td>
              <td class="views-field-field-winner-rank">2003 - Winner(s)</td>
            </tr>
          </tbody>
        </table>
        """
        with self.assertRaises(NewberySourceError) as caught:
            _listing(html)
        self.assertIn('missing a title', str(caught.exception))

    def test_missing_detail_url_fails_closed(self):
        html = """
        <h3 class="accordion-item__heading">2003</h3>
        <table class="views-table">
          <thead><tr><th class="views-field-title-1">Title</th>
          <th class="views-field-field-winner-rank">Year</th></tr></thead>
          <tbody>
            <tr>
              <td class="views-field-title-1">Crispin: The Cross of Lead</td>
              <td class="views-field-field-winner-rank">2003 - Winner(s)</td>
            </tr>
          </tbody>
        </table>
        """
        with self.assertRaises(NewberySourceError) as caught:
            _listing(html)
        self.assertIn('missing an official winner URL', str(caught.exception))

    def test_off_host_detail_url_fails_closed(self):
        html = _row(
            title='Crispin: The Cross of Lead',
            rank='2003 - Winner(s)',
            href='https://evil.example/winner/crispin-cross-lead',
        )
        with self.assertRaises(NewberySourceError):
            _listing(html)

    def test_empty_fragment_without_rows_is_not_an_error(self):
        self.assertEqual(_listing('<p>About the Newbery Medal</p>'), [])


class NewberyTitleMatchingTests(unittest.TestCase):
    def test_one_sided_subtitle_colon_matches(self):
        self.assertTrue(
            _titles_match('Crispin', 'Crispin: The Cross of Lead')
        )
        self.assertTrue(
            _titles_match('Crispin: The Cross of Lead', 'Crispin')
        )

    def test_standalone_ampersand_matches_and(self):
        self.assertTrue(
            _titles_match(
                'Smith & Jones',
                'Smith and Jones',
            )
        )

    def test_two_sided_colon_does_not_fall_back(self):
        self.assertFalse(
            _titles_match(
                'Crispin: The Cross of Lead',
                'Crispin: A Different Subtitle',
            )
        )


class NewberyAuthorBylineTests(unittest.TestCase):
    def test_written_by_stops_before_publisher(self):
        self.assertEqual(
            _author_from_byline(
                'Written by Amina Luqman-Dawson. Published by '
                'JIMMY Patterson/Little, Brown Books for Young Readers.'
            ),
            'Amina Luqman-Dawson',
        )

    def test_by_name_and_published_by(self):
        self.assertEqual(
            _author_from_byline(
                'by Jerry Spinelli, and published by Little, Brown'
            ),
            'Jerry Spinelli',
        )

    def test_mononym_byline(self):
        self.assertEqual(
            _author_from_byline('by Avi, and published by Hyperion'),
            'Avi',
        )

    def test_quoted_title_written_by(self):
        self.assertEqual(
            _author_from_byline(
                '"The Last Cuentista" written by Donna Higuera. '
                'Published by Levine Querido.'
            ),
            'Donna Higuera',
        )

    def test_missing_byline_text_is_not_an_author(self):
        self.assertIsNone(_author_from_byline(''))
        self.assertIsNone(_author_from_byline('Published by Hyperion'))
        self.assertIsNone(
            _author_from_byline(
                'A lyrical narrative tells the story of several children.'
            )
        )


class NewberyDetailAuthorHtmlTests(unittest.TestCase):
    def test_written_by_subtitle_from_html(self):
        html = _load_fixture('detail_written_by.html')
        self.assertEqual(_parse_detail_author(html), 'Amina Luqman-Dawson')

    def test_spinelli_and_avi_and_cuentista_html(self):
        self.assertEqual(
            _parse_detail_author(
                _detail_page(
                    'Maniac Magee',
                    'by Jerry Spinelli, and published by Little, Brown',
                    'Starr LaTronica praised the book.',
                )
            ),
            'Jerry Spinelli',
        )
        self.assertEqual(
            _parse_detail_author(
                _detail_page(
                    'Crispin: The Cross of Lead',
                    'by Avi, and published by Hyperion',
                    'Starr LaTronica, chair of the committee, spoke.',
                )
            ),
            'Avi',
        )
        self.assertEqual(
            _parse_detail_author(
                _detail_page(
                    'The Last Cuentista',
                    '"The Last Cuentista" written by Donna Higuera. '
                    'Published by Levine Querido.',
                    'Donna is mentioned again in a review quote.',
                )
            ),
            'Donna Higuera',
        )

    def test_missing_subtitle_does_not_use_body_names(self):
        html = _load_fixture('detail_missing_author.html')
        self.assertIsNone(_parse_detail_author(html))

    def test_about_paragraph_is_not_a_fallback_author(self):
        html = _detail_page(
            'Freewater',
            None,
            'Written by a committee chair, Starr LaTronica praised the novel.',
        )
        self.assertIsNone(_parse_detail_author(html))


if __name__ == '__main__':
    unittest.main()
