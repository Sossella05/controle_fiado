from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = "sossella_secret"

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


# -------------------- LOGIN --------------------

class Usuario(UserMixin):
    def __init__(self, id, nome, senha):
        self.id = id
        self.nome = nome
        self.senha = senha


@login_manager.user_loader
def load_user(user_id):
    conn = sqlite3.connect("/tmp/fiado.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, nome, senha FROM usuarios WHERE id=?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return Usuario(id=row[0], nome=row[1], senha=row[2])
    return None


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        nome = request.form["usuario"]
        senha = request.form["senha"]

        conn = sqlite3.connect("/tmp/fiado.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id, nome, senha FROM usuarios WHERE nome=? AND senha=?", (nome, senha))
        row = cursor.fetchone()
        conn.close()

        if row:
            user = Usuario(id=row[0], nome=row[1], senha=row[2])
            login_user(user)
            flash("Login realizado com sucesso!")
            return redirect(url_for("index"))
        else:
            flash("Usuário ou senha incorretos!")
    return render_template("login.html")


# -------------------- LOGOUT --------------------

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# -------------------- INDEX / DASHBOARD --------------------

@app.route("/")
@login_required
def index():
    conn = sqlite3.connect("/tmp/fiado.db")
    cursor = conn.cursor()

    # Buscar lista de clientes
    cursor.execute("SELECT id, nome, total_comprado, total_pago FROM clientes")
    clientes = cursor.fetchall()

    # Cálculos para cards de resumo
    cursor.execute("SELECT COUNT(*) FROM clientes")
    total_clientes = cursor.fetchone()[0] or 0

    cursor.execute("SELECT SUM(total_comprado) FROM clientes")
    total_vendido = cursor.fetchone()[0] or 0

    cursor.execute("SELECT SUM(total_pago) FROM clientes")
    total_pago = cursor.fetchone()[0] or 0

    total_devedor = (total_vendido or 0) - (total_pago or 0)

    conn.close()

    return render_template(
        "index.html",
        clientes=clientes,
        total_clientes=total_clientes,
        total_vendido=total_vendido,
        total_pago=total_pago,
        total_devedor=total_devedor
    )


# -------------------- BACKUP --------------------

@app.route("/backup")
@login_required
def backup():
    db_path = "/tmp/fiado.db"
    if os.path.exists(db_path):
        return send_file(db_path, as_attachment=True)
    else:
        flash("Banco de dados não encontrado!")
        return redirect(url_for("index"))


# -------------------- MAIN --------------------
if __name__ == "__main__":
    app.run(debug=True)
