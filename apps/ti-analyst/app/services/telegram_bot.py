"""Interactive Telegram bot for CTI queries.

Commands (authorized users only):
  /start   — show user ID (no auth required, for initial setup)
  /threats [n] — last N threats (default 5)
  /latest  — most recent threat with full details
  /search <query> — search by CVE ID or keyword in title

Natural language messages are answered via LLM with recent threats as context.
"""
import asyncio
import logging
import threading

logger = logging.getLogger(__name__)

_loop: asyncio.AbstractEventLoop | None = None
_stop_event: asyncio.Event | None = None
_bot_thread: threading.Thread | None = None

_SEV_EMOJI = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}


# ── Authorization ──────────────────────────────────────────────────────────────

def _get_allowed_ids() -> set[int]:
    """Return allowed Telegram user IDs from DB + env fallback."""
    from app.config import settings
    from app.database import SessionLocal
    from app.models.models import AgentSettings

    allowed: set[int] = set()

    # Env fallback
    for raw in settings.telegram_bot_allowed_ids.split(","):
        raw = raw.strip()
        if raw.lstrip("-").isdigit():
            allowed.add(int(raw))

    # DB (takes precedence / merges)
    try:
        db = SessionLocal()
        try:
            s = db.query(AgentSettings).first()
            if s and s.bot_allowed_user_ids:
                for raw in s.bot_allowed_user_ids.split(","):
                    raw = raw.strip()
                    if raw.lstrip("-").isdigit():
                        allowed.add(int(raw))
        finally:
            db.close()
    except Exception:
        logger.exception("Failed to load bot_allowed_user_ids from DB")

    return allowed


def _is_authorized(user_id: int) -> bool:
    allowed = _get_allowed_ids()
    return bool(allowed) and user_id in allowed


# ── DB helpers ─────────────────────────────────────────────────────────────────

def _get_recent_threats(limit: int = 5) -> list:
    from app.database import SessionLocal
    from app.models.models import ThreatIntel

    db = SessionLocal()
    try:
        return (
            db.query(ThreatIntel)
            .filter(ThreatIntel.status != "error")
            .order_by(ThreatIntel.created_at.desc())
            .limit(limit)
            .all()
        )
    finally:
        db.close()


def _get_assets() -> list:
    from app.database import SessionLocal
    from app.models.models import Asset

    db = SessionLocal()
    try:
        return db.query(Asset).order_by(Asset.criticality.desc(), Asset.name).all()
    finally:
        db.close()


def _search_threats(query: str) -> list:
    from app.database import SessionLocal
    from app.models.models import ThreatIntel

    db = SessionLocal()
    try:
        q = query.strip()
        return (
            db.query(ThreatIntel)
            .filter(
                ThreatIntel.cve_ids.ilike(f"%{q}%")
                | ThreatIntel.title.ilike(f"%{q}%")
                | ThreatIntel.threat_type.ilike(f"%{q}%")
            )
            .order_by(ThreatIntel.created_at.desc())
            .limit(5)
            .all()
        )
    finally:
        db.close()


# ── Formatting ─────────────────────────────────────────────────────────────────

def _fmt_short(t) -> str:
    emoji = _SEV_EMOJI.get(t.severity or "", "⚪")
    return f"{emoji} {t.title or 'No title'} — `{t.severity or '?'}`"


def _fmt_full(t) -> str:
    emoji = _SEV_EMOJI.get(t.severity or "", "⚪")
    lines = [f"{emoji} *{t.title or 'No title'}*"]
    if t.severity:
        lines.append(f"Severity: `{t.severity}`")
    if t.threat_type:
        lines.append(f"Type: `{t.threat_type}`")
    if t.cve_ids:
        lines.append(f"CVEs: `{t.cve_ids}`")
    if t.exec_report:
        lines.append(f"\n_{t.exec_report[:600].strip()}_")
    if t.source_url:
        lines.append(f"\n[Source]({t.source_url})")
    return "\n".join(lines)


# ── LLM ───────────────────────────────────────────────────────────────────────

async def _ask_llm(question: str, threats: list, assets: list | None = None) -> str:
    import httpx

    from app.config import settings
    from app.database import SessionLocal
    from app.models.models import AgentSettings

    db = SessionLocal()
    try:
        s = db.query(AgentSettings).first()
        model = s.analyst_model if s else settings.analyst_model
    finally:
        db.close()

    threat_parts = []
    for t in threats:
        parts = [f"Title: {t.title}", f"Severity: {t.severity}", f"Type: {t.threat_type}"]
        if t.cve_ids:
            parts.append(f"CVEs: {t.cve_ids}")
        if t.exec_report:
            parts.append(f"Summary: {t.exec_report[:400]}")
        threat_parts.append("\n".join(parts))

    threats_context = "\n\n---\n\n".join(threat_parts) or "No threats in database yet."

    assets_context = ""
    if assets:
        asset_lines = [
            f"- {a.name} | {a.vendor} {a.model} | criticality={a.criticality}"
            + (f" | tags={a.tags}" if a.tags else "")
            for a in assets
        ]
        assets_context = "\n=== Monitored Assets ===\n" + "\n".join(asset_lines)

    prompt = (
        "You are a CTI analyst assistant. Answer the user's question based on the threat intelligence and asset data below.\n"
        "Be concise (3–5 sentences max). Reply in the same language as the question.\n\n"
        f"=== Recent Threats ===\n{threats_context}\n"
        f"{assets_context}\n\n"
        f"=== Question ===\n{question}"
    )

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{settings.litellm_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.litellm_api_key}"},
            json={"model": model, "messages": [{"role": "user", "content": prompt}]},
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()


# ── Handlers ───────────────────────────────────────────────────────────────────

async def _handle_start(update, context):
    user = update.effective_user
    await update.message.reply_text(
        f"👋 Your Telegram user ID: `{user.id}`\n\n"
        "Ask the admin to add it to *Bot Allowed User IDs* in ti-analyst Admin → Settings.",
        parse_mode="Markdown",
    )


async def _auth_check(update) -> bool:
    if not _is_authorized(update.effective_user.id):
        await update.message.reply_text("⛔ Not authorized.")
        return False
    return True


async def _handle_threats(update, context):
    if not await _auth_check(update):
        return
    args = context.args
    limit = 5
    if args and args[0].isdigit():
        limit = min(int(args[0]), 20)
    threats = _get_recent_threats(limit)
    if not threats:
        await update.message.reply_text("No threats in database yet.")
        return
    lines = [f"📋 *Last {len(threats)} threats:*\n"]
    lines += [_fmt_short(t) for t in threats]
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def _handle_latest(update, context):
    if not await _auth_check(update):
        return
    threats = _get_recent_threats(1)
    if not threats:
        await update.message.reply_text("No threats in database yet.")
        return
    await update.message.reply_text(_fmt_full(threats[0]), parse_mode="Markdown")


async def _handle_search(update, context):
    if not await _auth_check(update):
        return
    query = " ".join(context.args) if context.args else ""
    if not query:
        await update.message.reply_text("Usage: `/search CVE-2025-1234` or `/search juniper`", parse_mode="Markdown")
        return
    threats = _search_threats(query)
    if not threats:
        await update.message.reply_text(f"No threats found for `{query}`.", parse_mode="Markdown")
        return
    lines = [f"🔍 *Results for* `{query}`:\n"]
    lines += [_fmt_short(t) for t in threats]
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def _handle_assets(update, context):
    if not await _auth_check(update):
        return
    assets = _get_assets()
    if not assets:
        await update.message.reply_text("No assets configured yet. Add them in Admin → Assets.")
        return
    _crit_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
    lines = [f"🖥 *Monitored Assets ({len(assets)}):*\n"]
    for a in assets:
        emoji = _crit_emoji.get(a.criticality, "⚪")
        lines.append(f"{emoji} *{a.name}* — {a.vendor} {a.model} (`{a.criticality}`)")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def _handle_nlp(update, context):
    if not await _auth_check(update):
        return
    question = (update.message.text or "").strip()
    if not question:
        return
    thinking = await update.message.reply_text("🤔 Thinking…")
    try:
        threats = _get_recent_threats(15)
        assets = _get_assets()
        answer = await _ask_llm(question, threats, assets)
        await thinking.delete()
        await update.message.reply_text(answer)
    except Exception as exc:
        logger.error("NLP handler failed: %r", exc, exc_info=True)
        await thinking.edit_text("⚠️ Failed to answer your question. Check logs.")


# ── Lifecycle ──────────────────────────────────────────────────────────────────

def _build_app(token: str):
    from telegram.ext import Application, CommandHandler, MessageHandler, filters

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", _handle_start))
    app.add_handler(CommandHandler("threats", _handle_threats))
    app.add_handler(CommandHandler("latest", _handle_latest))
    app.add_handler(CommandHandler("search", _handle_search))
    app.add_handler(CommandHandler("assets", _handle_assets))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_nlp))
    return app


def _run_bot(token: str) -> None:
    global _loop, _stop_event

    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    _stop_event = asyncio.Event()

    app = _build_app(token)

    async def _main():
        async with app:
            await app.start()
            # Brief delay so any lingering Telegram long-poll from a previous
            # instance (409 window) can expire before we start polling.
            await asyncio.sleep(5)
            await app.updater.start_polling(drop_pending_updates=False)
            logger.info("Telegram bot polling started")
            await _stop_event.wait()
            await app.updater.stop()
            await app.stop()
        logger.info("Telegram bot stopped")

    _loop.run_until_complete(_main())


def start_bot() -> None:
    global _bot_thread

    from app.config import settings

    if not settings.telegram_bot_token:
        logger.info("TELEGRAM_BOT_TOKEN not set — bot disabled")
        return

    _bot_thread = threading.Thread(
        target=_run_bot,
        args=(settings.telegram_bot_token,),
        daemon=True,
        name="ti-telegram-bot",
    )
    _bot_thread.start()


def stop_bot() -> None:
    global _loop, _stop_event, _bot_thread
    if _loop and _stop_event:
        _loop.call_soon_threadsafe(_stop_event.set)
    if _bot_thread and _bot_thread.is_alive():
        _bot_thread.join(timeout=8)
