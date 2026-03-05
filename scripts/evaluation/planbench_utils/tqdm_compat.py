"""
Unified tqdm compatibility module.

Provides a transparent tqdm wrapper that falls back to a lightweight
dummy implementation when stdout is not a TTY (e.g., nohup, systemd, CI).
"""
import sys

IS_TTY = sys.stdout.isatty()

if IS_TTY:
    from tqdm import tqdm  # noqa: F401
else:
    class tqdm:
        """Minimal tqdm replacement for non-TTY environments."""

        def __init__(self, iterable=None, total=None, desc="", **kwargs):
            self.iterable = iterable
            self.total = total or (len(iterable) if iterable else 0)
            self.desc = desc
            self.n = 0
            if self.total:
                print(f"{desc}: 0/{self.total}")

        def __iter__(self):
            for item in self.iterable:
                yield item
                self.n += 1
                if self.n % 10 == 0 or self.n == self.total:
                    print(f"{self.desc}: {self.n}/{self.total}")

        def update(self, n=1):
            self.n += n
            if self.n % 10 == 0 or self.n == self.total:
                print(f"{self.desc}: {self.n}/{self.total}")

        def close(self):
            pass

        @staticmethod
        def write(s):
            print(s)
