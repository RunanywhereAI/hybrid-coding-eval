"""Small helpers."""


def chunked(seq, n):
    # TODO: accept any iterable, not just a list
    return [seq[i : i + n] for i in range(0, len(seq), n)]
