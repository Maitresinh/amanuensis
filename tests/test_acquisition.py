from unittest import TestCase

from amanuensis.acquisition import (
    CandidateIntent,
    SearchCandidate,
    assess_candidate,
    select_candidate,
)


class CandidateSelectionTests(TestCase):
    def test_selects_bibliographic_match_instead_of_first_result(self):
        wrong = SearchCandidate(
            "1" * 32,
            "Les Voyageurs immobiles",
            ("Paul Example",),
            language="en",
            format="pdf",
        )
        correct = SearchCandidate(
            "2" * 32,
            "Les Voyageurs - integrale",
            ("Becky Chambers",),
            language="fr",
            format="epub",
        )
        intent = CandidateIntent("Les Voyageurs", ("Becky Chambers",))

        selection = select_candidate(intent, [wrong, correct])

        self.assertEqual(correct, selection.selected)
        self.assertGreater(
            assess_candidate(intent, correct).score,
            assess_candidate(intent, wrong).score,
        )

    def test_rejects_weak_match(self):
        candidate = SearchCandidate("3" * 32, "A completely unrelated book", ("Other",))
        selection = select_candidate(CandidateIntent("Dune", ("Frank Herbert",)), [candidate])
        self.assertIsNone(selection.selected)
        self.assertIn("threshold", selection.reason)

    def test_source_allowlist_is_enforced(self):
        candidate = SearchCandidate("4" * 32, "Dune", ("Frank Herbert",), source="unknown")
        selection = select_candidate(
            CandidateIntent("Dune", ("Frank Herbert",), allowed_sources=("approved",)),
            [candidate],
        )
        self.assertIsNone(selection.selected)
        self.assertTrue(selection.assessments[0].rejected)

    def test_non_latin_subtitle_is_not_discarded_during_scoring(self):
        intent = CandidateIntent("Candide", ("Voltaire",))
        exact = SearchCandidate("5" * 32, "Candide", ("Voltaire",), language="fr", format="epub")
        translated = SearchCandidate(
            "6" * 32,
            "Candide (\u6cd5\u6587\u7248)",
            ("Voltaire",),
            language="fr",
            format="epub",
        )

        self.assertGreater(
            assess_candidate(intent, exact).score,
            assess_candidate(intent, translated).score,
        )
