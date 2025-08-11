import os
from flask import Flask
from extensions import db, login_manager, migrate
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
from pytz import timezone

def create_app():
    load_dotenv()

    app = Flask(
        __name__,
        instance_relative_config=False,
        static_folder="static",
        template_folder="templates",
    )
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
        "SQLALCHEMY_DATABASE_URI", "sqlite:///app.db"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["UPLOAD_FOLDER"] = os.getenv("UPLOAD_FOLDER", "uploads")
    app.config["SESSION_PERMANENT"] = False

    # Extensões
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)

    # Blueprints (importar AQUI para evitar ciclos)
    from blueprints.auth.routes import auth_bp
    from blueprints.main.routes import main_bp
    from blueprints.companies.routes import companies_bp
    from blueprints.hr.routes import hr_bp
    from blueprints.documents.routes import documents_bp
    from blueprints.admin.routes import admin_bp
    from blueprints.admin.users import admin_users_bp
    from blueprints.dash.routes import dash_bp
    from blueprints.uploads.routes import uploads_bp  # <- uma única vez

    # Registro de blueprints
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(main_bp)
    app.register_blueprint(companies_bp, url_prefix="/empresas")
    app.register_blueprint(hr_bp, url_prefix="/rh")
    app.register_blueprint(documents_bp, url_prefix="/documentos")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(admin_users_bp, url_prefix="/admin/usuarios")
    app.register_blueprint(dash_bp)              # /dash
    app.register_blueprint(uploads_bp)           # /uploads/<path>

    # Filtro Jinja para normalizar caminhos de upload legados
    def norm_upload(p: str) -> str:
        if not p:
            return ""
        p = p.replace("\\", "/").lstrip("/")
        if p.startswith("uploads/"):
            p = p[len("uploads/"):]
        return p
    app.jinja_env.filters["norm_upload"] = norm_upload

    # Agendador de alertas
    from alerts import send_alerts
    sched = BackgroundScheduler(timezone=timezone("America/Sao_Paulo"))
    sched.add_job(
        send_alerts, "cron", hour=8, minute=0, id="daily_alerts", replace_existing=True
    )
    sched.start()

    return app


# Loader do usuário
from models import User

@login_manager.user_loader
def load_user(uid):
    return User.query.get(int(uid))


# Fábrica
app = create_app()


# Comando CLI para dados iniciais
@app.cli.command("init-data")
def init_data():
    from models import User, Company, Funcao, DocumentType
    from extensions import db

    if not User.query.filter_by(username="admin").first():
        u = User(
            username="admin",
            password="admin123",
            role="admin",
            nome_completo="Administrador",
        )
        db.session.add(u)

    if Funcao.query.count() == 0:
        db.session.add(Funcao(nome="Motorista"))
        db.session.add(Funcao(nome="Auxiliar"))

    if DocumentType.query.count() == 0:
        db.session.add(DocumentType(nome="Alvará"))
        db.session.add(DocumentType(nome="Certidão"))

    if Company.query.count() == 0:
        db.session.add(
            Company(
                razao_social="Empresa Exemplo LTDA",
                nome_fantasia="Exemplo",
                cnpj="00.000.000/0001-00",
                cidade="São José do Rio Pardo",
                uf="SP",
            )
        )

    db.session.commit()
    print("Dados iniciais criados. Login: admin / admin123")


if __name__ == "__main__":
    app.run()
