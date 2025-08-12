from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, current_app
from flask_login import login_required
from extensions import db
from models import Employee, Company, Funcao, EmployeeDocument
from forms import EmployeeForm, FuncaoForm, EmployeeDocForm
from utils import save_file
from audit import log_action
from pdf_reports import employee_pdf, toxicos_pdf
import io, requests
from datetime import date, timedelta

# NOVOS IMPORTS
import sqlite3
from pathlib import Path

hr_bp = Blueprint("rh", __name__, template_folder='../../templates/hr')

# ---------------------- Helpers de validade (SQLite) ----------------------
def _db_path_from_uri(uri: str, app_root: str) -> Path:
    if uri.startswith("sqlite:///"):
        return Path(app_root) / uri.replace("sqlite:///", "")
    if uri.startswith("sqlite:////"):
        return Path("/" + uri.replace("sqlite:////", ""))
    return Path(app_root) / "app.db"

def _doc_fetchall(sql: str, params=()):
    uri = current_app.config.get("SQLALCHEMY_DATABASE_URI", "sqlite:///app.db")
    db_path = _db_path_from_uri(uri, current_app.root_path)
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    try:
        return con.execute(sql, params).fetchall()
    finally:
        con.close()

def _doc_ensure_columns():
    uri = current_app.config.get("SQLALCHEMY_DATABASE_URI", "sqlite:///app.db")
    db_path = _db_path_from_uri(uri, current_app.root_path)
    if not db_path.exists():
        return
    con = sqlite3.connect(str(db_path))
    try:
        cols = [r[1] for r in con.execute("PRAGMA table_info(funcionarios)")]
        for col in ("aso_vencimento", "carteira_vencimento", "toxico_vencimento"):
            if col not in cols:
                con.execute(f"ALTER TABLE funcionarios ADD COLUMN {col} TEXT")
        con.commit()
    finally:
        con.close()
# -------------------------------------------------------------------------

# --------- Colaboradores ---------
@hr_bp.route("/colaboradores")
@login_required
def employees():
    # Filtros já existentes
    q = request.args.get("q","").strip()
    ativo = request.args.get("ativo","")
    mes_aniversario = request.args.get("mes","")

    # NOVOS filtros de validade
    doc = request.args.get("doc", "aso")         # 'aso' | 'carteira' | 'toxico'
    status = request.args.get("status", "")      # 'vencidos' | 'a_vencer' | 'validos' | ''
    try:
        dias = int(request.args.get("dias", 30))
    except ValueError:
        dias = 30

    # Query base (SQLAlchemy) — mantém sua listagem normal
    query = Employee.query
    if q:
        like = f"%{q}%"
        query = query.filter(Employee.nome.ilike(like))
    if ativo in ("1","0"):
        query = query.filter_by(ativo=(ativo=="1"))
    items = query.order_by(Employee.nome).all()
    if mes_aniversario:
        try:
            m = int(mes_aniversario)
            items = [e for e in items if e.data_nascimento and e.data_nascimento.month==m]
        except:
            pass

    # ---- Enriquecimento com vencimento do documento escolhido ----
    venc_map = {}
    try:
        _doc_ensure_columns()
        col_map = {
            "aso": "aso_vencimento",
            "carteira": "carteira_vencimento",
            "toxico": "toxico_vencimento",
        }
        col = col_map.get(doc, "aso_vencimento")

        if items:
            ids = [e.id for e in items]
            placeholders = ",".join(["?"] * len(ids))
            base_sql = f"SELECT id, COALESCE({col}, '') AS venc FROM funcionarios WHERE id IN ({placeholders})"
            where = ""
            params = list(ids)

            if status == "vencidos":
                where += f" AND {col} IS NOT NULL AND {col} <> '' AND DATE({col}) < DATE('now')"
            elif status == "a_vencer":
                where += f" AND {col} IS NOT NULL AND {col} <> '' AND DATE({col}) BETWEEN DATE('now') AND DATE('now', ?)"
                params.append(f"+{dias} day")
            elif status == "validos":
                where += f" AND {col} IS NOT NULL AND {col} <> '' AND DATE({col}) > DATE('now', ?)"
                params.append(f"+{dias} day")

            rows = _doc_fetchall(base_sql + where, tuple(params))
            venc_map = {int(r["id"]): r["venc"] for r in rows}

            if status in ("vencidos", "a_vencer", "validos"):
                idset = set(venc_map.keys())
                items = [e for e in items if e.id in idset]

    except Exception as ex:
        current_app.logger.warning("Filtro de validade indisponível: %s", ex)

    return render_template(
        "hr/employees_list.html",
        items=items,
        q=q, ativo=ativo, mes=mes_aniversario,
        doc=doc, status=status, dias=dias, venc_map=venc_map
    )

@hr_bp.route("/colaboradores/new", methods=["GET","POST"])
@login_required
def employees_new():
    form = EmployeeForm()
    form.company_id.choices = [(0,"-")] + [(c.id, c.razao_social) for c in Company.query.order_by(Company.razao_social)]
    form.funcao_id.choices = [(0,"-")] + [(f.id, f.nome) for f in Funcao.query.order_by(Funcao.nome)]
    if form.validate_on_submit():
        e = Employee()
        for f in form:
            if hasattr(e, f.name):
                v = f.data
                if f.name in ("company_id","funcao_id") and v==0: v=None
                setattr(e, f.name, v)
        if form.foto.data:
            e.foto_path = save_file(form.foto.data, "fotos")
        db.session.add(e); db.session.commit()
        log_action("create","Employee", e.id, {"nome": e.nome})
        flash("Colaborador criado.", "success")
        return redirect(url_for("rh.employees"))
    return render_template("hr/employee_form.html", form=form, title="Novo Colaborador")

@hr_bp.route("/colaboradores/<int:emp_id>/edit", methods=["GET","POST"])
@login_required
def employees_edit(emp_id):
    e = Employee.query.get_or_404(emp_id)
    form = EmployeeForm(obj=e)
    form.company_id.choices = [(0,"-")] + [(c.id, c.razao_social) for c in Company.query.order_by(Company.razao_social)]
    form.funcao_id.choices = [(0,"-")] + [(f.id, f.nome) for f in Funcao.query.order_by(Funcao.nome)]
    if form.validate_on_submit():
        for f in form:
            if hasattr(e, f.name):
                v = f.data
                if f.name in ("company_id","funcao_id") and v==0: v=None
                setattr(e, f.name, v)
        if form.foto.data:
            e.foto_path = save_file(form.foto.data, "fotos")
        db.session.commit()
        log_action("update","Employee", e.id, {"nome": e.nome})
        flash("Colaborador atualizado.", "success")
        return redirect(url_for("rh.employees"))
    return render_template("hr/employee_form.html", form=form, title="Editar Colaborador")

@hr_bp.route("/colaboradores/<int:emp_id>/pdf")
@login_required
def employees_pdf(emp_id):
    e = Employee.query.get_or_404(emp_id)
    bio = io.BytesIO()
    employee_pdf(bio, current_app, e)
    bio.seek(0)
    return send_file(bio, as_attachment=True, download_name=f"colaborador_{e.id}.pdf", mimetype="application/pdf")

# --------- CEP (ViaCEP proxy) ---------
@hr_bp.route("/api/cep/<cep>")
@login_required
def api_cep(cep):
    try:
        r = requests.get(f"https://viacep.com.br/ws/{cep}/json/", timeout=10)
        return r.json(), r.status_code
    except Exception:
        return {"erro":True}, 400

# --------- Funções ---------
@hr_bp.route("/funcoes")
@login_required
def funcoes():
    items = Funcao.query.order_by(Funcao.nome).all()
    return render_template("hr/funcoes_list.html", items=items)

@hr_bp.route("/funcoes/new", methods=["GET","POST"])
@login_required
def funcoes_new():
    form = FuncaoForm()
    if form.validate_on_submit():
        f = Funcao(nome=form.nome.data)
        db.session.add(f); db.session.commit()
        flash("Função criada.", "success")
        return redirect(url_for("rh.funcoes"))
    return render_template("hr/funcao_form.html", form=form)

# --------- Documentos do Colaborador ---------
@hr_bp.route("/colaboradores/<int:emp_id>/docs", methods=["GET","POST"])
@login_required
def employee_docs(emp_id):
    emp = Employee.query.get_or_404(emp_id)
    form = EmployeeDocForm()
    if form.validate_on_submit():
        path = None
        if form.arquivo.data:
            path = save_file(form.arquivo.data, "func_docs")
        doc = EmployeeDocument(employee_id=emp.id, tipo=form.tipo.data, descricao=form.descricao.data, arquivo_path=path)
        db.session.add(doc); db.session.commit()
        flash("Documento adicionado.", "success")
        return redirect(url_for("rh.employee_docs", emp_id=emp.id))
    q = request.args.get("q","").strip()
    docs = emp.documentos
    if q:
        docs = [d for d in docs if q.lower() in (d.tipo or '').lower() or q.lower() in (d.descricao or '').lower()]
    return render_template("hr/employee_docs_list.html", emp=emp, form=form, docs=docs)

# --------- Toxicológico (rotas antigas mantidas) ---------
@hr_bp.route("/toxicos")
@login_required
def toxicos():
    status = request.args.get("status", "")
    hoje = date.today()
    em_30 = hoje + timedelta(days=30)
    items = Employee.query.filter(Employee.exame_toxico_validade != None).all()
    def classify(e):
        if not e.exame_toxico_validade: return "indef"
        if e.exame_toxico_validade < hoje: return "vencido"
        if e.exame_toxico_validade <= em_30: return "a_vencer"
        return "vigente"
    if status in ("vencido","a_vencer","vigente"):
        items = [e for e in items if classify(e)==status]
    return render_template("hr/toxicos_list.html", items=items, status=status)

@hr_bp.route("/toxicos.pdf")
@login_required
def toxicos_pdf_all():
    status = request.args.get("status", "")
    hoje = date.today()
    em_30 = hoje + timedelta(days=30)
    items = Employee.query.filter(Employee.exame_toxico_validade != None).all()
    def classify(e):
        if not e.exame_toxico_validade: return "indef"
        if e.exame_toxico_validade < hoje: return "vencido"
        if e.exame_toxico_validade <= em_30: return "a_vencer"
        return "vigente"
    if status in ("vencido","a_vencer","vigente"):
        items = [e for e in items if classify(e)==status]
    bio = io.BytesIO()
    title = "Exame Toxicológico"
    if status=="vencido": title += " - Vencidos"
    elif status=="a_vencer": title += " - A Vencer (30d)"
    elif status=="vigente": title += " - Vigentes"
    toxicos_pdf(bio, current_app, items, titulo=title)
    bio.seek(0)
    return send_file(bio, as_attachment=True, download_name="toxicos.pdf", mimetype="application/pdf")
