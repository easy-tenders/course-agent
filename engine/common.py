#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Общее для всех скриптов движка: сеть, временные папки, чтение документов.

Работает на Windows, macOS и Linux. Внешних библиотек не требует; если для
чтения PDF в системе нет ни одного инструмента, скрипт останавливается с
внятным сообщением — что именно поставить.
"""
import html as _html
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

# Единый User-Agent. Портал отдаёт публичную часть без ЭЦП и без cookie.
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " \
     "(KHTML, like Gecko) Chrome/120 Safari/537.36"

# Правило базы: между запросами к порталу — пауза. Держим её здесь, а не
# россыпью time.sleep по скриптам.
PAUSE = 0.35
_last_request = 0.0


def base_dir():
    """Корень базы — на два уровня выше этого файла (engine/common.py)."""
    return Path(__file__).resolve().parent.parent


def cache_dir(tag):
    """Папка под промежуточные файлы прогона. Не в базе: в базу попадает
    только то, что записано операцией."""
    d = Path(tempfile.gettempdir()) / "tender-agent" / tag
    d.mkdir(parents=True, exist_ok=True)
    return d


def fetch(url, dest, min_size=0):
    """Скачать url в dest. Уже скачанное не трогаем — прогон можно продолжить
    с того места, где оборвался. Возвращает True, если файл на месте."""
    global _last_request
    dest = Path(dest)
    if dest.exists() and dest.stat().st_size > min_size:
        return True
    wait = PAUSE - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            body = resp.read()
    except (urllib.error.URLError, OSError) as e:
        print(f"  не скачалось: {url} — {e}", file=sys.stderr)
        _last_request = time.monotonic()
        return False
    _last_request = time.monotonic()
    dest.write_bytes(body)
    return dest.stat().st_size > min_size


def read(url):
    """Скачать и вернуть как текст, без файла на диске."""
    global _last_request
    wait = PAUSE - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as resp:
        body = resp.read()
    _last_request = time.monotonic()
    return body.decode("utf-8", "ignore")


# ── чтение документов ────────────────────────────────────────────────────────
# Портал отдаёт протоколы двумя разными форматами:
#   PDF   — протокол об итогах (ЗЦП, аукцион, конкурс);
#   HTML  — закупка из одного источника (ИОИ), другой род документа.
# Расширение файла об этом не говорит — смотрим на содержимое.

MISSING_PDF_TOOL = """
Не могу прочитать PDF: в системе нет ни pdftotext, ни библиотеки pypdf.
Поставь любое из двух:
  pip install pypdf                     — проще, ставится куда угодно
  poppler (даёт pdftotext)              — Windows: winget install poppler
                                          macOS:   brew install poppler
"""


def kind_of(path):
    """'pdf' | 'html' | 'unknown' — по сигнатуре файла, не по имени."""
    head = Path(path).open("rb").read(512).lstrip()
    if head[:4] == b"%PDF":
        return "pdf"
    if head[:1] == b"<":
        return "html"
    return "unknown"


def _pdftotext_binary():
    """pdftotext, если он есть в PATH. Абсолютных путей не зашиваем —
    на каждой машине он лежит по-своему."""
    return shutil.which("pdftotext")


def pdf_text(path):
    """Текст из PDF с сохранением колоночной раскладки — парсеры протоколов
    разбирают строки по двум и более пробелам, раскладка им нужна."""
    exe = _pdftotext_binary()
    if exe:
        out = Path(str(path) + ".txt")
        subprocess.run([exe, "-layout", str(path), str(out)], capture_output=True)
        if out.exists():
            return out.read_text(encoding="utf-8", errors="ignore")
    try:
        from pypdf import PdfReader
    except ImportError:
        raise RuntimeError(MISSING_PDF_TOOL.strip())
    reader = PdfReader(str(path))
    return "\n".join(p.extract_text(extraction_mode="layout") or ""
                     for p in reader.pages)


def _cell(s):
    return _html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s))).strip()


def html_text(source):
    """HTML-документ в колоночный текст: ячейки таблицы разделены двумя
    пробелами — тот же вид, что даёт `pdftotext -layout`, поэтому парсеры
    протоколов работают с обоими форматами одинаково."""
    if not isinstance(source, str) or "<" not in source:
        source = Path(source).read_text(encoding="utf-8", errors="ignore")
    lines = []
    for table in re.findall(r"<table.*?</table>", source, re.S):
        for row in re.findall(r"<tr.*?</tr>", table, re.S):
            cells = [_cell(c) for c in re.findall(r"<t[dh].*?</t[dh]>", row, re.S)]
            if any(cells):
                lines.append("  ".join(cells))
        lines.append("")
    return "\n".join(lines)


def document_text(path):
    """(текст, формат) для любого скачанного документа.

    Формат возвращается наружу нарочно: закупка из одного источника приходит
    HTML-ом, и её надо пропускать осознанно и со счётом, а не молча — иначе
    статистика тихо недосчитывает лоты и никто об этом не знает.
    """
    k = kind_of(path)
    if k == "pdf":
        return pdf_text(path), "pdf"
    if k == "html":
        return html_text(path), "html"
    return "", "unknown"


# ── мелочи, общие для парсеров ───────────────────────────────────────────────

def strip_tags(s):
    return _cell(s)


def num(s):
    """Число из строки портала: '1 234 567,89' -> 1234567.89. None, если не число."""
    s = re.sub(r"[^\d.,]", "", str(s)).replace(" ", "")
    if s.count(",") == 1 and s.count(".") == 0:
        s = s.replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def add_engine_to_path():
    """Чтобы `import common` работал из scripts/ и report/ при любом cwd."""
    root = str(Path(__file__).resolve().parent)
    if root not in sys.path:
        sys.path.insert(0, root)
