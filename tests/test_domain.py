from unittest import TestCase

from amanuensis.domain import Evidence, MediaKind, StageState, StagedItem, TransitionError


class StagingWorkflowTests(TestCase):
    def test_happy_path_reaches_imported(self):
        item = StagedItem("request-1", "Example", MediaKind.BOOK)
        for state in (
            StageState.ACQUIRING,
            StageState.ACQUIRED,
            StageState.IDENTIFYING,
            StageState.READY_TO_IMPORT,
            StageState.IMPORTING,
            StageState.IMPORTED,
        ):
            item = item.transition(state)
        self.assertEqual(StageState.IMPORTED, item.state)

    def test_retry_returns_to_end_of_queue_state(self):
        item = StagedItem("request-2", "Example", MediaKind.BOOK)
        item = item.transition(StageState.ACQUIRING)
        item = item.transition(StageState.FAILED_RETRYABLE)
        item = item.transition(StageState.QUEUED)
        self.assertEqual(StageState.QUEUED, item.state)

    def test_unverified_item_cannot_skip_identification(self):
        item = StagedItem("request-3", "Example", MediaKind.PERIODICAL_ISSUE)
        with self.assertRaises(TransitionError):
            item.transition(StageState.READY_TO_IMPORT)

    def test_evidence_confidence_is_bounded(self):
        with self.assertRaises(ValueError):
            Evidence("fixture", "title", 1.1)

    def test_periodical_issue_does_not_require_numeric_issue(self):
        item = StagedItem(
            "request-4",
            "Special issue",
            MediaKind.PERIODICAL_ISSUE,
            series="Example Review",
        )
        self.assertIsNone(item.issue)
