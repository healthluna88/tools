from __future__ import annotations

from dataclasses import dataclass

from typing import Any, Callable, Optional

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class Scheduler(QObject):

    task_result = Signal(int, int, object)  # request, generation, result
    task_error  = Signal(int, int, object)  # request, generation, error

    @dataclass(frozen=True)
    class Token:

        request:    int
        generation: int

    class _CallableRunnable(QRunnable):

        def __init__(self, fn: Callable[[], Any], done: Callable[[Any, Optional[BaseException]], None]) -> None:

            super().__init__()

            self._fn   = fn
            self._done = done

        def run(self) -> None:

            try:

                result = self._fn()

                self._done(result, None)

            except BaseException as error:

                self._done(None, error)

    def __init__(self, threadpool: Optional[QThreadPool] = None) -> None:

        super().__init__()

        self._pool = threadpool or QThreadPool.globalInstance()
        self._next_id = 1

    def submit(self, *, fn: Callable[[], Any], generation: int = 0) -> Token:

        request = self._next_id

        self._next_id += 1

        def _done(result: Any, error: Optional[BaseException]) -> None:

            if error is None:

                self.task_result.emit(request, generation, result)

            else:

                self.task_error.emit(request, generation, error)

        self._pool.start(Scheduler._CallableRunnable(fn, _done))

        return Scheduler.Token(request = request, generation = generation)
