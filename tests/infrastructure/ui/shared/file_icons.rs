//! The icons must decode without gdk-pixbuf: in the Snap (core26),
//! gdk-pixbuf hands PNGs to glycin, whose sandboxed loaders can't run.

use dupot_file_browser::infrastructure::ui::shared::file_icons::{
    baked_icon, baked_icon_keys, tinted_folder,
};
use gtk::gdk;
use gtk::prelude::*;

#[test]
fn every_embedded_icon_decodes_in_both_variants() {
    for key in baked_icon_keys() {
        for dark in [false, true] {
            let texture = baked_icon(key, dark).unwrap_or_else(|| panic!("{key} (dark: {dark})"));
            assert!(texture.width() > 0 && texture.height() > 0, "{key}");
        }
    }
}

#[test]
fn tinted_folder_keeps_the_silhouette_in_the_tag_color() {
    let texture = tinted_folder("#f54f54", 16).expect("tinted folder");
    let mut downloader = gdk::TextureDownloader::new(&texture);
    downloader.set_format(gdk::MemoryFormat::R8g8b8a8);
    let (bytes, _) = downloader.download_bytes();
    let pixels: Vec<&[u8]> = bytes.chunks(4).collect();
    assert!(pixels.iter().any(|pixel| pixel[3] > 0), "empty icon");
    assert!(
        pixels
            .iter()
            .filter(|pixel| pixel[3] > 0)
            .all(|pixel| pixel[..3] == [0xf5, 0x4f, 0x54])
    );
}

#[test]
fn tinted_folder_rejects_a_malformed_color() {
    assert!(tinted_folder("red", 16).is_none());
}
