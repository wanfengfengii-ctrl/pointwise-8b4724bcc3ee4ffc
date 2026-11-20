import json
import tempfile
import unittest
from pathlib import Path

from plans.freeze import freeze_plan
from reports.storage import open_archive
from source.intake import receive
from source.revisions import Station, TransferCount
from source.storage import open_source


SAMPLE_DIR = Path(__file__).resolve().parents[1] / 'samples'


def sample(name):
    for filename in ('shift.json', 'boundaries.json'):
        cases = json.loads((SAMPLE_DIR / filename).read_text(encoding='utf-8'))
        if name in cases:
            return cases[name]
    raise KeyError(name)


def receive_sample(source, data):
    return receive(
        source, data['batch'], [Station(*row) for row in data['stations']],
        data['release'], data['reject'], [TransferCount(*row) for row in data['counts']],
    )


class DatabaseCase(unittest.TestCase):
    def setUp(self):
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.source_path = directory / 'source.sqlite3'
        self.archive_path = directory / 'archive.sqlite3'
        self.source = self._open(open_source, self.source_path)
        self.archive = self._open(open_archive, self.archive_path)

    def _open(self, opener, path):
        connection = opener(path)
        self.addCleanup(connection.close)
        return connection

    def reopen_source(self):
        self.source.close()
        self.source = self._open(open_source, self.source_path)

    def reopen_archive(self):
        self.archive.close()
        self.archive = self._open(open_archive, self.archive_path)

    def freeze(self, name):
        revision = receive_sample(self.source, sample(name))
        return freeze_plan(self.source, self.archive, revision)

    def revision_ids(self):
        return [row[0] for row in self.source.execute('SELECT revision_id FROM revisions ORDER BY revision_id')]
