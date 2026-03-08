import uuid

from app.database import SessionLocal
from app.models.models import CuratedNewsItem, NewsSource, RawNewsItem


def test_delete_source_removes_related_items(client) -> None:
    source_name = f"Delete Source {uuid.uuid4().hex[:8]}"

    with SessionLocal() as db:
        source = NewsSource(
            name=source_name,
            base_url="https://example.com/source",
            topic_scope="ai",
            crawl_priority=5,
        )
        db.add(source)
        db.flush()

        raw_item = RawNewsItem(
            source_id=source.id,
            source_url="https://example.com/source/article",
            canonical_url="https://example.com/source/article",
            title="Test article",
            raw_text="Test article body",
            excerpt="Test article excerpt",
            status="selected",
            dedup_hash=f"dedup-{uuid.uuid4().hex}",
        )
        db.add(raw_item)
        db.flush()

        curated_item = CuratedNewsItem(
            raw_news_item_id=raw_item.id,
            title="Curated title",
            summary="Curated summary",
            body="Curated body",
            status="ready",
        )
        db.add(curated_item)
        db.commit()

        source_id = source.id
        raw_item_id = raw_item.id
        curated_item_id = curated_item.id

    response = client.post(f"/admin/sources/{source_id}/delete", follow_redirects=False)
    assert response.status_code == 303

    with SessionLocal() as db:
        assert db.query(NewsSource).filter(NewsSource.id == source_id).first() is None
        assert db.query(RawNewsItem).filter(RawNewsItem.id == raw_item_id).first() is None
        assert db.query(CuratedNewsItem).filter(CuratedNewsItem.id == curated_item_id).first() is None
