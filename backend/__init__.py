import os
import click
from flask import Flask, jsonify
from dotenv import load_dotenv
from sqlalchemy import event
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import HTTPException
from .extensions import db, migrate
from .utils.validation import APIError


def create_app(test_config=None):
    load_dotenv()
    app = Flask(__name__)
    database_url = os.getenv("DATABASE_URL")
    if not database_url and os.getenv("MYSQL_HOST"):
        database_url = URL.create(
            "mysql+pymysql",
            username=os.environ["MYSQL_USER"],
            password=os.environ["MYSQL_PASSWORD"],
            host=os.environ["MYSQL_HOST"],
            port=int(os.getenv("MYSQL_PORT", "3306")),
            database=os.environ["MYSQL_DATABASE"],
            query={"charset": "utf8mb4"},
        )
    app.config.update(
        SQLALCHEMY_DATABASE_URI=database_url,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True},
        MAX_CONTENT_LENGTH=64 * 1024,
        SESSION_HOURS=8,
    )
    if test_config:
        app.config.update(test_config)
    if not app.config["SQLALCHEMY_DATABASE_URI"]:
        raise RuntimeError("DATABASE_URL is required. See .env.example and README.md.")
    db.init_app(app)
    migrate.init_app(app, db, compare_type=True)
    with app.app_context():
        if db.engine.dialect.name == "sqlite":

            @event.listens_for(db.engine, "connect")
            def enable_foreign_keys(connection, _):
                connection.execute("PRAGMA foreign_keys=ON")

    from .routes.auth import bp as auth_bp

    app.register_blueprint(auth_bp)
    # Management blueprints are loaded as later phases are completed.
    from .routes import register_management

    register_management(app)

    @app.get("/api/health")
    def health():
        from sqlalchemy import text

        db.session.execute(text("SELECT 1"))
        return jsonify(status="ok")

    @app.errorhandler(APIError)
    def api_error(error):
        db.session.rollback()
        return jsonify(error=error.message), error.status

    @app.errorhandler(IntegrityError)
    def integrity_error(error):
        db.session.rollback()
        return jsonify(
            error="Duplicate value or dependent records prevent this operation"
        ), 409

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error=error.description), error.code

    @app.errorhandler(Exception)
    def internal_error(error):
        db.session.rollback()
        app.logger.exception("Unhandled request failure")
        return jsonify(error="Internal server error"), 500

    @app.after_request
    def security_headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.cli.command("create-admin")
    @click.option("--login-id", prompt=True)
    @click.option("--name", prompt=True)
    @click.option("--email", prompt=True)
    @click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
    def create_admin(login_id, name, email, password):
        from .services.people import create_user

        create_user(
            "ADMIN",
            {"login_id": login_id, "name": name, "email": email, "password": password},
        )
        db.session.commit()
        click.echo("Admin created")

    @app.cli.command("seed-demo")
    @click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
    def seed_demo(password):
        from .services.seed import seed

        seed(password)
        click.echo(
            "Demo data created. IDs: ADM001, C001, C002, S001–S006. Use the password you supplied."
        )

    @app.cli.command("cleanup-auth")
    def cleanup_auth():
        from datetime import timedelta
        from sqlalchemy import delete
        from .models import AuthSession, LoginAttempt, utcnow

        db.session.execute(delete(AuthSession).where(AuthSession.expires_at < utcnow()))
        db.session.execute(
            delete(LoginAttempt).where(
                LoginAttempt.attempted_at < utcnow() - timedelta(days=1)
            )
        )
        db.session.commit()
        click.echo("Expired sessions and old login attempts removed")

    return app
