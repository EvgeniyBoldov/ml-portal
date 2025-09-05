# gen_all_code/__main__.py
from __future__ import annotations

import argparse
import os
from pathlib import Path

DEFAULT_EXCLUDED_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", "node_modules", ".venv", "venv",
    ".idea", ".mypy_cache", ".pytest_cache", ".tox", ".DS_Store"
}
DEFAULT_EXCLUDED_FILES = {"all_code.txt"}

def is_binary_file(path: Path, probe_size: int = 4096) -> bool:
    """Грубая, но быстрая проверка: null-байт или не декодируется в UTF-8."""
    try:
        with path.open("rb") as f:
            chunk = f.read(probe_size)
        if b"\x00" in chunk:
            return True
        try:
            chunk.decode("utf-8")
            return False
        except UnicodeDecodeError:
            return True
    except Exception:
        # На всякий случай считаем файл неподходящим
        return True

def iter_text_files(
    root: Path,
    follow_symlinks: bool = False,
    max_bytes: int | None = None,
    excluded_dirs: set[str] | None = None,
    excluded_files: set[str] | None = None,
):
    excluded_dirs = set(excluded_dirs or [])
    excluded_files = set(excluded_files or [])
    # Проходим каталогами с возможностью "обрезать" исключённые
    for dirpath, dirnames, filenames in os.walk(root, followlinks=follow_symlinks):
        # Удаляем исключённые папки из обхода
        dirnames[:] = [d for d in dirnames if d not in excluded_dirs]
        for name in filenames:
            if name in excluded_files:
                continue
            p = Path(dirpath) / name
            # Пропустим симлинки на файлы, если не просили их обходить
            if p.is_symlink() and not follow_symlinks:
                continue
            # Ограничение по размеру, если задано
            if max_bytes is not None:
                try:
                    if p.stat().st_size > max_bytes:
                        continue
                except OSError:
                    continue
            # Пропускаем бинарники
            if is_binary_file(p):
                continue
            yield p

def write_bundle(files: list[Path], root: Path, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="\n") as out:
        for file_path in sorted(files, key=lambda x: x.relative_to(root).as_posix()):
            rel = file_path.relative_to(root).as_posix()
            out.write(f"### {rel}\n")
            try:
                with file_path.open("r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        out.write(line)
            except Exception as e:
                out.write(f"<<Ошибка чтения файла: {e}>>\n")
            # Пустая строка-разделитель после содержимого каждого файла
            out.write("\n")

def main():
    parser = argparse.ArgumentParser(
        description="Собрать все текстовые файлы из директории в один all_code.txt."
    )
    parser.add_argument(
        "root",
        help="Корневая директория для обхода (например, app/).",
    )
    parser.add_argument(
        "-o", "--output",
        default="all_code.txt",
        help="Путь к результирующему файлу (по умолчанию: ./all_code.txt).",
    )
    parser.add_argument(
        "--follow-symlinks", action="store_true",
        help="Следовать по симлинкам (по умолчанию выключено).",
    )
    parser.add_argument(
        "--max-bytes", type=int, default=None,
        help="Максимальный размер файла в байтах для включения (по умолчанию без лимита).",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"Не найдена директория: {args.root}")

    out_path = Path(args.output).resolve()

    # Не включать сам файл-результат, если он находится внутри root
    excluded_files = set(DEFAULT_EXCLUDED_FILES)
    excluded_dirs = set(DEFAULT_EXCLUDED_DIRS)
    excluded_files.add(out_path.name)

    files = list(
        iter_text_files(
            root=root,
            follow_symlinks=args.follow_symlinks,
            max_bytes=args.max_bytes,
            excluded_dirs=excluded_dirs,
            excluded_files=excluded_files,
        )
    )
    write_bundle(files, root=root, out_path=out_path)
    print(f"Готово: {out_path}")

if __name__ == "__main__":
    main()
