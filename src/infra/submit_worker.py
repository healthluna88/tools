from __future__ import annotations

import requests

from PySide6.QtCore import QObject, Signal, QRunnable


class SubmitSignals(QObject):

    started = Signal()
    succeeded = Signal(object)  # response json / text
    failed = Signal(str)
    finished = Signal()


class AnnotationSubmitWorker(QRunnable):

    def __init__(self, url: str, payload: dict, timeout_s: int = 15):

        super().__init__()

        self.url = url
        self.payload = payload
        self.timeout_s = timeout_s
        self.signals = SubmitSignals()

    def run(self) -> None:
        self.signals.started.emit()
        try:

            print('AnnotationSubmitWorker.run', self.url, self.payload)
            resp = requests.post(self.url, json = self.payload, timeout = self.timeout_s)

            print('AnnotationSubmitWorker.run', resp)

            if 200 <= resp.status_code < 300:
                try:
                    self.signals.succeeded.emit(resp.json())
                except Exception:
                    self.signals.succeeded.emit(resp.text)
            else:
                # keep message short but actionable
                msg = f"HTTP {resp.status_code}: {resp.text[:400]}"
                self.signals.failed.emit(msg)
        except Exception as e:
            self.signals.failed.emit(str(e))
        finally:
            self.signals.finished.emit()
