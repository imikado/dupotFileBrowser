from gi.repository import GLib


def run_then_close(popover, action) -> None:
    """Pops `popover` down, then runs `action` — both from a single
    high-priority idle callback, `popover.popdown()` first.

    Neither step can happen synchronously inside the button's own
    "clicked" handler: GTK is still mid-way through press/release
    bookkeeping for that button at that point, and touching the popover
    right then corrupts it — "Gtk-WARNING: Broken accounting of active
    state for widget" (seen in the Flatpak build). Hence the single
    GLib.idle_add wrapping both.

    `action` used to run first, with popdown() only queued afterwards
    (at plain idle priority) on the theory that a follow-up popup
    opened by `action` (Add Color, Open With…) would simply steal the
    grab and let `popover` close as a side effect. It doesn't: that
    follow-up popup schedules its own popup() via popup_deferred at
    GLib.PRIORITY_HIGH_IDLE, which then ran *before* this plain-priority
    popdown() — so for one idle turn two popovers held a grab at once,
    which is exactly the accounting corruption above (still reported
    against `popover`'s own widgets afterwards).

    popdown() first, in the same PRIORITY_HIGH_IDLE callback, avoids
    that: `popover` is fully closed before `action` runs, so any
    follow-up popup it opens (also PRIORITY_HIGH_IDLE, but queued after
    this callback — same priority runs in queue order) only ever grabs
    once `popover` has already let go. Running both from one callback
    also means `action` always fires — it isn't gated on `popover`'s own
    "closed" signal (which isn't always emitted — see popup_deferred) or
    a timeout race, which is what let clicks silently do nothing before."""

    def _run() -> bool:
        popover.popdown()
        action()
        return False

    GLib.idle_add(_run, priority=GLib.PRIORITY_HIGH_IDLE)


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
