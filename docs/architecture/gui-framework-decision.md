# Desktop GUI framework decision

- Status: Accepted for the first Experimental desktop vertical slice
- Date: 2026-08-18
- Scope: Issue #4; standalone installers remain deferred to Issue #6

## Decision

Use **PySide6 Qt Widgets**, limited to modules distributed by
`PySide6-Essentials`, as an optional `ordifile[gui]` dependency. The existing
`ordifile` installation and CLI remain free of a GUI runtime dependency.

The desktop layer calls only public `ordifile.api` functions. It does not own file
discovery, format detection, vendor parsing, scientific models, sorting, privacy
policy, or workbook generation.

## Compared candidates

| Criterion | Tkinter + ttk | PySide6 Qt Widgets | wxPython |
|---|---|---|---|
| Windows/macOS/Linux | Available with Tcl/Tk, but the module may be omitted by a Python distributor | Official wheels for all three | Supported, but Linux installation may require distro wheels or a source build |
| External file drag/drop | Standard `tkinter.dnd` is intra-application and experimental | Native MIME/URL drop APIs | `wx.FileDropTarget` |
| Accessibility | Keyboard traversal and labels; cross-platform assistive-technology coverage is not explicit | Keyboard focus plus documented MSAA, macOS Accessibility, and AT-SPI backends | Keyboard traversal; extended `wx.Accessible` support is Windows-specific |
| Testability | Event generation, no dedicated GUI test module | QtTest, QTest, QSignalSpy, and model testing | UIActionSimulator, with platform limitations |
| License | PSF plus permissive Tcl/Tk terms | LGPLv3/GPL/commercial | wxWindows Library Licence 3.1 |
| Dependency size | Lowest | Highest; Essentials wheels are roughly 55–106 MiB depending on platform | Smaller wheels, but uneven Linux distribution |
| Packaging path | Widely supported by bundlers | Official deployment tooling plus third-party bundlers | Supported by third-party bundlers |

Tkinter is the lightest option, but it does not meet the required external
file-manager drag/drop workflow without another native extension. wxPython has a
smaller binary footprint and native widgets, but its Linux wheel availability and
cross-platform accessibility evidence are weaker. PySide6 is selected because it is
the only candidate with first-party evidence for external file drop, assistive
technology on all target desktop families, dedicated UI testing, and maintained
cross-platform deployment tooling.

## Dependency and license boundary

- `pip install ordifile` does not install Qt.
- `pip install ordifile[gui]` installs the exact reviewed
  `PySide6-Essentials==6.11.2` baseline. Its required `shiboken6` companion is pinned
  transitively to the same version by that distribution.
- The current implementation imports only QtCore, QtGui, and QtWidgets from
  Essentials. QtTest remains an available framework capability but is not currently
  imported by Ordifile.
- The Python wheel does not bundle Qt libraries. Future standalone bundles must
  preserve LGPL notices, license text, corresponding-source availability, and user
  relinking/replacement rights. That separate redistribution gate belongs to Issue
  #6.
- Vendor applications, SDKs, DLLs, executables, and scientific fixtures are never GUI
  dependencies.

## Application boundary

The first slice uses a framework-neutral controller and immutable state, plus a Qt
worker that calls the synchronous public API outside the UI thread. Conversion does
not require a network connection and has no telemetry. Forced cancellation is omitted
until a public cooperative cancellation contract can preserve workbook transaction
safety.

Preview and conversion never maintain a GUI-owned adapter list. A synthetic YoungIn
Result Table regression demonstrates that a newly registered Experimental adapter is
detected through `inspect_inputs()` and produces the same scientific workbook sheets
through the desktop service and direct public `convert()` call, without a desktop
vendor branch.

## Evidence

- [Python tkinter documentation](https://docs.python.org/3.14/library/tkinter.html)
  and [tkinter.dnd boundary](https://docs.python.org/3.14/library/tkinter.dnd.html)
- [PySide6 package metadata](https://pypi.org/project/PySide6/6.11.2/) and
  [PySide6 Essentials](https://pypi.org/project/PySide6-Essentials/6.11.2/)
- [Qt for Python drag/drop example](https://doc.qt.io/qtforpython-6/examples/example_widgets_draganddrop_dropsite.html)
- [Qt keyboard focus](https://doc.qt.io/qtforpython-6/overviews/qtwidgets-focus.html),
  [QAccessible](https://doc.qt.io/qtforpython-6/PySide6/QtGui/QAccessible.html), and
  [QtTest](https://doc.qt.io/qtforpython-6/PySide6/QtTest/index.html)
- [Qt for Python deployment](https://doc.qt.io/qtforpython-6/deployment/index.html)
  and [Qt LGPL obligations](https://www.qt.io/development/open-source-lgpl-obligations)
- [wxPython downloads](https://wxpython.org/pages/downloads/),
  [wx.FileDropTarget](https://docs.wxpython.org/wx.FileDropTarget.html), and
  [wx.Accessible](https://docs.wxpython.org/wx.Accessible.html)

Cold-start time, frozen bundle size, Wayland drag/drop, and assistive-technology
behavior on physical Windows and macOS systems remain packaging-stage measurements.
