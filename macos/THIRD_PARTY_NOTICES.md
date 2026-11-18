# Copyright, source and distribution

macOS edition only: GPL-3.0-only. Copyright (C) 2026 iOS Location Studio contributors.
The repository root license and Windows edition are unchanged.

Includes unmodified aur3l14no/accessory-location, GPL-3.0-only:
https://github.com/aur3l14no/accessory-location
Pinned upstream commit: 8a13296a3d81dae18ad4481e7a9eca913c2c644f.
Full tracked upstream source, copyright notices, license, protocol references and tests
are retained in vendor/accessory-location. No identity files are included.
The Mac controller uses this pinned engine and bundles its source; it does not
relicense the engine as MIT. See vendor/accessory-location/docs/sources.md for
original protocol research acknowledgements.

Runtime dependencies: PySide6/Qt (LGPL-3.0/GPL/commercial options; this Mac edition
uses GPL-compatible open-source distribution), pymobiledevice3 (GPL-3.0),
cryptography (Apache-2.0 OR BSD-3-Clause), and their transitive dependencies.
PyInstaller is GPL with its bootloader exception. The lockfile records exact versions.
Build output retains dependency license metadata through PyInstaller. Before public
binary release, audit the packaged dependency notices, including Qt and its plugins;
independent legal/security review has NOT occurred.

GPL distribution: give recipients GPLv3 text, notices, modification notices and the
complete corresponding source for the exact distributed build, including build scripts
and pinned dependencies required to rebuild. Do not impose additional restrictions.
For binary download releases provide equivalent source access alongside the binary
(GPLv3 section 6); a link to mutable upstream main is not sufficient.
The supplied source archive is the application's tracked source at HEAD, not a complete
automatic archive of every transitive dependency. Collect matching dependency source
and notices before public distribution. No public binary release is authorized here.
Reference: https://www.gnu.org/licenses/gpl-3.0.html (sections 4–6).

MFi certificates/keys and pairing records are neither source nor bundled assets.
The optional upstream importer is retained for inspection; the GUI never invokes it.
User-supplied identity authorization, revocation and device acceptance remain separate.

Offline overview data: Natural Earth ne_110m_land (public domain), by Natural Earth contributors.
Source: https://github.com/nvkelso/natural-earth-vector/blob/master/geojson/ne_110m_land.geojson
Terms: https://www.naturalearthdata.com/about/terms-of-use/
Processed 2026-11-17: retained polygon rings, rounded lon/lat to 3 decimals, removed feature metadata.
Shipped as src/location_studio_mac/assets/world-land.json. Overview only; not a street/navigation map.
