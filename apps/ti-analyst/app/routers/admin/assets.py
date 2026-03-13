import csv
import io
import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import Asset
from app.services.opensearch_client import OpenSearchClient
from app.templates_config import templates

router = APIRouter(prefix="/admin/assets", tags=["admin-assets"])
# Security: all /admin/* routes are protected by Traefik edge-auth middleware
# (compose.agent-ti-analyst.yaml → traefik.http.routers.ti-analyst-agent.middlewares=edge-auth@docker).
# Application-level auth is intentionally absent — auth is enforced at the infrastructure layer.
logger = logging.getLogger(__name__)

CRITICALITY_OPTIONS = ["low", "medium", "high", "critical"]


@router.get("", response_class=HTMLResponse)
def list_assets(request: Request, db: Annotated[Session, Depends(get_db)]):
    assets = db.query(Asset).order_by(Asset.criticality.desc(), Asset.vendor).all()
    return templates.TemplateResponse(
        request, "admin/assets.html", {"assets": assets, "criticality_options": CRITICALITY_OPTIONS}
    )


@router.post("/create")
def create_asset(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    name: str = Form(...),
    vendor: str = Form(...),
    model: str = Form(...),
    software_version: str = Form(""),
    criticality: str = Form("medium"),
    tags: str = Form(""),
    notes: str = Form(""),
):
    asset = Asset(
        name=name,
        vendor=vendor,
        model=model,
        software_version=software_version or None,
        criticality=criticality,
        tags=tags or None,
        notes=notes or None,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    try:
        os_client = OpenSearchClient()
        os_client.ensure_indices()
        os_client.index_asset(str(asset.id), {
            "name": asset.name, "vendor": asset.vendor, "model": asset.model,
            "software_version": asset.software_version, "criticality": asset.criticality,
            "created_at": asset.created_at.isoformat(),
        })
    except Exception as exc:
        logger.warning("OpenSearch asset index failed: %s", exc)
    return RedirectResponse("/admin/assets", status_code=303)


@router.post("/import-csv")
async def import_csv(db: Annotated[Session, Depends(get_db)], file: UploadFile = File(...)):
    """Import assets from CSV. Expected columns: name,vendor,model,software_version,criticality"""
    content = await file.read()
    reader = csv.DictReader(io.StringIO(content.decode("utf-8")))
    imported = 0
    os_client = OpenSearchClient()
    for row in reader:
        asset = Asset(
            name=row.get("name", ""),
            vendor=row.get("vendor", ""),
            model=row.get("model", ""),
            software_version=row.get("software_version") or None,
            criticality=row.get("criticality", "medium"),
        )
        db.add(asset)
        db.flush()
        try:
            os_client.index_asset(str(asset.id), {
                "name": asset.name, "vendor": asset.vendor, "model": asset.model,
                "software_version": asset.software_version, "criticality": asset.criticality,
            })
        except Exception:
            pass
        imported += 1
    db.commit()
    return RedirectResponse(f"/admin/assets?imported={imported}", status_code=303)


@router.post("/{asset_id}/update")
def update_asset(
    asset_id: str,
    db: Annotated[Session, Depends(get_db)],
    name: str = Form(...),
    vendor: str = Form(...),
    model: str = Form(...),
    software_version: str = Form(""),
    criticality: str = Form("medium"),
    tags: str = Form(""),
    notes: str = Form(""),
):
    asset = db.query(Asset).filter(Asset.id == uuid.UUID(asset_id)).first()
    if asset:
        asset.name = name
        asset.vendor = vendor
        asset.model = model
        asset.software_version = software_version or None
        asset.criticality = criticality
        asset.tags = tags or None
        asset.notes = notes or None
        db.commit()
        db.refresh(asset)
        try:
            os_client = OpenSearchClient()
            os_client.index_asset(str(asset.id), {
                "name": asset.name, "vendor": asset.vendor, "model": asset.model,
                "software_version": asset.software_version, "criticality": asset.criticality,
                "tags": asset.tags, "created_at": asset.created_at.isoformat(),
            })
        except Exception as exc:
            logger.warning("OpenSearch asset re-index failed: %s", exc)
    return RedirectResponse("/admin/assets", status_code=303)


@router.post("/{asset_id}/delete")
def delete_asset(asset_id: str, db: Annotated[Session, Depends(get_db)]):
    asset = db.query(Asset).filter(Asset.id == uuid.UUID(asset_id)).first()
    if asset:
        try:
            os_client = OpenSearchClient()
            os_client._request("DELETE", f"ti_analyst_assets/_doc/{asset_id}")
        except Exception as exc:
            logger.warning("OpenSearch asset delete failed: %s", exc)
        db.delete(asset)
        db.commit()
    return RedirectResponse("/admin/assets", status_code=303)
