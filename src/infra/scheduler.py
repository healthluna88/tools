from __future__ import annotations

from dataclasses import dataclass
from typing      import Any, Callable, Optional

from PySide6.QtCore import Signal, QRunnable, QObject, QThreadPool


@dataclass(frozen = True)
class TaskToken:

    request:    int
    generation: int


class TaskScheduler(QObject):

    task_result = Signal(int, int, object)  # request, generation, result
    task_error  = Signal(int, int, object)  # request, generation, error

    class _CallableRunnable(QRunnable):

        def __init__(self, fn: Callable[[], Any], done: Callable[[Any, Optional[BaseException]], None]) -> None:

            super().__init__()

            self._fn   = fn
            self._done = done

        def run(self) -> None:

            try:

                res = self._fn()

                self._done(res, None)

            except BaseException as e:

                self._done(None, e)

    def __init__(self, threadpool: Optional[QThreadPool] = None) -> None:

        super().__init__()

        self._pool = threadpool or QThreadPool.globalInstance()

        self._next_id = 1

    def submit(self, *, generation: int, fn: Callable[[], Any]) -> TaskToken:

        request = self._next_id

        self._next_id += 1

        def done(result: Any, error: Optional[BaseException]) -> None:

            if error is None:

                self.task_result.emit(request, generation, result)

            else:

                self.task_error.emit(request, generation, error)

        self._pool.start(TaskScheduler._CallableRunnable(fn, done))

        return TaskToken(request = request, generation = generation)
