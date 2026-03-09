from fastapi import APIRouter

from app.config import settings

router = APIRouter()


@router.get("/api/v1/manifest")
def get_manifest() -> dict:
    return {
        "name": "ti-analyst",
        "version": "0.1.0",
        "description": "Sentinel-AI: Cyber Threat Intelligence analysis and infrastructure risk correlation",
        "url": "http://ti-analyst-agent:8000/api/v1/a2a",
        "provider": {
            "organization": "AI Community Platform",
            "url": "https://github.com/nmdimas/ai-community-platform",
        },
        "capabilities": {"streaming": False, "pushNotifications": True},
        "defaultInputModes": ["text"],
        "defaultOutputModes": ["text"],
        "skills": [
            {
                "id": "ti.analyze",
                "name": "Threat Analysis",
                "description": "Analyze a text snippet for cyber threat intelligence",
                "tags": ["security", "cti", "threat-intel"],
            },
            {
                "id": "ti.inventory",
                "name": "Asset Inventory",
                "description": "Manage infrastructure asset inventory for threat correlation",
                "tags": ["security", "assets", "inventory"],
            },
            {
                "id": "ti.report",
                "name": "Threat Report",
                "description": "Retrieve generated threat intelligence reports",
                "tags": ["security", "reporting"],
            },
        ],
        "health_url": "http://ti-analyst-agent:8000/health",
        "admin_url": settings.admin_public_url,
        "storage": {
            "postgres": {
                "db_name": "ti_analyst",
                "user": "ti_analyst",
                "startup_migration": {
                    "enabled": True,
                    "mode": "best_effort",
                    "command": "alembic upgrade head || true",
                },
            },
            "opensearch": {
                "collections": ["ti_analyst_assets", "ti_analyst_threats"],
            },
        },
    }
