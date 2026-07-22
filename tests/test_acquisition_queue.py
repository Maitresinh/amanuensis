from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from amanuensis.acquisition import CandidateIntent, CatalogueQuery, RetryableProviderError, SearchPage
from amanuensis.queue import AcquisitionState, SQLiteAcquisitionQueue
from amanuensis.workflow import AcquisitionCoordinator, RetryPolicy


class AlwaysUnavailableAdapter:
    def search(self, query):
        if "first" in query.text:
            raise RetryableProviderError("temporary outage")
        return SearchPage(())


class DurableQueueTests(TestCase):
    def test_retry_is_moved_behind_existing_work(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            repository = SQLiteAcquisitionQueue(root / "queue.db")
            first = repository.create(CatalogueQuery("first"), CandidateIntent("First"))
            second = repository.create(CatalogueQuery("second"), CandidateIntent("Second"))
            coordinator = AcquisitionCoordinator(
                repository,
                AlwaysUnavailableAdapter(),
                root / "staging",
                retry_policy=RetryPolicy(maximum_attempts=3, base_delay_seconds=0),
            )

            failed = coordinator.process_next()
            next_item = repository.next_due()

            self.assertEqual(first.identifier, failed.identifier)
            self.assertEqual(AcquisitionState.FAILED_RETRYABLE, failed.state)
            self.assertEqual(second.identifier, next_item.identifier)
            self.assertGreater(failed.queued_sequence, second.queued_sequence)

    def test_queue_and_history_survive_repository_reopen(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "queue.db"
            created = SQLiteAcquisitionQueue(path).create(
                CatalogueQuery("Dune"), CandidateIntent("Dune", ("Frank Herbert",))
            )

            reopened = SQLiteAcquisitionQueue(path)
            loaded = reopened.get(created.identifier)

            self.assertEqual(created.intent, loaded.intent)
            self.assertEqual("request_created", reopened.events(created.identifier)[0]["event"])
