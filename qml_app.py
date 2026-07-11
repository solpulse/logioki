"""Unified Qt Quick application entry point."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QUrl
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine

import diagnostics
from application_view_model import ApplicationViewModel

APP_ID = "io.github.solpulse.Logioki"


def _resource_dir() -> Path:
    source = Path(__file__).resolve().parent / "logioki_ui" / "qml"
    if source.is_dir():
        return source
    return Path(sys.prefix) / "share" / "logioki" / "qml"


def application_icon() -> QIcon:
    source = Path(__file__).resolve().parent / "data" / f"{APP_ID}.svg"
    candidates = (source, Path(sys.prefix) / "share/icons/hicolor/scalable/apps" / f"{APP_ID}.svg")
    return next(
        (QIcon(str(path)) for path in candidates if path.is_file()), QIcon.fromTheme(APP_ID)
    )


def main(argv=None) -> int:
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Fusion")
    app = QGuiApplication(list(sys.argv if argv is None else argv))
    QCoreApplication.setApplicationName("Logioki")
    QCoreApplication.setOrganizationName("Solpulse")
    QCoreApplication.setOrganizationDomain("github.com/solpulse")
    QGuiApplication.setDesktopFileName(APP_ID)
    app.setWindowIcon(application_icon())
    diagnostics.configure_logging()
    engine = QQmlApplicationEngine()
    qml_dir = _resource_dir()
    engine.addImportPath(str(qml_dir.parent))
    view_model = ApplicationViewModel()
    engine.setInitialProperties({"vm": view_model})
    engine.load(QUrl.fromLocalFile(str(qml_dir / "Main.qml")))
    if not engine.rootObjects():
        view_model.shutdown()
        return 1
    app.aboutToQuit.connect(view_model.shutdown)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
