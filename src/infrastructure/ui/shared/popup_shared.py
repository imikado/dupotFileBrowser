from gi.repository import GLib


def run_then_close(popover, action) -> None:
    """Runs `action` right now — synchronously, before `popover` closes
    — then pops `popover` down on the next idle iteration.

    This used to run the other way around (close first, run `action`
    once "closed" fired or a timeout elapsed), to avoid opening a
    follow-up popup while the old grab hadn't been released yet. In
    practice that ordering was the less reliable one: waiting on
    "closed" (which isn't always emitted — see popup_deferred) or a
    fixed timeout is itself a race, and it was still possible for the
    click to visibly close the menu without `action` ever running —
    exactly the "right-click menu opens, but clicking an item does
    nothing" symptom (seen intermittently in the Flatpak build).
    Running `action` first removes that race entirely: it always fires,
    synchronously, in direct response to the click.

    A follow-up popup opened by `action` (Add Color, Open With…) is
    safe to open here, with `popover` still technically open: every
    such popup already goes through popup_deferred, which defers its
    own popup() to the next *high-priority* idle turn. popdown() below
    is queued at plain (lower) idle priority, so the follow-up popup's
    popup() runs first and takes the pointer grab — GTK then closes
    `popover` on its own as a side effect of losing that grab, and this
    popdown() call just confirms it.

    popdown() is deferred to idle rather than called synchronously here
    because doing it synchronously from inside this very button's own
    "clicked" handler corrupts GTK's press/release bookkeeping for that
    button — "Gtk-WARNING: Broken accounting of active state for
    widget" (also seen in the Flatpak build)."""
    action()
    GLib.idle_add(popover.popdown)


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
