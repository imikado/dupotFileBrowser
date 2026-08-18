from gi.repository import GLib


def close_then_run(popover, action) -> None:
    """Pops `popover` down and calls `action` once it has actually
    closed. Never call popover.popdown() synchronously from
    inside one of its own buttons' "clicked" handler: GTK is still
    mid-way through press/release bookkeeping for that button, and
    tearing the popover out of the widget tree right then corrupts it
    — surfaces as "Gtk-WARNING: Broken accounting of active state for
    widget" (seen in the Flatpak build) and can leave `action` never
    called, i.e. the click silently does nothing. Deferring one tick
    lets the click event finish unwinding before touching the tree.

    `action` then runs on the popover's real "closed" signal, not just
    after popdown() — a follow-up popup opened from `action` races the
    close animation/pointer-grab teardown otherwise (see popup_deferred).
    But "closed" isn't guaranteed to fire (e.g. popdown() interrupting
    the popover's own still-in-flight *opening* transition), so a short
    timeout runs `action` anyway if "closed" doesn't show up — whichever
    fires first wins, the other is a no-op."""

    def _start_close() -> bool:
        ran = False

        def _run_once(*_args) -> bool:
            nonlocal ran
            if not ran:
                ran = True
                action()
            return False

        popover.connect("closed", _run_once)
        popover.popdown()
        GLib.timeout_add(200, _run_once)
        return False

    GLib.idle_add(_start_close)


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
