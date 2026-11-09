import logging
from contextlib import asynccontextmanager

from agents import set_tracing_disabled
from fastapi import FastAPI
from openai import AsyncOpenAI

from core.config import get_settings
from core.logging import configure_logging
from modules.openui import cloud_system_prompt

# Preserve the existing startup/shutdown log category.
logger = logging.getLogger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)
    set_tracing_disabled(disabled=True)
    app.state.settings = settings
    app.state.openui_prompt = cloud_system_prompt(settings.OPENUI_SPEC_PATH)
    logger.info("Application starting.")

    try:
        async with AsyncOpenAI(
            api_key=settings.THESYS_API_KEY.get_secret_value(),
            base_url=settings.THESYS_BASE_URL,
        ) as client:
            app.state.openai_client = client
            yield
    finally:
        logger.info("Application stopped.")
