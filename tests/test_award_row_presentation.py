"""Execute the shared production row presentation with offline widget doubles."""
import unittest
from dataclasses import replace
from awards import engine
from awards.formatter import DEFAULT_AWARD_OUTPUT_TEMPLATE,format_award_result
from awards.model import AwardResult
from tests.test_six_issue_reliability import render_actual_match_row,render_actual_dialog

class AwardRowPresentationTests(unittest.TestCase):
    def result(self,**changes):
        data=dict(work_title='A Book',work_author='An Author',award_name='CWA Gold Dagger',
                  award_year=2026,category=None,status='Winner',rank=None,
                  source_name='Official source',source_url='https://thecwa.co.uk/past-winners/a-book/',
                  source_details=('Main award only.',))
        data.update(changes)
        return AwardResult(**data)

    def test_ordinary_winner_has_no_explanatory_paragraphs_but_keeps_tooltip(self):
        result=self.result()
        assessment=engine.assess_award_result(result)
        labels,box=render_actual_match_row(assessment,'English Book','An Author')
        self.assertEqual(labels,[])
        tooltip=box.setToolTip.call_args.args[0]
        for text in ['Official source',result.source_url,'Source: A Book | An Author',
                     'Main award only.',assessment.qualification.reason,'QUALIFIES']:
            self.assertIn(text,tooltip)
        box.setChecked.assert_called_once_with(True)
        self.assertEqual(format_award_result(result,DEFAULT_AWARD_OUTPUT_TEMPLATE),'Winner - 2026 CWA Gold Dagger')

    def test_review_keeps_label_and_unchecked_default_without_reason_paragraph(self):
        assessment=engine.assess_award_result(self.result(status='Shortlisted'))
        labels,box=render_actual_match_row(assessment,'A Book','An Author')
        self.assertEqual(labels,['REVIEW'])
        self.assertIn(assessment.qualification.reason,box.setToolTip.call_args.args[0])
        box.setChecked.assert_called_once_with(False)

    def test_identity_warning_is_visible_once_and_in_tooltip(self):
        result=self.result(identity_confirmation_required=True,source_identity_note='Confirm the awarded volume.')
        labels,box=render_actual_match_row(engine.assess_award_result(result),'A Book','An Author')
        warnings=[text for text in labels if 'IDENTITY CONFIRMATION REQUIRED' in text]
        self.assertEqual(len(warnings),1)
        self.assertIn('Confirm the awarded volume.',warnings[0])
        self.assertIn(warnings[0],box.setToolTip.call_args.args[0])
        box.setChecked.assert_called_once_with(False)

    def test_author_scope_and_source_details_are_tooltip_only(self):
        result=self.result(identity_kind='author',is_specifically_cited_work=True)
        labels,box=render_actual_match_row(engine.assess_award_result(result),'Different Book','An Author')
        self.assertEqual(labels,[])
        tooltip=box.setToolTip.call_args.args[0]
        self.assertIn('AUTHOR AWARD',tooltip)
        self.assertIn('explicitly cited',tooltip)

    def test_actual_source_failures_remain_visible_in_empty_dialog(self):
        report=engine.AwardLookupReport((),(engine.SourceFailure('Official source','Unavailable','Retrieval failed.'),))
        labels,_=render_actual_dialog(report)
        self.assertTrue(any('Retrieval failed.' in text for text in labels))

if __name__=='__main__': unittest.main()
