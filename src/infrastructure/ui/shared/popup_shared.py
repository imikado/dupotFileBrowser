def popup_deferred(popover) -> bool:
    """Shows a popover on the next idle iteration instead of straight
    away. Needed whenever popup() is called synchronously from inside
    another popover's own click/close handling (e.g. a right-click menu
    item opening a follow-up popover, or the right-click gesture itself)
    — doing it immediately races that other popover's pointer grab
    /teardown and the new one ends up unresponsive.

    Usage: GLib.idle_add(popup_deferred, popover)
    """
    popover.popup()
    return False
