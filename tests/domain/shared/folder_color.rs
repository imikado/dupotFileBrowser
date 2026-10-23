use serde_json::json;

use dupot_file_browser::domain::shared::folder_color::{
    PALETTE, color_from_nemo_icon_uri, colored_path_map, nemo_icon_uri, with_colored_path,
};

#[test]
fn nemo_uri_round_trip_for_every_palette_color() {
    for (_, hex) in PALETTE {
        let uri = nemo_icon_uri(hex).unwrap();
        assert_eq!(color_from_nemo_icon_uri(&uri), Some(hex));
    }
    assert_eq!(nemo_icon_uri("#123456"), None);
    assert_eq!(
        nemo_icon_uri("#50C16F").as_deref(),
        Some("file:///usr/share/icons/Mint-Y/places/48/folder.png")
    );
}

#[test]
fn reads_nemo_variants_and_rejects_others() {
    assert_eq!(
        color_from_nemo_icon_uri("file:///usr/share/icons/Mint-Y-Red/places/32@2x/folder-open.png"),
        Some("#f54f54")
    );
    assert_eq!(
        color_from_nemo_icon_uri("file:///usr/share/icons/Mint-L-Red/places/48/folder.png"),
        None
    );
    assert_eq!(color_from_nemo_icon_uri("file:///home/me/custom.png"), None);
    assert_eq!(
        color_from_nemo_icon_uri("file:///usr/share/icons/Mint-Y/places/big/folder.png"),
        None
    );
}

#[test]
fn sidecar_map_skips_malformed_items() {
    let sidecar = json!({"coloredPathList": [
        {"name": "a.txt", "color": "#5294e2"},
        {"name": "b.txt"},
        "junk"
    ]});
    let map = colored_path_map(&sidecar);
    assert_eq!(map.len(), 1);
    assert_eq!(map["a.txt"], "#5294e2");
    assert!(colored_path_map(&json!([])).is_empty());
}

#[test]
fn tagging_replaces_and_untagging_removes() {
    let sidecar = json!({"other": 1, "coloredPathList": [{"name": "a", "color": "#5294e2"}]});
    let retagged = with_colored_path(&sidecar, "a", Some("#f54f54")).unwrap();
    assert_eq!(colored_path_map(&retagged)["a"], "#f54f54");
    assert_eq!(retagged["other"], 1);

    let untagged = with_colored_path(&retagged, "a", None).unwrap();
    assert!(colored_path_map(&untagged).is_empty());
    assert_eq!(
        with_colored_path(&untagged, "a", None),
        None,
        "nothing to remove"
    );
}
