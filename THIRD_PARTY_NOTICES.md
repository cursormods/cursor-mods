# Third-party notices

The project's MIT license covers Cursor Mods code and original assets.
Third-party components retain their own copyrights and licenses.

| Component | License | Source / notices |
| --- | --- | --- |
| oneko sprite | MIT | [adryd325/oneko.js](https://github.com/adryd325/oneko.js), [notice](assets/ONEKO-LICENSE.txt) |
| Qt, PySide6, Shiboken6 | LGPL 3.0 (open-source distribution) | [Qt for Python](https://code.qt.io/cgit/pyside/pyside-setup.git/), [Qt](https://code.qt.io/cgit/qt/), [license texts](licenses/qt) |
| Pillow | MIT-CMU and bundled-library notices | [Pillow](https://github.com/python-pillow/Pillow), [notice](licenses/pillow/LICENSE) |
| keyboard | MIT | [keyboard](https://github.com/boppreh/keyboard), [notice](licenses/keyboard/LICENSE.txt) |
| pywin32 | Package-specific permissive licenses | [pywin32](https://github.com/mhammond/pywin32), [notices](licenses/pywin32) |
| Python | PSF and included notices | [Python](https://www.python.org/), [notice](licenses/python/LICENSE.txt) |
| PyInstaller bootloader | GPL with distribution exception | [PyInstaller](https://github.com/pyinstaller/pyinstaller), [notice](licenses/pyinstaller/COPYING.txt) |

Qt and PySide are used as unmodified shared libraries. Their licenses permit
replacement or modification under the applicable terms. Build from source using
the README instructions to use your own compatible Qt/PySide build. Exact Python
package versions are recorded in `requirements.txt`.

Distributors must preserve the relevant notices and meet the source-availability
and relinking requirements of the libraries they ship. Before distributing a
binary, check the licenses and bundled third-party components of that exact build.
