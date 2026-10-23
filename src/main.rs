use adw::prelude::*;
use dupot_file_browser::infrastructure::ui::app_window;

fn main() -> gtk::glib::ExitCode {
    app_window::build_application().run()
}
