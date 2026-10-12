"""Bounded local WAV cache; hashed keys, no transcript metadata, 24-hour expiry."""
import os
from pathlib import Path
import tempfile
import time


class AudioCache:
    def __init__(self, root, max_bytes=128 * 1024 * 1024, ttl=86400):
        self.root = Path(root)
        self.max_bytes = max_bytes
        self.ttl = ttl

    def get(self, key):
        path = self.root / (key + '.wav')
        try:
            stat = path.stat()
            if time.time() - stat.st_mtime > self.ttl or stat.st_size > 12_000_000:
                path.unlink(missing_ok=True)
                return None
            result = path.read_bytes()
            os.utime(path, None)
            return result
        except FileNotFoundError:
            return None

    def put(self, key, audio):
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        now = time.time()
        files = []
        for path in self.root.glob('*.wav'):
            stat = path.stat()
            if now - stat.st_mtime > self.ttl:
                path.unlink(missing_ok=True)
            else:
                files.append((stat.st_mtime, stat.st_size, path))
        size = sum(row[1] for row in files)
        for _, length, path in sorted(files):
            if size + len(audio) <= self.max_bytes:
                break
            path.unlink(missing_ok=True)
            size -= length
        if len(audio) > self.max_bytes:
            return
        fd, temporary = tempfile.mkstemp(dir=self.root)
        try:
            with os.fdopen(fd, 'wb') as output:
                output.write(audio)
            os.replace(temporary, self.root / (key + '.wav'))
        finally:
            Path(temporary).unlink(missing_ok=True)
