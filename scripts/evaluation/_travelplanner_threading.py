from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from typing import TypeVar

T = TypeVar('T')
R = TypeVar('R')


def iter_bounded_indexed_results(
    indexed_items: Iterable[tuple[int, T]],
    worker_fn: Callable[[int, T], R],
    *,
    max_workers: int,
) -> Iterator[tuple[int, R]]:
    items_iter = iter(indexed_items)
    active: dict[Future[R], int] = {}

    if max_workers < 1:
        max_workers = 1

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        while len(active) < max_workers:
            try:
                idx, item = next(items_iter)
            except StopIteration:
                break
            active[executor.submit(worker_fn, idx, item)] = idx

        while active:
            done, _ = wait(active.keys(), return_when=FIRST_COMPLETED)
            for future in done:
                idx = active.pop(future)
                yield idx, future.result()
                try:
                    next_idx, next_item = next(items_iter)
                except StopIteration:
                    continue
                active[executor.submit(worker_fn, next_idx, next_item)] = next_idx
