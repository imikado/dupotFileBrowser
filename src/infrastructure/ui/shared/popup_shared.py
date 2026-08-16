def popup_deferred(popover) -> bool:
    """Shows a popover on the next idle iteration instead of straight
    away. Needed whenever popup() is called synchronously from inside
    another popover's own click/close handling (e.g. a right-click menu
    item opening a follow-up popover, or the right-click gesture itself)
    — doing it immediately races that other popover's pointer grab
    /teardown and the new one ends up unresponsive.

    Always schedule at GLib.PRIORITY_HIGH_IDLE, not idle_add()'s default
    PRIORITY_DEFAULT_IDLE: a right-click on a just-opened/just-navigated
    row can land behind that row's own default-priority idle work (e.g.
    PathPage._scroll_to_end, queued the moment the click opened a new
    column) — at equal priority those run in queue order, so this popup
    would sit waiting on unrelated layout work and could show late enough
    to miss the click meant for one of its own buttons.

    Usage: GLib.idle_add(popup_deferred, popover, priority=GLib.PRIORITY_HIGH_IDLE)
    """
    popover.popup()
    return False
