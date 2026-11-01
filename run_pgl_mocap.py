"""Точка входа PGL Mocap (используется и для запуска из исходников, и для сборки exe)."""
import sys


def _redirect_output():
    # В оконном exe нет консоли: пишем ошибки в лог рядом с настройками
    if getattr(sys, "frozen", False):
        try:
            from pglmocap.paths import settings_dir
            log = open(settings_dir() / "pgl_mocap.log", "a", encoding="utf-8", buffering=1)
            sys.stdout = sys.stderr = log
        except Exception:
            pass


def _selftest():
    from pglmocap.paths import exe_dir
    import selftest
    path = exe_dir() / "pgl_mocap_selftest.txt"
    with open(path, "w", encoding="utf-8", buffering=1) as f:
        ok = selftest.run(lambda s: f.write(s + "\n"))
    return 0 if ok else 1


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    _redirect_output()
    from pglmocap.gui import main
    main()
