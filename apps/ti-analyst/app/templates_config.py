from pathlib import Path

from fastapi.templating import Jinja2Templates

# Templates are in the same package directory as this file
_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
