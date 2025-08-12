import os
from flask import Flask
from extensions import db, login_manager, migrate
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
from pytz import timezone

# --- Novos imports para garantir colunas no SQLite ---
import sqlite3
from urllib.parse import urlparse
from pathlib import Path
# -----------------------------------------------------


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
    from blueprints.uploads.routes import uploads_bp

    # Registro de blueprints
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(main_bp)
    app.register_blueprint(companies_bp, url_prefix="/empresas")
    app.register_blueprint(hr_bp, url_prefix="/rh")
    app.register_blueprint(documents_bp, url_prefix="/documentos")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(admin_users_bp, url_prefix="/admin/usuarios")
    app.register_blueprint(dash_bp)              # rota /dash
    app.register_blueprint(uploads_bp)           # rota /uploads/<path>

    # Filtro Jinja para normalizar caminhos de upload legados
    def norm_upload(p: str) -> str:
        if not p:
            return ""
        p = p.replace("\\", "/").lstrip("/")
        if p.startswith("uploads/"):
            p = p[len("uploads/"):]
        return p

    app.jinja_env.filters["norm_upload"] = norm_upload

    # ---------- Garantia das colunas de vencimento (SQLite) ----------
    # Cria as colunas se não existirem nas tabelas que você pode ter:
    # 'funcionarios', 'colaboradores' ou 'employees'.
    def _ensure_doc_columns(app_):
        uri = app_.config.get("SQLALCHEMY_DATABASE_URI", "")
        if not uri.startswith("sqlite"):
            return  # só precisamos disso para SQLite

        # Resolve caminho do arquivo sqlite
        # Ex.: sqlite:///app.db  -> <root>/app.db
        #      sqlite:////abs.db -> /abs.db
        parsed = urlparse(uri)
        if uri.startswith("sqlite:///"):
            db_path = Path(app_.root_path) / uri.replace("sqlite:///", "")
        elif uri.startswith("sqlite:////"):  # caminho absoluto
            db_path = Path(uri.replace("sqlite:////", "/"))
        else:
            # fallback: app.db no root do app
            db_path = Path(app_.root_path) / "app.db"

        if not db_path.exists():
            return

        con = sqlite3.connect(str(db_path))
        try:
            def table_exists(name: str) -> bool:
                row = con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (name,)
                ).fetchone()
                return bool(row)

            def ensure_on(name: str):
                if not table_exists(name):
                    return
                cols = [r[1] for r in con.execute(f"PRAGMA table_info({name})")]
                for col in ("aso_vencimento", "carteira_vencimento", "toxico_vencimento"):
                    if col not in cols:
                        con.execute(f"ALTER TABLE {name} ADD COLUMN {col} TEXT")

            for t in ("funcionarios", "colaboradores", "employees"):
                ensure_on(t)

            con.commit()
        finally:
            con.close()

    with app.app_context():
        try:
            _ensure_doc_columns(app)
        except Exception as e:
            # Não falha o servidor por causa disso
            app.logger.warning("Não foi possível garantir colunas de vencimento: %s", e)
    # ----------------------------------------------------------------

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
