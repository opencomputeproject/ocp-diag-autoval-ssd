# pyre-unsafe
import queue
import threading
import time
import typing as t

from autoval_ssd.tests.storage_hw_eng.libs.utils.exception_tb import get_traceback_str


class BackgroundPoll(threading.Thread):
    """
    Represents a background poll job.
    """

    def __init__(
        self,
        *,
        function: t.Optional[t.Any],
        args: t.Tuple = (),
        kwargs: t.Optional[dict] = None,
        inter_poll_time: float = 5.0,
        total_polling_period: float = 60.0,
        run_indefinately: bool = False,
    ):
        """
        function (Callable, optional):
            The function to run in the background.
        args (tuple, optional):
            The positonal arguments for the function.
        kwargs (dict, optional):
            The keyword arguments for the function.
        inter_poll_time (float, optional):
            The inter-poll time
        total_polling_period (float, optional):
            The total amount of time to poll.
        run_indefinately (bool, optional):
            Run indefinately -- overrides total_polling_period
        """
        self.function = function if function is not None else (lambda: None)
        self.args = args
        self.kwargs = kwargs if kwargs is not None else {}
        self.inter_poll_time = inter_poll_time
        self.total_polling_period = total_polling_period
        self.gbl_kill = threading.Event()
        self.output_store = []
        self.has_run = False
        self.run_indefinately = run_indefinately

        super().__init__()

    def run(self):
        def _chk_status():
            if self.run_indefinately:
                return not self.gbl_kill.is_set()

            return not self.gbl_kill.is_set() and (
                time.time() - init_poll_time <= self.total_polling_period
            )

        init_poll_time = time.time()
        previous_poll_time = 0.0
        # While no kill event
        while _chk_status():
            # Check if we should poll again.
            time_delta = time.time() - previous_poll_time
            if time_delta > self.inter_poll_time:
                try:
                    val = self.function(*self.args, *self.kwargs)
                except Exception as e:
                    e.traceback_str = get_traceback_str()
                    val = e
                self.output_store.append(val)
                # If so run then set prev. time
                previous_poll_time = time.time()

            # Yield
            time.sleep(0)

        self.has_run = True

    def set_kill(self):
        """
        Set the kill flag.
        """
        self.gbl_kill.set()

    def block_until_end(self):
        """
        Block until the thread has ended.
        """
        while not self.has_run:
            time.sleep(0)


class BackgroundPollingDriver:
    """
    Background Polling Driver
    """

    def __init__(self, logging: t.Optional[t.Callable] = None):
        """ """
        self.queue = queue.Queue()
        self.stop_event = threading.Event()
        self.logging = lambda x: x if logging is None else logging
        self.thread = self.PollingControllerThread(
            self.queue, self.stop_event, self.logging
        )

    class PollingControllerThread(threading.Thread):
        def __init__(
            self,
            queue: queue.Queue,
            stop_event: threading.Event,
            logging: t.Callable[[str], t.Any],
        ):
            """ """
            self.queue = queue
            self.stop_event = stop_event
            self.running_threads = []
            self.logging = logging
            super().__init__()

        def run(self):
            """
            Perform background polling.
            """

            while not self.stop_event.is_set():
                if not self.queue.empty():
                    task = self.queue.get()
                    self.logging(f"Starting Thread:{task.function}")
                    task.start()
                    self.running_threads.append(task)

                self.running_threads = [
                    thread for thread in self.running_threads if thread.is_alive()
                ]

                # Yield
                time.sleep(0)

            # Cleanup
            for thread in self.running_threads:
                thread.set_kill()
                thread.join()

    def start(self):
        """
        Start the background polling driver if it has not already been started.
        """
        if not self.thread.is_alive():
            self.thread.start()

    def stop(self):
        """
        Stop the background polling driver if it is running.
        """
        if self.thread.is_alive():
            self.stop_event.set()
            self.thread.join()

    def num_running_tasks(self):
        """
        Get the number of running threads.
        """
        return len(self.thread.running_threads)

    def num_pending_tasks(self):
        """
        Get the number of running threads.
        """
        return self.queue.qsize()

    def submit(self, task: BackgroundPoll):
        """
        Submit a background polling task to the driver.
        """
        self.queue.put(task)

    def is_running(self):
        """
        Returns if the polling is running.
        """
        return self.thread.is_alive()
