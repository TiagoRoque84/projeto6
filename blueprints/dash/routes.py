from flask import Blueprint, render_template
from flask_login import login_required
from models import Document, Employee
from datetime import date, timedelta

dash_bp = Blueprint("dash", __name__, template_folder='../../templates')

@dash_bp.route("/dash")
@login_required
def dashboard():
    hoje = date.today()
    em_30 = hoje + timedelta(days=30)

    # ---------- ASO (via Employee.aso_validade) ----------
    aso_expired = [
        {"nome": e.nome, "aso_vencimento": e.aso_validade}
        for e in (
            Employee.query
            .filter(Employee.aso_validade != None, Employee.aso_validade < hoje)
            .order_by(Employee.aso_validade.asc())
            .limit(100)
            .all()
        )
    ]
    aso_expiring = [
        {"nome": e.nome, "aso_vencimento": e.aso_validade}
        for e in (
            Employee.query
            .filter(
                Employee.aso_validade != None,
                Employee.aso_validade >= hoje,
                Employee.aso_validade <= em_30,
            )
            .order_by(Employee.aso_validade.asc())
            .limit(100)
            .all()
        )
    ]

    # ---------- Toxicológico (via Employee.exame_toxico_validade) ----------
    tox_expired = [
        {"nome": e.nome, "toxico_vencimento": e.exame_toxico_validade}
        for e in (
            Employee.query
            .filter(Employee.exame_toxico_validade != None, Employee.exame_toxico_validade < hoje)
            .order_by(Employee.exame_toxico_validade.asc())
            .limit(100)
            .all()
        )
    ]
    tox_expiring = [
        {"nome": e.nome, "toxico_vencimento": e.exame_toxico_validade}
        for e in (
            Employee.query
            .filter(
                Employee.exame_toxico_validade != None,
                Employee.exame_toxico_validade >= hoje,
                Employee.exame_toxico_validade <= em_30,
            )
            .order_by(Employee.exame_toxico_validade.asc())
            .limit(100)
            .all()
        )
    ]

    # ---------- Carteiras (CNH) ----------
    cart_expired, cart_expiring = [], []
    try:
        # Tenta primeiro uma coluna no Employee (carteira_validade ou cnh_validade)
        col = None
        if hasattr(Employee, "carteira_validade"):
            col = getattr(Employee, "carteira_validade")
        elif hasattr(Employee, "cnh_validade"):
            col = getattr(Employee, "cnh_validade")

        if col is not None:
            cart_expired = [
                {"nome": e.nome, "carteira_vencimento": getattr(e, col.key)}
                for e in (
                    Employee.query
                    .filter(col != None, col < hoje)
                    .order_by(col.asc())
                    .limit(100)
                    .all()
                )
            ]
            cart_expiring = [
                {"nome": e.nome, "carteira_vencimento": getattr(e, col.key)}
                for e in (
                    Employee.query
                    .filter(col != None, col >= hoje, col <= em_30)
                    .order_by(col.asc())
                    .limit(100)
                    .all()
                )
            ]
        else:
            # Sem coluna no Employee: tenta via Document (tipo Carteira/CNH)
            carteira_tipos = ("CNH", "Carteira", "Carteira de Motorista")
            q_base = Document.query.filter(Document.data_vencimento != None)
            if hasattr(Document, "tipo"):
                q_base = q_base.filter(Document.tipo.in_(carteira_tipos))

            if hasattr(Document, "employee") or hasattr(Document, "employee_id"):
                from sqlalchemy.orm import aliased
                Emp = aliased(Employee)

                # vencidos
                q1 = (
                    q_base.join(Emp, Document.employee_id == Emp.id)
                    .filter(Document.data_vencimento < hoje)
                    .with_entities(
                        Emp.nome.label("nome"),
                        Document.data_vencimento.label("carteira_vencimento"),
                    )
                    .order_by(Document.data_vencimento.asc())
                    .limit(100)
                )
                cart_expired = [
                    {"nome": r.nome, "carteira_vencimento": r.carteira_vencimento}
                    for r in q1.all()
                ]

                # a vencer (30d)
                q2 = (
                    q_base.join(Emp, Document.employee_id == Emp.id)
                    .filter(
                        Document.data_vencimento >= hoje,
                        Document.data_vencimento <= em_30,
                    )
                    .with_entities(
                        Emp.nome.label("nome"),
                        Document.data_vencimento.label("carteira_vencimento"),
                    )
                    .order_by(Document.data_vencimento.asc())
                    .limit(100)
                )
                cart_expiring = [
                    {"nome": r.nome, "carteira_vencimento": r.carteira_vencimento}
                    for r in q2.all()
                ]
    except Exception:
        # Qualquer divergência de modelo não deve derrubar o dashboard
        cart_expired, cart_expiring = [], []

    # --------- Contagens (mantidas p/ compatibilidade) ---------
    docs_venc = (
        Document.query
        .filter(Document.data_vencimento != None, Document.data_vencimento < hoje)
        .count()
    )
    docs_avencer = (
        Document.query
        .filter(
            Document.data_vencimento != None,
            Document.data_vencimento >= hoje,
            Document.data_vencimento <= em_30
        )
        .count()
    )
    aso_venc = len(aso_expired)
    aso_avencer = len(aso_expiring)
    tox_venc = len(tox_expired)
    tox_avencer = len(tox_expiring)
    total_func = Employee.query.count()
    ativos = Employee.query.filter_by(ativo=True).count()
    inativos = total_func - ativos

    return render_template(
        "dashboard.html",
        # contagens
        docs_venc=docs_venc, docs_avencer=docs_avencer,
        aso_venc=aso_venc, aso_avencer=aso_avencer,
        tox_venc=tox_venc, tox_avencer=tox_avencer,
        total_func=total_func, ativos=ativos, inativos=inativos,
        # listas p/ cards
        aso_expired=aso_expired, aso_expiring=aso_expiring,
        cart_expired=cart_expired, cart_expiring=cart_expiring,
        tox_expired=tox_expired, tox_expiring=tox_expiring,
    )
