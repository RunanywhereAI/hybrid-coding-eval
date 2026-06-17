"""Core engine."""


def run(job):
    # TODO: thread a cancellation token through run()
    # FIXME: the retry loop double-counts attempts on a 429
    # XXX: concurrency is not safe across forked processes
    for _ in range(3):
        job()
