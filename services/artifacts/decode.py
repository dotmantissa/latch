"""Fixed isolated PNG decoder entry point; invoked with Python -I and no credentials."""

import ctypes
import errno
import io
import os
import resource
import sys
import warnings

MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 12_000_000


def restrict():
    """Deny new file handles, networking, children and exec before touching image bytes."""
    resource.setrlimit(resource.RLIMIT_AS, (384 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (6, 7))
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_BYTES,) * 2)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(38, 1, 0, 0, 0) != 0:  # PR_SET_NO_NEW_PRIVS
        raise RuntimeError("SANITIZER_RESTRICTION_FAILED")
    sec = ctypes.CDLL("libseccomp.so.2", use_errno=True)
    sec.seccomp_init.argtypes = [ctypes.c_uint32]
    sec.seccomp_init.restype = ctypes.c_void_p
    sec.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    sec.seccomp_syscall_resolve_name.restype = ctypes.c_int
    sec.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
    sec.seccomp_load.argtypes = [ctypes.c_void_p]
    sec.seccomp_release.argtypes = [ctypes.c_void_p]
    ctx = sec.seccomp_init(0x00050000 | errno.EPERM)  # SCMP_ACT_ERRNO
    if not ctx:
        raise RuntimeError("SANITIZER_RESTRICTION_FAILED")
    try:
        # Only inherited stdin/stdout/stderr exist. No open, socket, clone, exec, ptrace,
        # filesystem mutations or io_uring. Memory protection cannot grant new authority.
        for name in (
            "read", "write", "readv", "writev", "close", "fstat", "lseek", "pread64",
            "brk", "mmap", "mprotect", "munmap", "mremap", "madvise", "futex",
            "rt_sigaction", "rt_sigprocmask", "rt_sigreturn", "sigaltstack",
            "clock_gettime", "gettimeofday", "getrusage", "getpid", "gettid",
            "sched_yield", "restart_syscall", "exit", "exit_group",
        ):
            number = sec.seccomp_syscall_resolve_name(name.encode())
            if number < 0 or sec.seccomp_rule_add(ctx, 0x7FFF0000, number, 0) != 0:
                raise RuntimeError("SANITIZER_RESTRICTION_FAILED")
        if sec.seccomp_load(ctx) != 0:
            raise RuntimeError("SANITIZER_RESTRICTION_FAILED")
    finally:
        sec.seccomp_release(ctx)


def main():
    # Load the fixed PNG codec and zlib before file access is denied. Never call Image.init(),
    # which would import unrelated supplier-selected decoders after restriction.
    from PIL import Image, PngImagePlugin

    if sys.argv[1:] == ["--probe"]:
        import socket

    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    warnings.simplefilter("error", Image.DecompressionBombWarning)
    assert PngImagePlugin.PngImageFile.format == "PNG"
    restrict()
    if sys.argv[1:] == ["--probe"]:
        # Boundary check uses the exact production filter, with no image or secret input.
        blocked = 0
        for action in (
            lambda: os.open("/etc/hostname", os.O_RDONLY),
            lambda: socket.socket(socket.AF_INET, socket.SOCK_STREAM),
            lambda: os.fork(),
            lambda: os.execve("/bin/true", ["/bin/true"], {}),
        ):
            try:
                action()
            except PermissionError:
                blocked += 1
        if blocked != 4:
            raise RuntimeError("SANITIZER_RESTRICTION_FAILED")
        sys.stdout.buffer.write(b"restricted\n")
        return
    if sys.argv[1:]:
        raise ValueError("SANITIZER_ARGUMENTS_INVALID")
    data = sys.stdin.buffer.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("SANITIZER_INPUT_LIMIT")
    with Image.open(io.BytesIO(data), formats=["PNG"]) as image:
        width, height = image.size
        if (not 1 <= width <= 4000 or not 1 <= height <= 16000
                or width * height > MAX_PIXELS or getattr(image, "n_frames", 1) != 1):
            raise ValueError("SANITIZER_IMAGE_LIMIT")
        image.verify()  # Includes PNG chunk CRCs; the header alone is never sufficient.
    with Image.open(io.BytesIO(data), formats=["PNG"]) as image:
        image.load()
        if image.mode not in ("RGB", "RGBA") or "transparency" in image.info:
            raise ValueError("SANITIZER_COLOR_MODE")
        if image.mode == "RGBA" and image.getextrema()[3] != (255, 255):
            raise ValueError("SANITIZER_TRANSPARENCY")
        rgb = image.convert("RGB")
        # Allocate a new raster to discard text, EXIF, profiles and every source info entry.
        clean = Image.new("RGB", rgb.size)
        clean.paste(rgb)
        output = io.BytesIO()
        clean.save(output, format="PNG", optimize=False, compress_level=6)
    value = output.getvalue()
    if len(value) > MAX_BYTES:
        raise ValueError("SANITIZER_OUTPUT_LIMIT")
    sys.stdout.buffer.write(value)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # No decoder traceback or supplier text is retained. Nonzero means quarantine only.
        raise SystemExit(1) from None
