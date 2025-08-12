#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# apply_aso_patch_v2.py
# Uso: python scripts/apply_aso_patch_v2.py "C:\\projeto6"

import sys, re, shutil, os, datetime
from pathlib import Path

CARDS_BLOCK = """
<!-- Cards de ASO (injetado) -->
<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:12px 0;">
  <div style="border:1px solid #ddd;border-radius:12px;padding:12px;">
    <h3 style="margin:0 0 8px 0;">ASO vencidos</h3>
    {% if aso_expired and aso_expired|length > 0 %}
      <ul style="margin:0;padding-left:18px;">
        {% for r in aso_expired %}
          <li>{{ r['nome'] if r.__class__.__name__=='Row' else r.nome }} - {{ (r['aso_vencimento'] if r.__class__.__name__=='Row' else r.aso_vencimento) }}</li>
        {% endfor %}
      </ul>
    {% else %}
      <div style="opacity:.7">Nenhum ASO vencido.</div>
    {% endif %}
  </div>
  <div style="border:1px solid #ddd;border-radius:12px;padding:12px;">
    <h3 style="margin:0 0 8px 0;">ASO que vencem em 30 dias</h3>
    {% if aso_expiring and aso_expiring|length > 0 %}
      <ul style="margin:0;padding-left:18px;">
        {% for r in aso_expiring %}
          <li>{{ r['nome'] if r.__class__.__name__=='Row' else r.nome }} - {{ (r['aso_vencimento'] if r.__class__.__name__=='Row' else r.aso_vencimento) }}</li>
        {% endfor %}
      </ul>
    {% else %}
      <div style="opacity:.7">Nada vence nos proximos 30 dias.</div>
    {% endif %}
  </div>
</div>
"""

FILTER_FORM = """
<!-- Filtro de ASO (injetado) -->
<form method="get" style="display:flex;gap:.5rem;align-items:center;margin:8px 0;padding:.5rem;border:1px solid #ddd;border-radius:8px;">
  <label for="aso">ASO:</label>
  <select id="aso" name="aso">
    <option value="" {{ 'selected' if not aso }}>Todos</option>
    <option value="vencidos" {{ 'selected' if aso=='vencidos' }}>Vencidos</option>
    <option value="a_vencer" {{ 'selected' if aso=='a_vencer' }}>A vencer</option>
    <option value="validos" {{ 'selected' if aso=='validos' }}>Validos</option>
  </select>
  <label for="dias">Dias:</label>
  <input id="dias" type="number" name="dias" value="{{ dias or 30 }}" min="1" style="width:90px">
  <button type="submit">Filtrar</button>
  <a href="{{ url_for(list_endpoint, aso='vencidos') }}" style="margin-left:auto">Somente vencidos</a>
  <a href="{{ url_for(list_endpoint, aso='a_vencer', dias=30) }}">A vencer (30d)</a>
  <a href="{{ url_for(list_endpoint) }}">Limpar</a>
  <small style="opacity:.7;margin-left:.5rem">Data no formato: YYYY-MM-DD</small>
</form>
"""

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
    return render_template("rh/funcionarios_list.html", funcionarios=funcionarios, aso=aso, dias=dias, list_endpoint="rh.funcionarios_list")
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
    return render_template("rh/colaboradores_list.html", funcionarios=funcionarios, aso=aso, dias=dias, list_endpoint="rh.colaboradores_list")
"""

def backup_file(path: Path, backup_dir: Path):
    if path.exists():
        shutil.copy2(path, backup_dir / path.name)

def inject_cards_in_index_html(index_html: Path):
    txt = index_html.read_text(encoding="utf-8")
    if "ASO vencidos" in txt and "ASO que vencem em 30 dias" in txt:
        return False
    m = re.search(r"<h1[^>]*>.*?Dashboard.*?</h1>", txt, flags=re.IGNORECASE|re.DOTALL)
    if m:
        pos = m.end()
        new_txt = txt[:pos] + "\n" + CARDS_BLOCK + "\n" + txt[pos:]
    else:
        new_txt = txt + "\n" + CARDS_BLOCK + "\n"
    index_html.write_text(new_txt, encoding="utf-8")
    return True

def inject_filter_in_list_html(list_html: Path, endpoint_name: str):
    txt = list_html.read_text(encoding="utf-8")
    changed = False
    if "Filtro de ASO" not in txt:
        m = re.search(r"<h1[^>]*>.*?</h1>", txt, flags=re.IGNORECASE|re.DOTALL)
        form = FILTER_FORM.replace("list_endpoint", endpoint_name)
        if m:
            pos = m.end()
            txt = txt[:pos] + "\n" + form + "\n" + txt[pos:]
        else:
            txt = form + "\n" + txt
        changed = True
    if "ASO (vencimento)" not in txt:
        txt = re.sub(r"(<thead>.*?<tr>.*?</th>)", r"\1\n      <th>ASO (vencimento)</th>", txt, flags=re.DOTALL, count=1)
        changed = True
    if "{{ dt }}" not in txt and "aso_vencimento" in txt and "{{ (f['aso_vencimento']" not in txt:
        txt = re.sub(r"(<tbody>.*?<tr>.*?</td>.*?</td>)", r"\1\n      <td>{{ (f['aso_vencimento'] if f.__class__.__name__=='Row' else f.aso_vencimento) }}</td>", txt, flags=re.DOTALL, count=1)
        changed = True
    list_html.write_text(txt, encoding="utf-8")
    return changed

def patch_rh_routes(routes_py: Path, use_colab: bool):
    txt = routes_py.read_text(encoding="utf-8")
    if "def _get_db_path()" not in txt or "def _ensure_aso_column()" not in txt:
        head = RH_HELPERS
        if "Blueprint(" in txt and "rh_bp" in txt:
            head = head.replace('rh_bp = Blueprint("rh", __name__, url_prefix="/rh")\n\n', "")
        txt = head + "\n" + txt
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
    routes_py.write_text(txt, encoding="utf-8")
    return True

def patch_app_py(app_py: Path):
    txt = app_py.read_text(encoding="utf-8")
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
    app_py.write_text(txt, encoding="utf-8")
    return True

def main():
    if len(sys.argv) > 1:
        proj = Path(sys.argv[1])
    else:
        proj = Path.cwd()
    app_py = proj / "app.py"
    rh_routes = proj / "blueprints" / "rh" / "routes.py"
    tmpl_colab = proj / "templates" / "rh" / "colaboradores_list.html"
    tmpl_func = proj / "templates" / "rh" / "funcionarios_list.html"
    index_html = proj / "templates" / "index.html"
    missing = [str(p) for p in [app_py, rh_routes, index_html] if not p.exists()]
    if missing:
        print("[ERRO] Arquivos esperados nao encontrados:", missing)
        sys.exit(2)
    use_colab = tmpl_colab.exists()
    list_html = tmpl_colab if use_colab else tmpl_func
    if not list_html.exists():
        print("[ERRO] Template de listagem nao encontrado:", tmpl_colab, "ou", tmpl_func)
        sys.exit(2)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = proj / ("_backup_aso_patch_v2_" + stamp)
    backup_dir.mkdir(parents=True, exist_ok=True)
    for p in [app_py, rh_routes, list_html, index_html]:
        backup_file(p, backup_dir)
    print("[INFO] Patching app.py...")
    patch_app_py(app_py)
    print("[INFO] Patching routes.py (colaboradores=%s)..." % use_colab)
    patch_rh_routes(rh_routes, use_colab)
    print("[INFO] Injetando filtro no template:", list_html.name)
    inject_filter_in_list_html(list_html, "rh.colaboradores_list" if use_colab else "rh.funcionarios_list")
    print("[INFO] Injetando cards no index.html...")
    inject_cards_in_index_html(index_html)
    print("[OK] Tudo pronto. Backup em", backup_dir)

if __name__ == "__main__":
    main()