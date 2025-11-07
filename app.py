from flask import Flask, render_template, request, redirect, url_for, flash, send_file, session
from flask_login import (
    LoginManager, UserMixin, login_user, login_required,
    logout_user, current_user
)
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = "chave-secreta-fiado"

# ---------------- FLASK-LOGIN ----------------
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# ---------------- USUÁRIO ----------------
class User(UserMixin):
    def __init__(self, id, nome, senha):
        self.id = id
        self.nome = nome
        self.senha = senha

@login_manager.user_loader
def load_user(user_id):
    conn = sqlite3.connect("/tmp/fiado.db")
    c = conn.cursor()
    c.execute("SELECT id, nome, senha FROM usuarios WHERE id=?", (user_id,))
    user = c.fetchone()
    conn.close()
    if user:
        return User(*user)
    return None

# ---------------- BANCO DE DADOS ----------------
def init_db():
    conn = sqlite3.connect("/tmp/fiado.db")
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS vendas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER,
            data TEXT,
            valor_compra REAL,
            valor_pago REAL,
            FOREIGN KEY(cliente_id) REFERENCES clientes(id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT UNIQUE,
            senha TEXT
        )
    """)

    c.execute("SELECT * FROM usuarios WHERE nome='admin'")
    if not c.fetchone():
        c.execute("INSERT INTO usuarios (nome, senha) VALUES ('admin', '1234')")
        print("✅ Usuário padrão criado: admin / 1234")

    conn.commit()
    conn.close()

init_db()

# ---------------- ROTA PRINCIPAL ----------------
@app.route("/")
@login_required
def index():
    conn = sqlite3.connect("/tmp/fiado.db")
    c = conn.cursor()
    c.execute("""
        SELECT clientes.id, clientes.nome,
               IFNULL(SUM(vendas.valor_compra),0) as total_compra,
               IFNULL(SUM(vendas.valor_pago),0) as total_pago,
               IFNULL(SUM(vendas.valor_compra),0) - IFNULL(SUM(vendas.valor_pago),0) as saldo
        FROM clientes
        LEFT JOIN vendas ON clientes.id = vendas.cliente_id
        GROUP BY clientes.id, clientes.nome
    """)
    dados = c.fetchall()
    conn.close()

    nomes = [d[1] for d in dados]
    total_compras = [d[2] for d in dados]
    total_pagos = [d[3] for d in dados]
    saldos = [d[4] for d in dados]

    return render_template(
        "index.html",
        dados=dados,
        usuario=current_user.nome,
        nomes=nomes,
        total_compras=total_compras,
        total_pagos=total_pagos,
        saldos=saldos,
        datetime=datetime
    )

# ---------------- CLIENTES ----------------
@app.route("/cliente", methods=["GET", "POST"])
@login_required
def cliente():
    if request.method == "POST":
        nome = request.form["nome"]
        conn = sqlite3.connect("/tmp/fiado.db")
        c = conn.cursor()
        c.execute("INSERT INTO clientes (nome) VALUES (?)", (nome,))
        conn.commit()
        conn.close()
        return redirect(url_for("index"))
    return render_template("clientes.html")

# ---------------- HISTÓRICO ----------------
@app.route("/cliente/<int:cliente_id>")
@login_required
def historico(cliente_id):
    conn = sqlite3.connect("/tmp/fiado.db")
    c = conn.cursor()
    c.execute("SELECT nome FROM clientes WHERE id=?", (cliente_id,))
    cliente = c.fetchone()[0]

    c.execute("""
        SELECT id, data, valor_compra, valor_pago
        FROM vendas WHERE cliente_id=? ORDER BY data DESC
    """, (cliente_id,))
    vendas = c.fetchall()

    c.execute("""
        SELECT IFNULL(SUM(valor_compra),0), IFNULL(SUM(valor_pago),0)
        FROM vendas WHERE cliente_id=?
    """, (cliente_id,))
    total_compra, total_pago = c.fetchone()
    saldo = total_compra - total_pago

    conn.close()
    return render_template(
        "historico.html",
        cliente_id=cliente_id,
        cliente=cliente,
        vendas=vendas,
        total_compra=total_compra,
        total_pago=total_pago,
        saldo=saldo
    )

# ---------------- LANÇAMENTO ----------------
@app.route("/lancar/<int:cliente_id>", methods=["GET", "POST"])
@login_required
def lancar(cliente_id):
    if request.method == "POST":
        data = request.form["data"]
        valor_compra = float(request.form["valor_compra"] or 0)
        valor_pago = float(request.form["valor_pago"] or 0)

        conn = sqlite3.connect("/tmp/fiado.db")
        c = conn.cursor()
        c.execute("""
            INSERT INTO vendas (cliente_id, data, valor_compra, valor_pago)
            VALUES (?, ?, ?, ?)
        """, (cliente_id, data, valor_compra, valor_pago))
        venda_id = c.lastrowid
        conn.commit()
        conn.close()

        session["ultima_acao"] = {
            "tipo": "lancamento",
            "dados": {"id": venda_id}
        }

        flash("Lançamento adicionado com sucesso! (pode desfazer abaixo 👇)")
        return redirect(url_for("index"))

    hoje = datetime.today().strftime("%Y-%m-%d")
    return render_template("lancar.html", cliente_id=cliente_id, data=hoje)

# ---------------- PAGAMENTO DIRETO ----------------
@app.route("/pagamento/<int:cliente_id>", methods=["POST"])
@login_required
def pagamento(cliente_id):
    valor_pago = float(request.form["valor_pago"] or 0)
    data = datetime.today().strftime("%Y-%m-%d")

    conn = sqlite3.connect("/tmp/fiado.db")
    c = conn.cursor()
    c.execute("""
        INSERT INTO vendas (cliente_id, data, valor_compra, valor_pago)
        VALUES (?, ?, 0, ?)
    """, (cliente_id, data, valor_pago))
    venda_id = c.lastrowid
    conn.commit()
    conn.close()

    session["ultima_acao"] = {
        "tipo": "pagamento",
        "dados": {"id": venda_id}
    }

    flash("Pagamento atualizado com sucesso! (pode desfazer abaixo 👇)")
    return redirect(url_for("index"))

# ---------------- EDITAR CLIENTE ----------------
@app.route("/editar/<int:cliente_id>", methods=["GET", "POST"])
@login_required
def editar(cliente_id):
    conn = sqlite3.connect("/tmp/fiado.db")
    c = conn.cursor()

    if request.method == "POST":
        novo_nome = request.form["nome"]
        c.execute("UPDATE clientes SET nome=? WHERE id=?", (novo_nome, cliente_id))
        conn.commit()
        conn.close()
        flash("Cliente atualizado com sucesso!")
        return redirect(url_for("index"))

    c.execute("SELECT nome FROM clientes WHERE id=?", (cliente_id,))
    cliente = c.fetchone()
    conn.close()
    return render_template("clientes.html", cliente_id=cliente_id, nome=cliente[0])

# ---------------- EXCLUIR CLIENTE ----------------
@app.route("/excluir/<int:cliente_id>")
@login_required
def excluir(cliente_id):
    conn = sqlite3.connect("/tmp/fiado.db")
    c = conn.cursor()

    # Salvar dados antes de excluir
    c.execute("SELECT id, nome FROM clientes WHERE id=?", (cliente_id,))
    cliente = c.fetchone()
    c.execute("SELECT * FROM vendas WHERE cliente_id=?", (cliente_id,))
    vendas = c.fetchall()

    session["ultima_acao"] = {
        "tipo": "excluir_cliente",
        "dados": {"id": cliente[0], "nome": cliente[1], "vendas": vendas}
    }

    c.execute("DELETE FROM vendas WHERE cliente_id=?", (cliente_id,))
    c.execute("DELETE FROM clientes WHERE id=?", (cliente_id,))
    conn.commit()
    conn.close()

    flash("Cliente excluído com sucesso! (pode desfazer abaixo 👇)")
    return redirect(url_for("index"))

# ---------------- DESFAZER ÚLTIMA AÇÃO ----------------
@app.route("/desfazer", methods=["POST"])
@login_required
def desfazer():
    ultima_acao = session.get("ultima_acao")

    if not ultima_acao:
        flash("Nenhuma ação recente para desfazer.")
        return redirect(url_for("index"))

    conn = sqlite3.connect("/tmp/fiado.db")
    c = conn.cursor()

    if ultima_acao["tipo"] == "excluir_cliente":
        c.execute("INSERT INTO clientes (id, nome) VALUES (?, ?)", 
                  (ultima_acao["dados"]["id"], ultima_acao["dados"]["nome"]))
        for venda in ultima_acao["dados"]["vendas"]:
            c.execute("INSERT INTO vendas (id, cliente_id, data, valor_compra, valor_pago) VALUES (?, ?, ?, ?, ?)",
                      venda)
        flash(f"Cliente '{ultima_acao['dados']['nome']}' restaurado com sucesso!")

    elif ultima_acao["tipo"] == "pagamento":
        venda_id = ultima_acao["dados"]["id"]
        c.execute("DELETE FROM vendas WHERE id=?", (venda_id,))
        flash("Pagamento desfeito com sucesso!")

    elif ultima_acao["tipo"] == "lancamento":
        venda_id = ultima_acao["dados"]["id"]
        c.execute("DELETE FROM vendas WHERE id=?", (venda_id,))
        flash("Lançamento desfeito com sucesso!")

    conn.commit()
    conn.close()
    session.pop("ultima_acao", None)
    return redirect(url_for("index"))

# ---------------- LOGIN ----------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        nome = request.form["nome"]
        senha = request.form["senha"]
        conn = sqlite3.connect("/tmp/fiado.db")
        c = conn.cursor()
        c.execute("SELECT id, nome, senha FROM usuarios WHERE nome=? AND senha=?", (nome, senha))
        user = c.fetchone()
        conn.close()
        if user:
            login_user(User(*user))
            return redirect(url_for("index"))
        else:
            flash("Usuário ou senha incorretos!")
    return render_template("login.html")

# ---------------- LOGOUT ----------------
@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

# ---------------- BACKUP ----------------
@app.route("/backup")
@login_required
def backup():
    db_path = "/tmp/fiado.db"
    if os.path.exists(db_path):
        return send_file(db_path, as_attachment=True)
    else:
        flash("Banco de dados não encontrado!")
        return redirect(url_for("index"))

# ---------------- ERRO 404 ----------------
@app.errorhandler(404)
def pagina_nao_encontrada(e):
    return render_template("404.html"), 404

# ---------------- MAIN ----------------
if __name__ == "__main__":
    app.run(debug=True)
