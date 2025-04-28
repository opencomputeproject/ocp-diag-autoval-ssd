# pyre-unsafe
import typing as t

from autoval_ssd.tests.storage_hw_eng.libs.utils.exception_tb import get_traceback_str


class TestTask:
    """
    Class to denote a task to run.
    """

    def __init__(
        self,
        func: t.Callable,
        args: t.Optional[str] = None,
        kwargs: t.Optional[t.Dict] = None,
        metadata: t.Optional[t.Dict] = None,
        can_run: t.Optional[
            t.Callable[[t.List["TestTask"], t.List["TestTask"]], bool]
        ] = None,
    ):
        """
        Create a Task

        Params:
            func (Callable):
                The function to run.
            args (list, optional):
                The positional arguments for the function.
            kwargs (dict, optional):
                The keyword arguments for the function.
            metadata (dict, optional):
                Any associated metadata for this task.
            can_run (Callable[List[Task], List[Task], bool], optional):
                Function which tests if a Task can be run.
                First list is the tasks that have been submitted.
                The second is the list of tasks currently unsubmitted.
        """
        self.func = func
        self.args = [] if args is None else args
        self.kwargs = {} if kwargs is None else kwargs
        self.metadata = {} if metadata is None else metadata
        self.can_run = (lambda x, y: True) if can_run is None else can_run

        self.has_run = False
        self.exception = None
        self.traceback = None
        self.result = None

    def run(self):
        try:
            self.result = self.func(*self.args, **self.kwargs)
        except Exception as e:
            self.exception = e
            self.traceback = get_traceback_str()
        finally:
            self.has_run = True
