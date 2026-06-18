from types import SimpleNamespace
from threading import RLock

import pytest

from src.database.weavservice import (
    ImportBatchError,
    PreparedImportRow,
    WeaviateService,
)
from src.pipeline.pipeline import ImportPipeline
from src.pipeline.utils import ProcessingResult
from src.scraping.types import ScrapeManifest


class FakeData:
    def __init__(self, state, lang):
        self.state = state
        self.lang = lang

    def delete_by_id(self, object_uuid):
        self.state[self.lang].pop(str(object_uuid), None)
        return True


def _reconciliation_service(initial_state):
    service = object.__new__(WeaviateService)
    service._last_query_time = 0
    state = {
        lang: dict(objects)
        for lang, objects in initial_state.items()
    }

    def prepare(rows, lang):
        return [
            PreparedImportRow(
                uuid=row["uuid"],
                properties=row,
                vector={"test": [1.0]},
            )
            for row in rows
        ]

    def collect(lang, source):
        return {
            object_uuid: properties
            for object_uuid, properties in state[lang].items()
            if properties.get("source") == source
        }

    def write(rows, lang):
        for row in rows:
            state[lang][row.uuid] = row.properties

    service.prepare_batch_import = prepare
    service._collect_source_objects = collect
    service._write_prepared_rows = write
    service._select_collection = lambda lang: (
        SimpleNamespace(data=FakeData(state, lang)),
        f"collection_{lang}",
    )
    return service, state


def test_collect_source_objects_uses_offset_with_filters():
    source = "https://example.test/page"
    pages = [
        [
            SimpleNamespace(
                uuid=f"uuid-{index}",
                properties={"source": source, "chunk_id": str(index)},
            )
            for index in range(start, min(start + 100, 205))
        ]
        for start in (0, 100, 200)
    ]
    calls = []

    def fetch_objects(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(objects=pages[kwargs["offset"] // 100])

    service = object.__new__(WeaviateService)
    service._client_lock = RLock()
    service._select_collection = lambda lang: (
        SimpleNamespace(query=SimpleNamespace(fetch_objects=fetch_objects)),
        "test_collection",
    )

    objects = service._collect_source_objects("en", source)

    assert len(objects) == 205
    assert [call["offset"] for call in calls] == [0, 100, 200]
    assert all("after" not in call for call in calls)
    assert all(call["filters"] is not None for call in calls)


def test_reconcile_migrates_legacy_uuid_and_language():
    source = "https://example.test/page"
    service, state = _reconciliation_service({
        "en": {"legacy-random": {"source": source}},
        "de": {},
    })

    summary = service.reconcile_source(
        source,
        {
            "en": [],
            "de": [{"uuid": "deterministic-new", "source": source}],
        },
    )

    assert state["en"] == {}
    assert set(state["de"]) == {"deterministic-new"}
    assert summary.inserted == 1
    assert summary.deleted == 1


def test_reconcile_zero_chunks_removes_old_source():
    source = "https://example.test/removed"
    service, state = _reconciliation_service({
        "en": {"old": {"source": source}},
        "de": {},
    })

    service.reconcile_source(source, {"en": [], "de": []})

    assert state == {"en": {}, "de": {}}


def test_reconcile_insert_failure_preserves_old_objects():
    source = "https://example.test/page"
    service, state = _reconciliation_service({
        "en": {"old": {"source": source}},
        "de": {},
    })
    service._write_prepared_rows = lambda rows, lang: (
        (_ for _ in ()).throw(ImportBatchError("embedding or insert failed"))
        if rows else None
    )

    with pytest.raises(ImportBatchError):
        service.reconcile_source(
            source,
            {"en": [{"uuid": "new", "source": source}], "de": []},
        )

    assert set(state["en"]) == {"old"}


def test_reconcile_verification_failure_prevents_cleanup():
    source = "https://example.test/page"
    service, state = _reconciliation_service({
        "en": {"old": {"source": source}},
        "de": {},
    })
    service._write_prepared_rows = lambda rows, lang: None

    with pytest.raises(ImportBatchError, match="Verification failed"):
        service.reconcile_source(
            source,
            {"en": [{"uuid": "missing", "source": source}], "de": []},
        )

    assert set(state["en"]) == {"old"}


def test_reconcile_retries_after_partial_insert_without_duplicates():
    source = "https://example.test/page"
    service, state = _reconciliation_service({
        "en": {"old": {"source": source}},
        "de": {},
    })
    normal_write = service._write_prepared_rows
    failed_once = False

    def partial_write(rows, lang):
        nonlocal failed_once
        if rows and not failed_once:
            failed_once = True
            normal_write(rows[:1], lang)
            raise ImportBatchError("connection dropped after a partial insert")
        normal_write(rows, lang)

    service._write_prepared_rows = partial_write
    rows = {
        "en": [
            {"uuid": "new-1", "source": source},
            {"uuid": "new-2", "source": source},
        ],
        "de": [],
    }

    with pytest.raises(ImportBatchError):
        service.reconcile_source(source, rows)

    summary = service.reconcile_source(source, rows)

    assert set(state["en"]) == {"new-1", "new-2"}
    assert summary.inserted == 1
    assert summary.retained == 1


def test_reconcile_retries_after_cleanup_failure():
    source = "https://example.test/page"
    service, state = _reconciliation_service({
        "en": {"old": {"source": source}},
        "de": {},
    })

    class FailOnceData(FakeData):
        failed = False

        def delete_by_id(self, object_uuid):
            if not self.failed:
                self.failed = True
                raise RuntimeError("delete connection dropped")
            return super().delete_by_id(object_uuid)

    failing_data = FailOnceData(state, "en")
    service._select_collection = lambda lang: (
        SimpleNamespace(data=failing_data if lang == "en" else FakeData(state, lang)),
        f"collection_{lang}",
    )
    rows = {"en": [{"uuid": "new", "source": source}], "de": []}

    with pytest.raises(RuntimeError, match="delete connection dropped"):
        service.reconcile_source(source, rows)

    assert set(state["en"]) == {"old", "new"}

    summary = service.reconcile_source(source, rows)

    assert set(state["en"]) == {"new"}
    assert summary.retained == 1
    assert summary.inserted == 0


class AlwaysFailBatchContext:
    number_errors = 1

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def add_object(self, **kwargs):
        pass


class AlwaysFailBatch:
    def __init__(self):
        self.failed_objects = []

    def fixed_size(self, **kwargs):
        return AlwaysFailBatchContext()


class FailedObjectBatchContext:
    number_errors = 0

    def __init__(self, owner):
        self.owner = owner

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.owner.failed_objects.append("server rejected object")
        return False

    def add_object(self, **kwargs):
        pass


class FailedObjectBatch:
    def __init__(self):
        self.failed_objects = []

    def fixed_size(self, **kwargs):
        return FailedObjectBatchContext(self)


def test_strict_batch_raises_on_asynchronous_errors(monkeypatch):
    service = object.__new__(WeaviateService)
    service._client_lock = RLock()
    service._last_query_time = 0
    service._select_collection = lambda lang: (
        SimpleNamespace(batch=AlwaysFailBatch()),
        "test_collection",
    )
    monkeypatch.setattr("src.database.weavservice.sleep", lambda _: None)

    with pytest.raises(ImportBatchError):
        service._write_prepared_rows(
            [
                PreparedImportRow(
                    uuid="68cda09a-5466-5f23-a595-3e9575af4102",
                    properties={"source": "source", "chunk_id": "chunk"},
                    vector={"test": [1.0]},
                )
            ],
            "en",
        )


def test_strict_batch_checks_failed_objects(monkeypatch):
    service = object.__new__(WeaviateService)
    service._client_lock = RLock()
    service._last_query_time = 0
    service._select_collection = lambda lang: (
        SimpleNamespace(batch=FailedObjectBatch()),
        "test_collection",
    )
    monkeypatch.setattr("src.database.weavservice.sleep", lambda _: None)

    with pytest.raises(ImportBatchError, match="server rejected object"):
        service._write_prepared_rows(
            [
                PreparedImportRow(
                    uuid="68cda09a-5466-5f23-a595-3e9575af4102",
                    properties={"source": "source", "chunk_id": "chunk"},
                    vector={"test": [1.0]},
                )
            ],
            "en",
        )


def test_scraper_manifest_reconciles_empty_languages():
    pipeline = object.__new__(ImportPipeline)
    calls = []
    pipeline._service = SimpleNamespace(
        reconcile_source=lambda source, rows: calls.append((source, rows))
    )
    manifest = ScrapeManifest(
        target_url="https://example.test",
        chunks_by_language={"de": []},
        processed_sources=["https://example.test/empty"],
    )

    pipeline.import_from_scraper(manifest)

    source, rows = calls[0]
    assert source == "https://example.test/empty"
    assert rows == {"en": [], "de": []}


def test_cli_local_import_replaces_existing_source():
    pipeline = object.__new__(ImportPipeline)
    calls = []
    pipeline._deduplication_callback = None
    pipeline._service = SimpleNamespace(
        source_object_count=lambda source: 2,
        reconcile_source=lambda source, rows: calls.append(("replace", source, rows)),
        batch_import=lambda rows, lang: calls.append(("append", lang, rows)),
    )
    result = ProcessingResult(
        chunks=[{"source": "document.pdf", "chunk_id": "new"}],
        source="document.pdf",
        lang="en",
    )

    pipeline._import_document_result(result)

    assert calls[0][0] == "replace"
    assert calls[0][2]["en"] == result.chunks
    assert calls[0][2]["de"] == []
