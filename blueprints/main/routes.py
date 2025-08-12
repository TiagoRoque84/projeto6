from flask import Blueprint, render_template
from flask_login import login_required
from models import Document, Employee
from datetime import date, timedelta

main_bp = Blueprint("main", __name__)

@main_bp.route("/")
@login_required
def index():
    hoje = date.today()
    em_30 = hoje + timedelta(days=30)

    total_emp = Employee.query.count()
    ativos = Employee.query.filter_by(ativo=True).count()
    inativos = total_emp - ativos

    vencidos = Document.query.filter(
        Document.data_vencimento != None,
        Document.data_vencimento < hoje
    ).count()
    a_vencer = Document.query.filter(
        Document.data_vencimento != None,
        Document.data_vencimento >= hoje,
        Document.data_vencimento <= em_30
    ).count()

    aso_expired = [
        {"nome": e.nome, "aso_vencimento": e.aso_validade}
        for e in (
            Employee.query
            .filter(Employee.aso_validade != None, Employee.aso_validade < hoje)
            .order_by(Employee.aso_validade.asc())
            .limit(100).all()
        )
    ]
    aso_expiring = [
        {"nome": e.nome, "aso_vencimento": e.aso_validade}
        for e in (
            Employee.query
            .filter(Employee.aso_validade != None, Employee.aso_validade >= hoje, Employee.aso_validade <= em_30)
            .order_by(Employee.aso_validade.asc())
            .limit(100).all()
        )
    ]

    tox_expired = [
        {"nome": e.nome, "toxico_vencimento": e.exame_toxico_validade}
        for e in (
            Employee.query
            .filter(Employee.exame_toxico_validade != None, Employee.exame_toxico_validade < hoje)
            .order_by(Employee.exame_toxico_validade.asc())
            .limit(100).all()
        )
    ]
    tox_expiring = [
        {"nome": e.nome, "toxico_vencimento": e.exame_toxico_validade}
        for e in (
            Employee.query
            .filter(Employee.exame_toxico_validade != None, Employee.exame_toxico_validade >= hoje, Employee.exame_toxico_validade <= em_30)
            .order_by(Employee.exame_toxico_validade.asc())
            .limit(100).all()
        )
    ]

    cart_expired, cart_expiring = [], []
    try:
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
                    .order_by(col.asc()).limit(100).all()
                )
            ]
            cart_expiring = [
                {"nome": e.nome, "carteira_vencimento": getattr(e, col.key)}
                for e in (
                    Employee.query
                    .filter(col != None, col >= hoje, col <= em_30)
                    .order_by(col.asc()).limit(100).all()
                )
            ]
    except Exception:
        pass

    return render_template(
        "index.html",
        total_emp=total_emp, ativos=ativos, inativos=inativos,
        vencidos=vencidos, a_vencer=a_vencer,
        aso_expired=aso_expired, aso_expiring=aso_expiring,
        cart_expired=cart_expired, cart_expiring=cart_expiring,
        tox_expired=tox_expired, tox_expiring=tox_expiring,
    )
