#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# apply_aso_patch_v2_1.py
# Uso: python scripts/apply_aso_patch_v2_1.py "C:\projeto6"

import sys, re, shutil, datetime
from pathlib import Path

def read_snippet(name: str) -> str:
    here = Path(__file__).parent.parent / "snippets" / name
    return here.read_text(encoding="utf-8")

CARDS_BLOCK = read_snippet("cards_aso.html")
FILTER_FORM = read_snippet("filter_aso.html")

APP_HELPERS = """
from flask import Flask, render_template, current_app
import sqlite3
from pathlib import Path

def _db_path():
    root = Path(current_app.root_path)
    default = root / "instance" / "app.db"
    return current_app.config.get("DATABASE", str(default))

def _db_fetchall(sql, params=()):
    con = sqlite3.connect(_db_path())
    con.row_factory = sqlite3.Row
    try:
        cur = con.execute(sql, params)
        return cur.fetchall()
    finally:
        con.close()

def _db_ensure_aso_column():
    con = sqlite3.connect(_db_path())
    try:
        cols = [r[1] for r in con.execute("PRAGMA table_info(funcionarios)").fetchall()]
        if "aso_vencimento" not in cols:
            con.execute("ALTER TABLE funcionarios ADD COLUMN aso_vencimento TEXT")
            con.commit()
    finally:
        con.close()
"""

INDEX_FUNC = """
@app.route("/")
def index():
    try:
        _db_ensure_aso_column()
        aso_expired = _db_fetchall("""
            SELECT nome, aso_vencimento
            FROM funcionarios
            WHERE aso_vencimento IS NOT NULL AND aso_vencimento <> ''
              AND DATE(aso_vencimento) < DATE('now')
            ORDER BY DATE(aso_vencimento) ASC
            LIMIT 100
        """)
        aso_expiring = _db_fetchall("""
            SELECT nome, aso_vencimento
            FROM funcionarios
            WHERE aso_vencimento IS NOT NULL AND aso_vencimento <> ''
              AND DATE(aso_vencimento) BETWEEN DATE('now') AND DATE('now', '+30 day')
            ORDER BY DATE(aso_vencimento) ASC
            LIMIT 100
        """)
    except Exception:
        aso_expired, aso_expiring = [], []
    return render_template("index.html", aso_expired=aso_expired, aso_expiring=aso_expiring)
"""

RH_HELPERS = """
from flask import Blueprint, render_template, request, current_app
import sqlite3
from pathlib import Path

rh_bp = Blueprint("rh", __name__, url_prefix="/rh")

def _get_db_path():
    root = Path(current_app.root_path)
    default = root / "instance" / "app.db"
    return current_app.config.get("DATABASE", str(default))

def _fetchall(sql, params=()):
    con = sqlite3.connect(_get_db_path())
    con.row_factory = sqlite3.Row
    try:
        cur = con.execute(sql, params)
        return cur.fetchall()
    finally:
        con.close()

def _ensure_aso_column():
    con = sqlite3.connect(_get_db_path())
    try:
        cols = [r[1] for r in con.execute("PRAGMA table_info(funcionarios)").fetchall()]
        if "aso_vencimento" not in cols:
            con.execute("ALTER TABLE funcionarios ADD COLUMN aso_vencimento TEXT")
            con.commit()
    finally:
        con.close()
"""

FUNC_LIST_ROUTE_FUNC = """
@rh_bp.route("/funcionarios")
def funcionarios_list():
    _ensure_aso_column()
    aso = request.args.get("aso")
    try:
        dias = int(request.args.get("dias", 30))
    except ValueError:
        dias = 30
    base_sql = "SELECT id, nome, cargo, coalesce(aso_vencimento,'') as aso_vencimento FROM funcionarios"
    where = ""
    params = []
    if aso == "vencidos":
        where = " WHERE aso_vencimento IS NOT NULL AND aso_vencimento <> '' AND DATE(aso_vencimento) < DATE('now')"
    elif aso == "a_vencer":
        where = " WHERE aso_vencimento IS NOT NULL AND aso_vencimento <> '' AND DATE(aso_vencimento) BETWEEN DATE('now') AND DATE('now', ?)"
        params.append(f"+{dias} day")
    elif aso == "validos":
        where = " WHERE aso_vencimento IS NOT NULL AND aso_vencimento <> '' AND DATE(aso_vencimento) > DATE('now', ?)"
        params.append(f"+{dias} day")
    sql = base_sql + where + " ORDER BY DATE(aso_vencimento) ASC"
    funcionarios = _fetchall(sql, tuple(params))
    return render_template("rh/funcionarios_list.html", funcionarios=funcionarios, aso=aso, dias=dias, list_endpoint='rh.funcionarios_list')
"""

FUNC_LIST_ROUTE_COLAB = """
@rh_bp.route("/colaboradores")
def colaboradores_list():
    _ensure_aso_column()
    aso = request.args.get("aso")
    try:
        dias = int(request.args.get("dias", 30))
    except ValueError:
        dias = 30
    base_sql = "SELECT id, nome, cargo, coalesce(aso_vencimento,'') as aso_vencimento FROM funcionarios"
    where = ""
    params = []
    if aso == "vencidos":
        where = " WHERE aso_vencimento IS NOT NULL AND aso_vencimento <> '' AND DATE(aso_vencimento) < DATE('now')"
    elif aso == "a_vencer":
        where = " WHERE aso_vencimento IS NOT NULL AND aso_vencimento <> '' AND DATE(aso_vencimento) BETWEEN DATE('now') AND DATE('now', ?)"
        params.append(f"+{dias} day")
    elif aso == "validos":
        where = " WHERE aso_vencimento IS NOT NULL AND aso_vencimento <> '' AND DATE(aso_vencimento) > DATE('now', ?)"
        params.append(f"+{dias} day")
    sql = base_sql + where + " ORDER BY DATE(aso_vencimento) ASC"
    funcionarios = _fetchall(sql, tuple(params))
    return render_template("rh/colaboradores_list.html", funcionarios=funcionarios, aso=aso, dias=dias, list_endpoint='rh.colaboradores_list')
"""

def backup(p: Path, dest: Path):
    dest.mkdir(parents=True, exist_ok=True)
    if p.exists():
        shutil.copy2(p, dest / p.name)

def inject_cards(index_html: Path):
    txt = index_html.read_text(encoding="utf-8")
    if "ASO vencidos" in txt and "ASO que vencem em 30 dias" in txt:
        return False
    import re
    m = re.search(r"<h1[^>]*>.*?Dashboard.*?</h1>", txt, flags=re.IGNORECASE|re.DOTALL)
    block = CARDS_BLOCK
    if m:
        pos = m.end()
        new = txt[:pos] + "\n" + block + "\n" + txt[pos:]
    else:
        new = txt + "\n" + block + "\n"
    index_html.write_text(new, encoding="utf-8"); return True

def inject_filter(list_html: Path, endpoint: str):
    txt = list_html.read_text(encoding="utf-8")
    changed = False
    if "Filtro de ASO" not in txt:
        import re
        m = re.search(r"<h1[^>]*>.*?</h1>", txt, flags=re.IGNORECASE|re.DOTALL)
        form = FILTER_FORM.replace("list_endpoint", endpoint)
        if m:
            pos = m.end()
            txt = txt[:pos] + "\n" + form + "\n" + txt[pos:]
        else:
            txt = form + "\n" + txt
        changed = True
    if "ASO (vencimento)" not in txt:
        import re
        txt = re.sub(r"(<thead>.*?<tr>.*?</th>)", r"\1\n      <th>ASO (vencimento)</th>", txt, flags=re.DOTALL, count=1)
        changed = True
    if "{{ dt }}" not in txt and "aso_vencimento" in txt and "{{ (f['aso_vencimento']" not in txt:
        import re
        txt = re.sub(r"(<tbody>.*?<tr>.*?</td>.*?</td>)", r"\1\n      <td>{{ (f['aso_vencimento'] if f.__class__.__name__=='Row' else f.aso_vencimento) }}</td>", txt, flags=re.DOTALL, count=1)
        changed = True
    list_html.write_text(txt, encoding="utf-8"); return changed

def patch_routes(routes: Path, use_colab: bool):
    txt = routes.read_text(encoding="utf-8")
    if "def _get_db_path()" not in txt or "def _ensure_aso_column()" not in txt:
        head = RH_HELPERS
        if "Blueprint(" in txt and "rh_bp" in txt:
            head = head.replace('rh_bp = Blueprint("rh", __name__, url_prefix="/rh")\n\n', "")
        txt = head + "\n" + txt
    import re
    if use_colab:
        pattern = r"@rh_bp\.route\("/colaboradores"\)[\s\S]*?def\s+\w+\([\s\S]*?\):[\s\S]*?return\s+render_template\([\s\S]*?\)\s*"
        if re.search(pattern, txt):
            txt = re.sub(pattern, FUNC_LIST_ROUTE_COLAB, txt, count=1)
        else:
            txt += "\n\n" + FUNC_LIST_ROUTE_COLAB
    else:
        pattern = r"@rh_bp\.route\("/funcionarios"\)[\s\S]*?def\s+\w+\([\s\S]*?\):[\s\S]*?return\s+render_template\([\s\S]*?\)\s*"
        if re.search(pattern, txt):
            txt = re.sub(pattern, FUNC_LIST_ROUTE_FUNC, txt, count=1)
        else:
            txt += "\n\n" + FUNC_LIST_ROUTE_FUNC
    routes.write_text(txt, encoding="utf-8"); return True

def patch_app(app_py: Path):
    txt = app_py.read_text(encoding="utf-8")
    import re
    if "_db_path" not in txt or "_db_fetchall" not in txt or "_db_ensure_aso_column" not in txt:
        if "from flask import Flask" in txt:
            txt = re.sub(r"(from\s+flask\s+import[^\n]+\n)", r"\1import sqlite3\nfrom pathlib import Path\n", txt, count=1)
            txt = txt + "\n" + APP_HELPERS
        else:
            txt = "from flask import Flask, render_template, current_app\nimport sqlite3\nfrom pathlib import Path\n\n" + txt + "\n" + APP_HELPERS
    if re.search(r"@app\.route\("/"\)\s*def\s+index\(", txt):
        txt = re.sub(r"@app\.route\("/"\)[\s\S]*?def\s+index\([^\)]*\):[\s\S]*?return\s+render_template\([^\n]*\)\s*", INDEX_FUNC, txt, count=1)
    else:
        txt += "\n\n" + INDEX_FUNC
    app_py.write_text(txt, encoding="utf-8"); return True

def main():
    proj = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    app_py = proj / "app.py"
    rh_routes = proj / "blueprints" / "rh" / "routes.py"
    tmpl_colab = proj / "templates" / "rh" / "colaboradores_list.html"
    tmpl_func  = proj / "templates" / "rh" / "funcionarios_list.html"
    index_html = proj / "templates" / "index.html"

    missing = [str(p) for p in [app_py, rh_routes, index_html] if not p.exists()]
    if missing:
        print("[ERRO] Arquivos esperados não encontrados:", missing); sys.exit(2)

    use_colab = tmpl_colab.exists()
    list_html = tmpl_colab if use_colab else tmpl_func
    if not list_html.exists():
        print("[ERRO] Template de listagem não encontrado:", tmpl_colab, "ou", tmpl_func); sys.exit(2)

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = proj / ("_backup_aso_patch_v2_1_" + stamp)
    for p in [app_py, rh_routes, list_html, index_html]: backup(p, backup_dir)

    print("[INFO] Patching app.py...");  patch_app(app_py)
    print("[INFO] Patching routes.py (colaboradores=%s)..." % use_colab);  patch_routes(rh_routes, use_colab)
    print("[INFO] Injetando filtro no template:", list_html.name);  inject_filter(list_html, 'rh.colaboradores_list' if use_colab else 'rh.funcionarios_list')
    print("[INFO] Injetando cards no index.html..."); inject_cards(index_html)
    print("[OK] Tudo pronto. Backup em", backup_dir)

if __name__ == "__main__":
    main()
