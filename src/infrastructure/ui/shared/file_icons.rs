//! Every icon of the app comes from the PNGs embedded from
//! `src/assets/icons/{light,dark}/` rather than an icon-theme name, so it
//! looks the same wherever it's installed. With "Use system icon theme",
//! file-type icons come from the theme when it has them.

use std::cell::{Cell, RefCell};
use std::collections::HashMap;

use adw::prelude::*;
use gtk::{gdk, gdk_pixbuf, gio, glib};

use crate::domain::entity::file_entry_entity::FOLDER_ICON_KEY;

pub const ICON_DISPLAY_SIZE: i32 = 16;

macro_rules! icons {
    ($($key:literal),* $(,)?) => {
        &[$((
            $key,
            include_bytes!(concat!("../../../assets/icons/light/", $key, ".png")) as &[u8],
            include_bytes!(concat!("../../../assets/icons/dark/", $key, ".png")) as &[u8],
        )),*]
    };
}

/// (key, light variant, dark variant).
const ICONS: &[(&str, &[u8], &[u8])] = icons![
    "archive",
    "audio",
    "document",
    "edit-paste",
    "edit-undo",
    "executable",
    "folder",
    "font",
    "generic",
    "go-next",
    "go-up",
    "image",
    "open-menu",
    "presentation",
    "spreadsheet",
    "user-home",
    "user-trash",
    "video",
    "weather-clear-night",
    "weather-clear",
];

/// Icon key -> freedesktop icon name, used with the system icon theme.
const SYSTEM_ICON_NAMES: &[(&str, &str)] = &[
    ("image", "image-x-generic"),
    ("audio", "audio-x-generic"),
    ("video", "video-x-generic"),
    ("archive", "package-x-generic"),
    ("document", "x-office-document"),
    ("spreadsheet", "x-office-spreadsheet"),
    ("presentation", "x-office-presentation"),
    ("font", "font-x-generic"),
    ("executable", "application-x-executable"),
    ("generic", "text-x-generic"),
    ("folder", "folder"),
];

thread_local! {
    static USE_SYSTEM_THEME: Cell<bool> = const { Cell::new(false) };
    static TEXTURES: RefCell<HashMap<(String, bool, i32), gdk::Texture>> = RefCell::default();
    static TINTED: RefCell<HashMap<(String, String, i32), Option<gdk::Texture>>> = RefCell::default();
    static SYSTEM_ICONS: RefCell<HashMap<(String, i32), Option<gtk::IconPaintable>>> = RefCell::default();
}

/// Read once at startup: changing it restarts the app.
pub fn set_use_system_theme(enabled: bool) {
    USE_SYSTEM_THEME.set(enabled);
}

fn icon_bytes(key: &str, dark: bool) -> &'static [u8] {
    let (_, light, dark_bytes) = ICONS
        .iter()
        .find(|(k, _, _)| *k == key)
        .or_else(|| ICONS.iter().find(|(k, _, _)| *k == "generic"))
        .expect("generic icon is embedded");
    if dark { dark_bytes } else { light }
}

fn load_pixbuf(bytes: &'static [u8], size: i32) -> Option<gdk_pixbuf::Pixbuf> {
    let stream = gio::MemoryInputStream::from_bytes(&glib::Bytes::from_static(bytes));
    gdk_pixbuf::Pixbuf::from_stream_at_scale(&stream, size, size, true, gio::Cancellable::NONE).ok()
}

fn baked_texture(key: &str, dark: bool, size: i32) -> Option<gdk::Texture> {
    let cache_key = (key.to_string(), dark, size);
    if let Some(texture) = TEXTURES.with_borrow(|cache| cache.get(&cache_key).cloned()) {
        return Some(texture);
    }
    let texture = gdk::Texture::for_pixbuf(&load_pixbuf(icon_bytes(key, dark), size)?);
    TEXTURES.with_borrow_mut(|cache| cache.insert(cache_key, texture.clone()));
    Some(texture)
}

/// Fills the icon's silhouette (alpha kept) with `hex` (`#rrggbb`).
fn tint(pixbuf: &gdk_pixbuf::Pixbuf, hex: &str) -> Option<gdk::Texture> {
    let channel = |i: usize| u8::from_str_radix(hex.get(i..i + 2)?, 16).ok();
    let rgb = [channel(1)?, channel(3)?, channel(5)?];
    let pixbuf = if pixbuf.has_alpha() {
        pixbuf.clone()
    } else {
        pixbuf.add_alpha(false, 0, 0, 0).ok()?
    };
    let (width, height) = (pixbuf.width() as usize, pixbuf.height() as usize);
    let stride = pixbuf.rowstride() as usize;
    let channels = pixbuf.n_channels() as usize;
    let mut data = pixbuf.read_pixel_bytes().to_vec();
    for y in 0..height {
        for x in 0..width {
            let i = y * stride + x * channels;
            data[i..i + 3].copy_from_slice(&rgb);
        }
    }
    Some(
        gdk::MemoryTexture::new(
            width as i32,
            height as i32,
            gdk::MemoryFormat::R8g8b8a8,
            &glib::Bytes::from_owned(data),
            stride,
        )
        .upcast(),
    )
}

fn system_icon(key: &str, size: i32) -> Option<gtk::IconPaintable> {
    let cache_key = (key.to_string(), size);
    if let Some(cached) = SYSTEM_ICONS.with_borrow(|cache| cache.get(&cache_key).cloned()) {
        return cached;
    }
    let paintable = SYSTEM_ICON_NAMES
        .iter()
        .find(|(k, _)| *k == key)
        .zip(gdk::Display::default())
        .and_then(|((_, name), display)| {
            let theme = gtk::IconTheme::for_display(&display);
            theme.has_icon(name).then(|| {
                theme.lookup_icon(
                    name,
                    &[],
                    size,
                    1,
                    gtk::TextDirection::None,
                    gtk::IconLookupFlags::FORCE_REGULAR,
                )
            })
        });
    SYSTEM_ICONS.with_borrow_mut(|cache| cache.insert(cache_key, paintable.clone()));
    paintable
}

/// Tinted folder icon: the system theme's own artwork when available as a
/// file (crisper, and matching uncolored folders), else the baked one.
fn tinted_folder(hex: &str, size: i32) -> Option<gdk::Texture> {
    let cache_key = (hex.to_string(), USE_SYSTEM_THEME.get().to_string(), size);
    if let Some(cached) = TINTED.with_borrow(|cache| cache.get(&cache_key).cloned()) {
        return cached;
    }
    let from_theme = USE_SYSTEM_THEME
        .get()
        .then(|| system_icon(FOLDER_ICON_KEY, size))
        .flatten()
        .and_then(|paintable| paintable.file()?.path())
        .and_then(|path| gdk_pixbuf::Pixbuf::from_file_at_size(path, size, size).ok());
    let pixbuf = from_theme.or_else(|| load_pixbuf(icon_bytes(FOLDER_ICON_KEY, false), size));
    let texture = pixbuf.and_then(|pixbuf| tint(&pixbuf, hex));
    TINTED.with_borrow_mut(|cache| cache.insert(cache_key, texture.clone()));
    texture
}

fn image_of(paintable: Option<&impl IsA<gdk::Paintable>>, size: i32) -> gtk::Image {
    let image = gtk::Image::new();
    if let Some(paintable) = paintable {
        image.set_paintable(Some(paintable));
    }
    image.set_size_request(size, size);
    image.set_pixel_size(size);
    image
}

fn is_dark() -> bool {
    adw::StyleManager::default().is_dark()
}

/// Icon `key` at `size`, matching the current light/dark style.
pub fn icon_image(key: &str, size: i32) -> gtk::Image {
    if USE_SYSTEM_THEME.get()
        && let Some(paintable) = system_icon(key, size)
    {
        return image_of(Some(&paintable), size);
    }
    image_of(baked_texture(key, is_dark(), size).as_ref(), size)
}

/// `icon_image` at the 16px size of list rows and buttons.
pub fn small_icon(key: &str) -> gtk::Image {
    icon_image(key, ICON_DISPLAY_SIZE)
}

/// Folder icon, tinted with its color tag if any.
pub fn folder_image(color: Option<&str>, size: i32) -> gtk::Image {
    match color.and_then(|hex| tinted_folder(hex, size)) {
        Some(texture) => image_of(Some(&texture), size),
        None => icon_image(FOLDER_ICON_KEY, size),
    }
}

/// A real preview of an image file, decoded at `size`.
pub fn thumbnail(path: &std::path::Path, size: i32) -> Option<gtk::Image> {
    let pixbuf = gdk_pixbuf::Pixbuf::from_file_at_scale(path, size, size, true).ok()?;
    Some(image_of(Some(&gdk::Texture::for_pixbuf(&pixbuf)), size))
}
