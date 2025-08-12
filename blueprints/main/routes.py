# blueprints/main/routes.py

from flask import Blueprint
from flask_login import login_required

main_bp = Blueprint("main", __name__, template_folder='../../templates')

@main_bp.route("/", endpoint="index")
@login_required
def index():
    # Usa a mesma view do painel (sem redirect e sem duplicar lógica)
    from blueprints.dash.routes import dashboard as dash_dashboard
    return dash_dashboard()
