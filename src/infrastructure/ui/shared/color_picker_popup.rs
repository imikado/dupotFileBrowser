//! Grid of Nemo's folder colors, plus "Remove Color".

use gtk::prelude::*;

use crate::domain::shared::folder_color::PALETTE;
use crate::infrastructure::service::i18n_service::tr;
use crate::infrastructure::ui::shared::context_menu::{
    attached_popover, popup_deferred, run_then_close,
};

const SWATCH_SIZE: i32 = 28;
const COLUMNS: i32 = 4;

/// `on_selected` gets the picked hex, or `None` for "Remove Color". The
/// `selected` color, if any, is drawn with a ring.
pub fn show_color_picker(
    parent: &impl IsA<gtk::Widget>,
    selected: Option<&str>,
    on_selected: impl Fn(Option<String>) + 'static,
) {
    let container = gtk::Box::new(gtk::Orientation::Vertical, 8);
    container.set_margin_top(10);
    container.set_margin_bottom(10);
    container.set_margin_start(10);
    container.set_margin_end(10);
    let grid = gtk::Grid::new();
    grid.set_row_spacing(6);
    grid.set_column_spacing(6);
    container.append(&grid);

    let popover = attached_popover(parent, &container);
    let on_selected = std::rc::Rc::new(on_selected);

    for (index, (label, hex)) in PALETTE.iter().enumerate() {
        let swatch = gtk::Button::new();
        swatch.set_tooltip_text(Some(&tr(label)));
        swatch.add_css_class("circular");
        swatch.add_css_class("fb-swatch");
        swatch.add_css_class(&swatch_class(hex));
        if selected.is_some_and(|color| color.eq_ignore_ascii_case(hex)) {
            swatch.add_css_class("fb-swatch-selected");
        }
        swatch.set_size_request(SWATCH_SIZE, SWATCH_SIZE);
        let (popover, on_selected, hex) = (popover.clone(), on_selected.clone(), hex.to_string());
        swatch.connect_clicked(move |_| {
            let (on_selected, hex) = (on_selected.clone(), hex.clone());
            run_then_close(&popover, move || on_selected(Some(hex)));
        });
        let index = index as i32;
        grid.attach(&swatch, index % COLUMNS, index / COLUMNS, 1, 1);
    }

    let remove = gtk::Button::with_label(&tr("Remove Color"));
    remove.add_css_class("flat");
    {
        let popover = popover.clone();
        remove.connect_clicked(move |_| {
            let on_selected = on_selected.clone();
            run_then_close(&popover, move || on_selected(None));
        });
    }
    container.append(&remove);
    popup_deferred(&popover);
}

/// CSS class of a palette color: `fb-color-5294e2`.
pub fn swatch_class(hex: &str) -> String {
    format!("fb-color-{}", hex.trim_start_matches('#').to_lowercase())
}

/// Background rules for every palette color, installed with the app CSS.
pub fn palette_css() -> String {
    PALETTE
        .iter()
        .map(|(_, hex)| format!(".{} {{ background: {hex}; }}\n", swatch_class(hex)))
        .collect()
}
