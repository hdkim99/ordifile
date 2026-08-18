# Qt / PySide6 / shiboken6 notice for unsigned prototypes

The Ordifile standalone prototype dynamically bundles Qt shared libraries and plugins
delivered by `PySide6-Essentials 6.11.2` and `shiboken6 6.11.2`. Ordifile does not copy
or modify their source code. Native deployment tooling may rewrite loader metadata in
copied bundle binaries, so final modification and source obligations remain a public-
distribution gate. Ordifile selects the LGPL-3.0 licensing option and itself remains
Apache-2.0.

Copyright in Qt, PySide6, and shiboken6 remains with The Qt Company and respective
contributors. The LGPL-3.0 text is included beside this notice.

Corresponding-source candidates for the exact reviewed version:

- <https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.11.2-src/>
- <https://download.qt.io/official_releases/qt/6.11/6.11.2/single/>

Before any public binary distribution, maintainers must archive and hash the exact
corresponding sources for every included Qt/PySide/shiboken component, inventory Qt's
own third-party notices, and confirm whether a written offer or bundled source is
required. A link alone is not asserted to complete those obligations.

The prototype uses replaceable shared libraries rather than static linking. Users must
be allowed to replace or relink LGPL components, reverse engineer for that purpose,
and run the modified combination. Windows replacement and unsigned macOS replacement
must be clean-machine tested. Signed/hardened macOS replacement and sufficient
installation information remain unresolved, so public signed artifacts are blocked.
