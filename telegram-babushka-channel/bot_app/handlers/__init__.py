from aiogram import Router

from bot_app.config import Settings

from bot_app.handlers import admin, common, fallback, order


def setup_routers(settings: Settings) -> Router:
    root = Router()
    root.include_router(common.setup(settings))
    root.include_router(order.setup(settings))
    root.include_router(admin.setup(settings))
    root.include_router(fallback.setup(settings))
    return root
