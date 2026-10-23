use std::cell::RefCell;
use std::collections::VecDeque;
use std::path::{Path, PathBuf};
use std::rc::Rc;
use std::time::Duration;

use adw::prelude::*;
use gtk::{gdk, gio, glib};

use crate::domain::contract::archive_repository::ArchiveRepository;
use crate::domain::contract::file_system_repository::FileSystemRepository;
use crate::domain::entity::app_info::APP;
use crate::domain::entity::file_operation_entity::{FileOperationEntity, FileOperationKind};
use crate::domain::entity::user_settings_entity::{Theme, ViewMode};
use crate::domain::error::{DomainError, DomainResult};
use crate::domain::shared::path::file_name;
use crate::domain::usecase::destination::{Destination, extract_destination, paste_destination};
use crate::infrastructure::service::gvfs_service;
use crate::infrastructure::service::i18n_service::{self, tr, trf};
use crate::infrastructure::ui::app_context::{AppContext, BrowserEvent};
use crate::infrastructure::ui::browser_tab::{BrowserTab, TabEventSink};
use crate::infrastructure::ui::menu::parameters_dialog::{SettingsChanges, show_parameters_dialog};
use crate::infrastructure::ui::shared::alert_dialog::{ask_name, show_error};
use crate::infrastructure::ui::shared::color_picker_popup::palette_css;
use crate::infrastructure::ui::shared::file_icons::{self, small_icon};
use crate::infrastructure::ui::shared::side_menu::{PathCallback, SideMenu, SideMenuItem};
use crate::infrastructure::ui::shared::view_mode_switcher::build_view_mode_switcher;

const APP_CSS: &str = "
label.fb-paste-badge {
    background: @accent_bg_color;
    color: @accent_fg_color;
    font-size: 0.7em;
    min-width: 14px;
    padding: 1px 4px;
    border-radius: 999px;
}

button.fb-menu-item {
    padding: 8px 16px;
    min-width: 160px;
}

row.fb-separator-row {
    background: none;
    border: none;
    box-shadow: none;
    padding: 0;
    margin: 0;
    min-height: 0;
}

.fb-color-dot {
    border-radius: 999px;
}

button.fb-swatch {
    min-width: 28px;
    min-height: 28px;
}

button.fb-swatch-selected {
    box-shadow: 0 0 0 2px @theme_bg_color, 0 0 0 4px @accent_bg_color;
}
";

const SIDEBAR_WIDTH: i32 = 220;
const SAVE_WINDOW_SIZE_DELAY: Duration = Duration::from_millis(500);
const GRID_ICON_SIZE_DELAY: Duration = Duration::from_millis(150);

fn install_app_css() {
    let provider = gtk::CssProvider::new();
    provider.load_from_string(&format!("{APP_CSS}{}", palette_css()));
    if let Some(display) = gdk::Display::default() {
        gtk::style_context_add_provider_for_display(
            &display,
            &provider,
            gtk::STYLE_PROVIDER_PRIORITY_APPLICATION,
        );
    }
}

pub fn build_application() -> adw::Application {
    gvfs_service::ensure_metadata_module_discoverable();
    let app = adw::Application::builder().application_id(APP.id).build();
    app.connect_startup(|_| install_app_css());
    app.connect_activate(|app| {
        if let Some(window) = app.active_window() {
            window.present();
            return;
        }
        let ctx = AppContext::new();
        let language = ctx.settings().language;
        i18n_service::init(&language.code(i18n_service::system_language_code()));
        file_icons::set_use_system_theme(ctx.settings().use_system_icon_theme);
        MainWindow::new(app, ctx).window.present();
    });
    app
}

fn run_job(
    file_system: &dyn FileSystemRepository,
    archives: &dyn ArchiveRepository,
    job: &FileOperationEntity,
) -> DomainResult<()> {
    match job.kind {
        FileOperationKind::Copy => file_system.copy_path(&job.source, &job.destination),
        FileOperationKind::Move => file_system.move_path(&job.source, &job.destination),
        FileOperationKind::Compress(format) => {
            archives.compress(&job.source, &job.destination, format)
        }
        FileOperationKind::Extract => archives.extract(&job.source, &job.destination),
    }
}

type WindowAction = fn(&Rc<MainWindow>);

struct MainWindow {
    ctx: Rc<AppContext>,
    window: adw::ApplicationWindow,
    up_button: gtk::Button,
    path_entry: gtk::Entry,
    menu_button: gtk::MenuButton,
    paste_slot: gtk::Box,
    tab_view: adw::TabView,
    side_menu: Rc<SideMenu>,
    tabs: RefCell<Vec<(Rc<BrowserTab>, adw::TabPage)>>,
    current_path: RefCell<PathBuf>,
    home_path: PathBuf,
    trash_path: PathBuf,
    /// Host system folders, reachable from the sandbox.
    host_paths: Vec<(String, PathBuf)>,
    /// File waiting to be pasted, and whether it was cut.
    clipboard: RefCell<Option<(PathBuf, bool)>>,
    /// Background jobs, run one at a time (front is running).
    jobs: RefCell<VecDeque<FileOperationEntity>>,
    save_size_source: RefCell<Option<glib::SourceId>>,
    icon_size_source: RefCell<Option<glib::SourceId>>,
}

impl MainWindow {
    fn new(app: &adw::Application, ctx: Rc<AppContext>) -> Rc<Self> {
        let (width, height) = {
            let settings = ctx.settings();
            (settings.window_width, settings.window_height)
        };
        let window = adw::ApplicationWindow::new(app);
        window.set_title(Some(&tr("File browser")));
        window.set_default_size(width, height);

        let home_path = ctx.file_system.home_dir();
        let trash_path = ctx.trash.trash_dir();
        let host_paths = if ctx.desktop.is_sandboxed() {
            [
                (tr("Host /etc"), "/run/host/etc"),
                (tr("Host /usr"), "/run/host/usr"),
            ]
            .into_iter()
            .filter(|(_, path)| ctx.file_system.is_dir(Path::new(path)))
            .map(|(label, path)| (label, PathBuf::from(path)))
            .collect()
        } else {
            Vec::new()
        };

        let up_button = gtk::Button::new();
        up_button.set_tooltip_text(Some(&tr("Parent folder")));
        let path_entry = gtk::Entry::new();
        path_entry.set_hexpand(true);
        path_entry.add_css_class("flat");
        path_entry.set_tooltip_text(Some(&tr("Type a path and press Enter to go there")));
        let menu = gio::Menu::new();
        menu.append(Some(&tr("Parameters")), Some("win.parameters"));
        menu.append(Some(&tr("About")), Some("win.about"));
        let menu_button = gtk::MenuButton::new();
        menu_button.set_menu_model(Some(&menu));

        let tab_view = adw::TabView::new();
        tab_view.set_vexpand(true);

        let this = Rc::new(Self {
            ctx,
            window,
            up_button,
            path_entry,
            menu_button,
            paste_slot: gtk::Box::new(gtk::Orientation::Horizontal, 0),
            tab_view,
            side_menu: SideMenu::new(),
            tabs: RefCell::default(),
            current_path: RefCell::new(home_path.clone()),
            home_path,
            trash_path,
            host_paths,
            clipboard: RefCell::default(),
            jobs: RefCell::default(),
            save_size_source: RefCell::default(),
            icon_size_source: RefCell::default(),
        });
        this.build_layout();
        this.connect_signals();
        this.apply_theme();
        this.refresh_header_icons();
        this.refresh_side_menu();
        let home = this.home_path.clone();
        this.new_tab(&home);
        this
    }

    fn build_layout(self: &Rc<Self>) {
        let header = adw::HeaderBar::new();
        header.pack_start(&self.up_button);
        header.set_title_widget(Some(&self.path_entry));
        header.pack_end(&self.paste_slot);

        let (mode, icon_size) = {
            let settings = self.ctx.settings();
            (settings.view_mode, settings.grid_icon_size)
        };
        let (on_mode, on_size) = (Rc::downgrade(self), Rc::downgrade(self));
        let switcher = build_view_mode_switcher(
            mode,
            icon_size,
            move |mode| {
                if let Some(this) = on_mode.upgrade() {
                    this.on_view_mode_changed(mode);
                }
            },
            move |size| {
                if let Some(this) = on_size.upgrade() {
                    this.on_grid_icon_size_changed(size);
                }
            },
        );
        header.pack_end(&switcher);
        header.pack_end(&self.menu_button);

        let tab_bar = adw::TabBar::new();
        tab_bar.set_view(Some(&self.tab_view));
        // Keeps the "+" button reachable with a single tab.
        tab_bar.set_autohide(false);
        let new_tab_button = gtk::Button::from_icon_name("tab-new-symbolic");
        new_tab_button.set_tooltip_text(Some(&tr("New Tab")));
        new_tab_button.set_action_name(Some("win.new-tab"));
        tab_bar.set_end_action_widget(Some(&new_tab_button));

        let content = gtk::Box::new(gtk::Orientation::Vertical, 0);
        content.set_hexpand(true);
        content.set_vexpand(true);
        content.append(&tab_bar);
        content.append(&self.tab_view);

        let sidebar = gtk::ScrolledWindow::new();
        sidebar.set_child(Some(self.side_menu.widget()));
        sidebar.set_policy(gtk::PolicyType::Never, gtk::PolicyType::Automatic);
        sidebar.set_size_request(SIDEBAR_WIDTH, -1);
        sidebar.add_css_class("background");

        let body = gtk::Box::new(gtk::Orientation::Horizontal, 0);
        body.set_vexpand(true);
        body.set_hexpand(true);
        body.append(&sidebar);
        body.append(&gtk::Separator::new(gtk::Orientation::Vertical));
        body.append(&content);

        let toolbar_view = adw::ToolbarView::new();
        toolbar_view.add_top_bar(&header);
        toolbar_view.set_content(Some(&body));
        self.window.set_content(Some(&toolbar_view));
    }

    fn connect_signals(self: &Rc<Self>) {
        let actions: [(&str, WindowAction); 4] = [
            ("parameters", Self::show_parameters),
            ("about", Self::show_about),
            ("new-tab", Self::new_tab_from_active),
            ("close-tab", Self::close_active_tab),
        ];
        for (name, callback) in actions {
            let action = gio::SimpleAction::new(name, None);
            let weak = Rc::downgrade(self);
            action.connect_activate(move |_, _| {
                if let Some(this) = weak.upgrade() {
                    callback(&this);
                }
            });
            self.window.add_action(&action);
        }
        if let Some(app) = self.window.application() {
            app.set_accels_for_action("win.new-tab", &["<Control>t"]);
            app.set_accels_for_action("win.close-tab", &["<Control>w"]);
        }

        let weak = Rc::downgrade(self);
        self.up_button.connect_clicked(move |_| {
            if let Some(this) = weak.upgrade() {
                this.on_up_clicked();
            }
        });
        let weak = Rc::downgrade(self);
        self.path_entry.connect_activate(move |entry| {
            if let Some(this) = weak.upgrade() {
                this.on_path_entry_activate(entry);
            }
        });
        self.path_entry
            .connect_changed(|entry| entry.remove_css_class("error"));

        let weak = Rc::downgrade(self);
        self.tab_view.connect_close_page(move |view, page| {
            let last = view.n_pages() <= 1;
            if !last && let Some(this) = weak.upgrade() {
                this.tabs.borrow_mut().retain(|(_, p)| p != page);
            }
            view.close_page_finish(page, !last);
            glib::Propagation::Stop
        });
        let weak = Rc::downgrade(self);
        self.tab_view.connect_selected_page_notify(move |_| {
            if let Some(this) = weak.upgrade() {
                this.on_tab_selected();
            }
        });

        for notify in ["default-width", "default-height"] {
            let weak = Rc::downgrade(self);
            self.window.connect_notify_local(Some(notify), move |_, _| {
                if let Some(this) = weak.upgrade() {
                    this.schedule_window_size_save();
                }
            });
        }
        let weak = Rc::downgrade(self);
        self.window.connect_close_request(move |_| {
            if let Some(this) = weak.upgrade() {
                this.flush_pending_saves();
            }
            glib::Propagation::Proceed
        });

        // File-type icons are baked light/dark PNGs: rebuild on style flips.
        let weak = Rc::downgrade(self);
        adw::StyleManager::default().connect_dark_notify(move |_| {
            if let Some(this) = weak.upgrade() {
                this.refresh_header_icons();
                this.update_paste_button();
                this.refresh_side_menu();
                for tab in this.all_tabs() {
                    tab.reload();
                }
            }
        });
    }

    // --- Settings persistence -----------------------------------------

    fn schedule_window_size_save(self: &Rc<Self>) {
        if let Some(source) = self.save_size_source.take() {
            source.remove();
        }
        let weak = Rc::downgrade(self);
        let source = glib::timeout_add_local_once(SAVE_WINDOW_SIZE_DELAY, move || {
            if let Some(this) = weak.upgrade() {
                this.save_size_source.take();
                this.save_window_size();
            }
        });
        *self.save_size_source.borrow_mut() = Some(source);
    }

    fn save_window_size(&self) {
        let (width, height) = self.window.default_size();
        self.ctx.settings_mut().set_window_size(width, height);
        self.ctx.save_settings();
    }

    fn flush_pending_saves(&self) {
        if let Some(source) = self.save_size_source.take() {
            source.remove();
            self.save_window_size();
        }
        if let Some(source) = self.icon_size_source.take() {
            source.remove();
            self.ctx.save_settings();
        }
    }

    fn apply_theme(&self) {
        let scheme = match self.ctx.settings().theme {
            Theme::Dark => adw::ColorScheme::ForceDark,
            Theme::Light => adw::ColorScheme::ForceLight,
            Theme::System => adw::ColorScheme::Default,
        };
        adw::StyleManager::default().set_color_scheme(scheme);
    }

    fn refresh_header_icons(&self) {
        self.up_button.set_child(Some(&small_icon("go-up")));
        self.menu_button.set_child(Some(&small_icon("open-menu")));
    }

    // --- Sidebar --------------------------------------------------------

    fn refresh_side_menu(self: &Rc<Self>) {
        let callback = |action: fn(&Rc<Self>, PathBuf)| -> PathCallback {
            let weak = Rc::downgrade(self);
            Rc::new(move |path| {
                if let Some(this) = weak.upgrade() {
                    action(&this, path);
                }
            })
        };
        let go_to = callback(Self::go_to_path);
        let item =
            |icon_key, label: String, path: &Path, on_activate: &PathCallback| SideMenuItem {
                icon_key,
                label,
                path: path.to_path_buf(),
                on_activate: on_activate.clone(),
                on_remove: None,
            };
        let mut items = vec![
            Some(item("user-home", tr("Home"), &self.home_path, &go_to)),
            Some(item(
                "user-trash",
                tr("Trash"),
                &self.trash_path,
                &callback(|this, _| this.go_to_trash()),
            )),
        ];
        for (label, path) in &self.host_paths {
            items.push(Some(item("folder", label.clone(), path, &go_to)));
        }
        let favorites = self.ctx.settings().favorite_list.clone();
        if !favorites.is_empty() {
            items.push(None);
            let remove = callback(Self::remove_favorite);
            for favorite in favorites {
                let mut favorite_item =
                    item("folder", favorite.label, Path::new(&favorite.path), &go_to);
                favorite_item.on_remove = Some(remove.clone());
                items.push(Some(favorite_item));
            }
        }
        self.side_menu.set_items(items);
        self.side_menu
            .set_selected_path(&self.current_path.borrow());
    }

    fn remove_favorite(self: &Rc<Self>, path: PathBuf) {
        self.ctx
            .settings_mut()
            .remove_favorite(&path.to_string_lossy());
        self.ctx.save_settings();
        self.refresh_side_menu();
    }

    // --- Tabs -----------------------------------------------------------

    fn all_tabs(&self) -> Vec<Rc<BrowserTab>> {
        self.tabs
            .borrow()
            .iter()
            .map(|(tab, _)| tab.clone())
            .collect()
    }

    fn active_tab(&self) -> Option<Rc<BrowserTab>> {
        let selected = self.tab_view.selected_page()?;
        self.tabs
            .borrow()
            .iter()
            .find(|(_, page)| *page == selected)
            .map(|(tab, _)| tab.clone())
    }

    fn tab_page(&self, tab: &Rc<BrowserTab>) -> Option<adw::TabPage> {
        self.tabs
            .borrow()
            .iter()
            .find(|(t, _)| Rc::ptr_eq(t, tab))
            .map(|(_, page)| page.clone())
    }

    fn new_tab_from_active(self: &Rc<Self>) {
        let path = match self.active_tab() {
            Some(tab) if tab.showing_trash() => self.home_path.clone(),
            _ => self.current_path.borrow().clone(),
        };
        self.new_tab(&path);
    }

    fn new_tab(self: &Rc<Self>, path: &Path) {
        let weak = Rc::downgrade(self);
        let sink: TabEventSink = Rc::new(move |tab, event| {
            if let Some(this) = weak.upgrade() {
                this.on_tab_event(tab, event);
            }
        });
        let tab = BrowserTab::new(&self.ctx, sink);
        let page = self.tab_view.append(tab.widget());
        self.tabs.borrow_mut().push((tab.clone(), page.clone()));
        tab.navigate(path, false);
        self.update_tab_title(&tab);
        self.tab_view.set_selected_page(&page);
        self.path_entry.set_sensitive(true);
        self.update_path_state(path);
    }

    fn close_active_tab(self: &Rc<Self>) {
        if let Some(page) = self.tab_view.selected_page() {
            self.tab_view.close_page(&page);
        }
    }

    fn on_tab_selected(&self) {
        let Some(tab) = self.active_tab() else { return };
        if tab.showing_trash() {
            self.show_trash_state();
        } else {
            self.path_entry.set_sensitive(true);
            self.update_path_state(&tab.current_path());
        }
    }

    fn tab_title(&self, tab: &BrowserTab) -> String {
        if tab.showing_trash() {
            return tr("Trash");
        }
        let path = tab.current_path();
        if path == self.home_path {
            tr("Home")
        } else {
            file_name(&path)
        }
    }

    fn update_tab_title(&self, tab: &Rc<BrowserTab>) {
        if let Some(page) = self.tab_page(tab) {
            page.set_title(&self.tab_title(tab));
        }
    }

    fn on_tab_event(self: &Rc<Self>, tab: &Rc<BrowserTab>, event: BrowserEvent) {
        match event {
            BrowserEvent::PathChanged(path) => {
                self.update_tab_title(tab);
                if self
                    .active_tab()
                    .is_some_and(|active| Rc::ptr_eq(&active, tab))
                {
                    self.update_path_state(&path);
                }
            }
            BrowserEvent::FavoritesChanged => self.refresh_side_menu(),
            BrowserEvent::Clipboard { path, cut } => {
                *self.clipboard.borrow_mut() = Some((path, cut));
                self.update_paste_button();
            }
            BrowserEvent::Job(job) => self.enqueue_job(job),
            BrowserEvent::Extract(archive) => self.request_extract(&archive, None),
        }
    }

    // --- Navigation -----------------------------------------------------

    fn update_path_state(&self, path: &Path) {
        *self.current_path.borrow_mut() = path.to_path_buf();
        self.path_entry.set_text(&path.to_string_lossy());
        self.path_entry.remove_css_class("error");
        self.up_button.set_sensitive(path.parent().is_some());
        self.side_menu.set_selected_path(path);
    }

    fn show_trash_state(&self) {
        *self.current_path.borrow_mut() = self.trash_path.clone();
        self.path_entry.set_text(&tr("Trash"));
        self.path_entry.set_sensitive(false);
        self.up_button.set_sensitive(false);
        self.side_menu.set_selected_path(&self.trash_path);
    }

    fn go_to_path(self: &Rc<Self>, path: PathBuf) {
        let Some(tab) = self.active_tab() else { return };
        tab.navigate(&path, false);
        self.update_tab_title(&tab);
        self.path_entry.set_sensitive(true);
        self.update_path_state(&path);
    }

    fn go_to_trash(self: &Rc<Self>) {
        let Some(tab) = self.active_tab() else { return };
        tab.go_to_trash();
        self.update_tab_title(&tab);
        self.show_trash_state();
    }

    fn on_up_clicked(&self) {
        let Some(tab) = self.active_tab() else { return };
        if let Some(path) = tab.go_up() {
            self.update_tab_title(&tab);
            self.update_path_state(&path);
        }
    }

    fn on_path_entry_activate(&self, entry: &gtk::Entry) {
        let text = entry.text();
        let path = PathBuf::from(text.trim());
        if text.trim().is_empty() || !self.ctx.file_system.is_dir(&path) {
            entry.add_css_class("error");
            return;
        }
        let Some(tab) = self.active_tab() else { return };
        tab.navigate(&path, true);
        self.update_tab_title(&tab);
        self.update_path_state(&path);
    }

    fn on_view_mode_changed(&self, mode: ViewMode) {
        self.ctx.settings_mut().view_mode = mode;
        self.ctx.save_settings();
        for tab in self.all_tabs() {
            tab.apply_view_mode();
        }
        if let Some(tab) = self.active_tab().filter(|tab| !tab.showing_trash()) {
            self.update_path_state(&tab.current_path());
        }
    }

    /// Debounced: dragging the slider fires many changes.
    fn on_grid_icon_size_changed(self: &Rc<Self>, size: i32) {
        if let Some(source) = self.icon_size_source.take() {
            source.remove();
        }
        let weak = Rc::downgrade(self);
        let source = glib::timeout_add_local_once(GRID_ICON_SIZE_DELAY, move || {
            let Some(this) = weak.upgrade() else { return };
            this.icon_size_source.take();
            this.ctx.settings_mut().set_grid_icon_size(size);
            let size = this.ctx.settings().grid_icon_size;
            for tab in this.all_tabs() {
                tab.set_grid_icon_size(size);
            }
            this.ctx.save_settings();
        });
        *self.icon_size_source.borrow_mut() = Some(source);
    }

    // --- Paste button and job queue -------------------------------------

    fn update_paste_button(self: &Rc<Self>) {
        while let Some(child) = self.paste_slot.first_child() {
            self.paste_slot.remove(&child);
        }
        let pending = self.jobs.borrow().len();
        if pending > 0 {
            self.paste_slot.append(&pending_button(pending));
            return;
        }
        let Some((path, cut)) = self.clipboard.borrow().clone() else {
            return;
        };
        let label = if cut {
            tr("Move file")
        } else {
            tr("Paste the file")
        };
        let button = gtk::Button::with_label(&label);
        button.add_css_class("flat");
        button.set_tooltip_text(Some(&path.to_string_lossy()));
        let weak = Rc::downgrade(self);
        button.connect_clicked(move |_| {
            if let Some(this) = weak.upgrade() {
                this.on_paste_clicked();
            }
        });
        self.paste_slot.append(&button);
    }

    fn on_paste_clicked(self: &Rc<Self>) {
        let Some((source, cut)) = self.clipboard.take() else {
            return;
        };
        self.update_paste_button();
        self.request_paste(&source, cut, None);
    }

    fn request_paste(self: &Rc<Self>, source: &Path, cut: bool, name: Option<&str>) {
        let folder = self.current_path.borrow().clone();
        match paste_destination(self.ctx.file_system.as_ref(), &folder, source, name) {
            Destination::Free(destination) => {
                self.enqueue_job(FileOperationEntity::paste(source, &destination, cut))
            }
            Destination::Taken(taken) => {
                let (weak, source) = (Rc::downgrade(self), source.to_path_buf());
                ask_name(
                    &self.window,
                    &tr("File already exists"),
                    &trf(
                        "\"{name}\" already exists in this folder. Choose a new name.",
                        &[("name", &taken)],
                    ),
                    &if cut { tr("Move") } else { tr("Paste") },
                    &taken,
                    None,
                    move |name| {
                        if let Some(this) = weak.upgrade() {
                            this.request_paste(&source, cut, Some(&name));
                        }
                    },
                );
            }
            Destination::Invalid => {}
        }
    }

    fn request_extract(self: &Rc<Self>, archive: &Path, name: Option<&str>) {
        match extract_destination(self.ctx.file_system.as_ref(), archive, name) {
            Destination::Free(destination) => self.enqueue_job(FileOperationEntity::new(
                FileOperationKind::Extract,
                archive,
                &destination,
            )),
            Destination::Taken(taken) => {
                let (weak, archive) = (Rc::downgrade(self), archive.to_path_buf());
                ask_name(
                    &self.window,
                    &tr("Folder already exists"),
                    &trf(
                        "\"{name}\" already exists in this folder. Choose a name for the extracted folder.",
                        &[("name", &taken)],
                    ),
                    &tr("Extract"),
                    &taken,
                    None,
                    move |name| {
                        if let Some(this) = weak.upgrade() {
                            this.request_extract(&archive, Some(&name));
                        }
                    },
                );
            }
            Destination::Invalid => {}
        }
    }

    fn enqueue_job(self: &Rc<Self>, job: FileOperationEntity) {
        let was_idle = self.jobs.borrow().is_empty();
        self.jobs.borrow_mut().push_back(job);
        self.update_paste_button();
        if was_idle {
            self.run_next_job();
        }
    }

    fn run_next_job(self: &Rc<Self>) {
        let Some(job) = self.jobs.borrow().front().cloned() else {
            return;
        };
        let (file_system, archives) = (self.ctx.file_system.clone(), self.ctx.archives.clone());
        let weak = Rc::downgrade(self);
        glib::spawn_future_local(async move {
            let running = job.clone();
            let result = gio::spawn_blocking(move || {
                run_job(file_system.as_ref(), archives.as_ref(), &running)
            })
            .await
            .unwrap_or_else(|_| Err(DomainError::new("the operation crashed")));
            if let Some(this) = weak.upgrade() {
                this.on_job_done(&job, result);
            }
        });
    }

    fn on_job_done(self: &Rc<Self>, job: &FileOperationEntity, result: DomainResult<()>) {
        self.jobs.borrow_mut().pop_front();
        self.update_paste_button();
        match result {
            Ok(()) => {
                for target in job.refresh_targets() {
                    for tab in self.all_tabs() {
                        tab.refresh_path(&target);
                    }
                }
            }
            Err(error) => {
                let (heading, body) = job.error_messages();
                let body = format!("{}\n\n{error}", trf(body, &[("name", &job.source_name())]));
                show_error(&self.window, &tr(heading), &body);
            }
        }
        self.run_next_job();
    }

    // --- Menu -----------------------------------------------------------

    fn show_parameters(self: &Rc<Self>) {
        let weak = Rc::downgrade(self);
        show_parameters_dialog(&self.window, &self.ctx, move |changes: SettingsChanges| {
            let Some(this) = weak.upgrade() else { return };
            this.apply_theme();
            for tab in this.all_tabs() {
                if changes.hidden_files {
                    tab.reload();
                }
                if changes.single_click_open {
                    tab.apply_click_to_open_setting();
                }
            }
        });
    }

    fn show_about(self: &Rc<Self>) {
        let about = adw::AboutDialog::new();
        about.set_application_name(&tr("File browser"));
        about.set_application_icon(APP.id);
        about.set_version(&APP.build.version_label());
        about.set_developer_name(APP.developer);
        about.set_license_type(gtk::License::Lgpl21);
        about.set_website(APP.website);
        about.set_issue_url(APP.issue_url);
        about.set_debug_info(&APP.build.details());
        about.present(Some(&self.window));
    }
}

/// Paste icon with the number of pending jobs as a badge.
fn pending_button(count: usize) -> gtk::Button {
    let badge = gtk::Label::new(Some(&count.to_string()));
    badge.add_css_class("fb-paste-badge");
    badge.set_halign(gtk::Align::End);
    badge.set_valign(gtk::Align::Start);
    let overlay = gtk::Overlay::new();
    overlay.set_child(Some(&small_icon("edit-paste")));
    overlay.add_overlay(&badge);
    let button = gtk::Button::new();
    button.add_css_class("flat");
    button.set_child(Some(&overlay));
    button.set_sensitive(false);
    button.set_tooltip_text(Some(&trf(
        "{count} pending",
        &[("count", &count.to_string())],
    )));
    button
}
