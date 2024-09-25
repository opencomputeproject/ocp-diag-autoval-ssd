# pyre-unsafe
from concurrent import futures


class MockExecutor(futures.Executor):
    def submit(self, f, *args, **kwargs):
        future = futures.Future()
        future.set_result(f(*args, **kwargs))
        return future

    def wait(self, futures=None):
        pass

    def shutdown(self, wait=True):
        pass
