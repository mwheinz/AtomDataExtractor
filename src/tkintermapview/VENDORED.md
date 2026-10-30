# Vendored TkinterMapView

This is a patched copy of [TkinterMapView](https://github.com/TomSchimansky/TkinterMapView)
1.29 (Creative Commons Zero v1.0 Universal, see `LICENSE.txt`).

## Why

OpenStreetMap's tile servers reject requests using the hard-coded
`User-Agent: TkinterMapView`, so maps stopped loading (issue #29).

## Changes from upstream 1.29

Back-ported the user-agent change from upstream
[PR 165](https://github.com/TomSchimansky/TkinterMapView/pull/165)
(unmerged at the time of vendoring):

* `map_widget.py`: added `TkinterMapView.set_user_agent()` and
  `request_image_from_server()`; tile requests now use `self.user_agent`.
* `offline_loading.py`: `OfflineLoader` takes an optional `user_agent`.

The rest of PR 165's branch (upstream 1.30's switch from `geocoder` to
`geopy`) was deliberately not taken.

If PR 165 is merged and released, this directory can be deleted and
`tkintermapview` added back to `requirements.txt`.
