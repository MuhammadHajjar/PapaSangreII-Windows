"""The bits around the game: menus, and the settings they change."""

from .menu import (Menu, MenuItem, PAD_REBINDABLE, REBINDABLE, about_menu, achievement_text, adios_menu,
                   achievements_menu, keys_menu, level_complete_menu,
                   level_failed_menu, level_menu, main_menu, pad_menu,
                   pause_menu, settings_menu, update_offer_menu, update_ready_menu)

__all__ = ['Menu', 'MenuItem', 'PAD_REBINDABLE', 'REBINDABLE', 'about_menu', 'achievement_text', 'adios_menu',
           'achievements_menu', 'keys_menu', 'level_complete_menu',
           'level_failed_menu', 'level_menu', 'main_menu', 'pad_menu',
           'pause_menu', 'settings_menu', 'update_offer_menu', 'update_ready_menu']
