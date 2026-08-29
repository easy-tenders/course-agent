#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Собрать все открытые лоты по ключевому слову с деталями.

    python collect_open.py [ключевое слово]

Результат — `lots.json` во временной папке прогона; путь печатается в конце.
Его читает rating.py.
"""
import json
import re
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import common

TMP = common.cache_dir("open")
KEY = sys.argv[1] if len(sys.argv) > 1 else "кондиционер"

txt = common.strip_tags
num = common.num

url = ("https://goszakup.gov.kz/ru/search/lots?filter%5Bname%5D=" + urllib.parse.quote(KEY)
       + "&filter%5Bstatus%5D%5B%5D=220")
if not common.fetch(url, TMP / "list.html", min_size=500):
    sys.exit("не удалось получить список лотов с портала")
d = (TMP / "list.html").read_text(encoding="utf-8", errors="ignore")
tables = re.findall(r"<table.*?</table>", d, re.S)
if len(tables) < 2:
    sys.exit(f"по слову «{KEY}» открытых лотов не найдено")
t = tables[1]
rows = re.findall(r"<tr.*?</tr>", re.search(r"<tbody.*?</tbody>", t, re.S).group(), re.S)

lots = []
for r in rows:
    link = re.search(r'href="(https://goszakup\.gov\.kz/ru/subpriceoffer/index/(\d+)/(\d+))"', r)
    cells = [txt(c) for c in re.findall(r"<td.*?</td>", r, re.S) if txt(c)]
    if not link or not cells:
        continue
    lots.append(dict(url=link.group(1), ann=link.group(2), lot_id=link.group(3),
                     num=cells[0].split()[0], method=cells[-2] if len(cells) > 5 else ""))

print(f"открытых лотов: {len(lots)}", file=sys.stderr)
out = []
for l in lots:
    p = TMP / f"lot_{l['lot_id']}.html"
    if not common.fetch(l["url"], p):
        continue
    h = p.read_text(encoding="utf-8", errors="ignore")
    tb = re.findall(r"<table.*?</table>", h, re.S)
    if not tb:
        continue
    ths = [txt(x) for x in re.findall(r"<th.*?</th>", tb[0], re.S)]
    tds = [txt(x) for x in re.findall(r"<td.*?</td>", tb[0], re.S)]
    f = dict(zip(ths, tds))
    out.append(dict(
        lot=f.get("Лот №", l["num"]).replace(" История", "").strip(),
        ann=l["ann"],
        status=f.get("Статус лота", ""),
        deadline=f.get("Дата окончания приема заявок", ""),
        customer=f.get("Наименование заказчика", "")[:70],
        tru_code=f.get("Код ТРУ", ""),
        tru_name=f.get("Наименование ТРУ", ""),
        char=f.get("Краткая характеристика", ""),
        char2=f.get("Дополнительная характеристика", "")[:80],
        unit_price=num(f.get("Цена за единицу", "")),
        qty=num(f.get("Количество", "")),
        total=num(f.get("Запланированная сумма", "")),
        delivery=f.get("Срок поставки ТРУ", "")[:60],
        method=l["method"],
    ))

dst = TMP / "lots.json"
dst.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"собрано карточек: {len(out)}", file=sys.stderr)
for r in out:
    print(f"{r['lot']:<20} {str(r['qty'] or ''):>4} × {r['unit_price'] or 0:>10,.0f} "
          f"= {r['total'] or 0:>11,.0f} | {r['char'][:52]}")
print(f"\nданные лотов: {dst}", file=sys.stderr)
