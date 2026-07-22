from unittest import TestCase

from amanuensis.search import (
    Passage,
    PassageQuery,
    ResultOrder,
    SearchHit,
    SearchScope,
    SourceUnit,
    assemble_passages,
)


class PassageSearchContractTests(TestCase):
    def setUp(self):
        self.text = (
            "Le premier paragraphe parle des villes flottantes.\n\n"
            "Le second explique comment elles conservent leur energie solaire.\n\n"
            "Un autre chapitre traite seulement des forets."
        )
        self.unit = SourceUnit("book-1", "chapter-3", 3, "Chapitre 3", self.text)
        self.units = {("book-1", "chapter-3"): self.unit}

    def test_search_requires_an_explicit_book_scope(self):
        with self.assertRaises(ValueError):
            SearchScope(frozenset())

    def test_nearby_hits_are_assembled_from_the_exact_source(self):
        first_start = self.text.index("villes")
        first_end = self.text.index(".\n\n") + 1
        second_start = self.text.index("Le second")
        second_end = self.text.index("solaire") + len("solaire")
        query = PassageQuery("comment vivent les villes flottantes", SearchScope(frozenset({"book-1"})))
        hits = [
            SearchHit(
                Passage("p-1", "book-1", "chapter-3", 1, first_start, first_end),
                0.82,
                ("lexical",),
            ),
            SearchHit(
                Passage("p-2", "book-1", "chapter-3", 2, second_start, second_end),
                0.91,
                ("semantic",),
            ),
        ]

        excerpts = assemble_passages(query, hits, self.units, merge_gap_chars=20)

        self.assertEqual(1, len(excerpts))
        excerpt = excerpts[0]
        self.assertEqual(self.text[first_start:second_end], excerpt.text)
        self.assertEqual(("p-1", "p-2"), excerpt.passage_ids)
        self.assertEqual(("lexical", "semantic"), excerpt.channels)

    def test_distant_hits_remain_separate_verbatim_excerpts(self):
        first_start = self.text.index("villes")
        first_end = first_start + len("villes flottantes")
        last_start = self.text.index("forets")
        last_end = last_start + len("forets")
        query = PassageQuery("environnement", SearchScope(frozenset({"book-1"})))
        hits = [
            SearchHit(
                Passage("p-1", "book-1", "chapter-3", 1, first_start, first_end),
                0.7,
            ),
            SearchHit(
                Passage("p-2", "book-1", "chapter-3", 2, last_start, last_end),
                0.8,
            ),
        ]

        excerpts = assemble_passages(query, hits, self.units, merge_gap_chars=5)

        self.assertEqual(["forets", "villes flottantes"], [item.text for item in excerpts])

    def test_reading_order_is_available_without_changing_text(self):
        first = self.text.index("villes")
        last = self.text.index("forets")
        query = PassageQuery(
            "environnement",
            SearchScope(frozenset({"book-1"})),
            order=ResultOrder.READING,
        )
        hits = [
            SearchHit(Passage("late", "book-1", "chapter-3", 2, last, last + 6), 1.0),
            SearchHit(Passage("early", "book-1", "chapter-3", 1, first, first + 6), 0.5),
        ]

        excerpts = assemble_passages(query, hits, self.units, merge_gap_chars=0)

        self.assertEqual(["villes", "forets"], [item.text for item in excerpts])

    def test_backend_cannot_leak_a_book_outside_the_selected_corpus(self):
        query = PassageQuery("secret", SearchScope(frozenset({"book-1"})))
        other = SourceUnit("book-2", "chapter-1", 1, "Chapitre 1", "Un secret.")
        hit = SearchHit(Passage("p-x", "book-2", "chapter-1", 1, 3, 9), 1.0)

        with self.assertRaisesRegex(ValueError, "out-of-scope"):
            assemble_passages(
                query,
                [hit],
                {("book-2", "chapter-1"): other},
            )
