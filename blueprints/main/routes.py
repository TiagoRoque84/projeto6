
from flask import Blueprint, render_template
from flask_login import login_required
from models import Employee, Document

main_bp = Blueprint("main", __name__, template_folder='../../templates')

@main_bp.route("/")
@login_required
def index():
    total_emp = Employee.query.count()
    ativos = Employee.query.filter_by(ativo=True).count()
    inativos = total_emp - ativos
    docs = Document.query.all()
    vencidos = len([d for d in docs if d.status=="Vencido"])
    a_vencer = len([d for d in docs if d.status=="A vencer"])
    return render_template("index.html", total_emp=total_emp, ativos=ativos, inativos=inativos, vencidos=vencidos, a_vencer=a_vencer)
