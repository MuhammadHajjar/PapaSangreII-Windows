"""ChaCha20 (RFC 8439), vectorised with numpy - the game data pack's cipher.

Whole files at a time: every 64-byte block of the keystream is computed at
once, one numpy column per block, so a megabyte takes milliseconds and no
third-party crypto library is needed.  Encryption and decryption are the same
operation.
"""

from __future__ import annotations

import numpy as np

_CONST = np.array([0x61707865, 0x3320646e, 0x79622d32, 0x6b206574], dtype=np.uint32)


def _quarter(x: np.ndarray, t: np.ndarray, a: int, b: int, c: int, d: int) -> None:
    """One quarter round on whole rows, in place (`t` is scratch)."""
    xa, xb, xc, xd = x[a], x[b], x[c], x[d]
    for p, q, r, n in ((xa, xb, xd, 16), (xc, xd, xb, 12), (xa, xb, xd, 8), (xc, xd, xb, 7)):
        p += q
        r ^= p
        np.right_shift(r, 32 - n, out=t)
        np.left_shift(r, n, out=r)
        r |= t


def keystream(key: bytes, nonce: bytes, nbytes: int, counter: int = 1) -> np.ndarray:
    """`nbytes` of ChaCha20 keystream for a 32-byte key and 12-byte nonce."""
    if len(key) != 32 or len(nonce) != 12:
        raise ValueError('ChaCha20 wants a 32-byte key and a 12-byte nonce')
    blocks = max(1, -(-nbytes // 64))
    init = np.empty((16, blocks), dtype=np.uint32)
    init[0:4] = _CONST[:, None]
    init[4:12] = np.frombuffer(key, dtype='<u4')[:, None]
    init[12] = (np.arange(blocks, dtype=np.uint64) + counter).astype(np.uint32)
    init[13:16] = np.frombuffer(nonce, dtype='<u4')[:, None]
    x = init.copy()
    t = np.empty(blocks, dtype=np.uint32)
    with np.errstate(over='ignore'):
        for _ in range(10):
            _quarter(x, t, 0, 4, 8, 12)
            _quarter(x, t, 1, 5, 9, 13)
            _quarter(x, t, 2, 6, 10, 14)
            _quarter(x, t, 3, 7, 11, 15)
            _quarter(x, t, 0, 5, 10, 15)
            _quarter(x, t, 1, 6, 11, 12)
            _quarter(x, t, 2, 7, 8, 13)
            _quarter(x, t, 3, 4, 9, 14)
        x += init
    # block-major, little-endian words
    return np.ascontiguousarray(x.T, dtype='<u4').view(np.uint8).reshape(-1)[:nbytes]


def crypt(key: bytes, nonce: bytes, data, counter: int = 1) -> bytes:
    """Encrypt or decrypt `data` (bytes-like)."""
    buf = np.frombuffer(data, dtype=np.uint8)
    if buf.size == 0:
        return b''
    return (buf ^ keystream(key, nonce, buf.size, counter)).tobytes()
