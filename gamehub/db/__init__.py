from .global_db import get_global_pool, close_global_pool
from .game_db import get_game_pool, close_game_pool
from .setup import init_databases

__all__ = [
    "get_global_pool",
    "close_global_pool",
    "get_game_pool",
    "close_game_pool",
    "init_databases",
]
