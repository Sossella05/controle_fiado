# app.py - versão consolidada e completa
from flask import (
    Flask, render_template, request, redirect, url_for, flash,
    send_file, session, abort
)
from flask_login import (
    LoginManager, UserMixin, login_user, login_required,
    logout_user, current_user
)
import sqlite3
import os
from datetime import datetime
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

DB_PATH = "/tmp/fiado.db"

app = Flask(__name__)
app.secret_key = "chave-secreta-fiado-2025"

# ---------------- FLASK-LOGIN ----------------
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

class User(UserMixin):
    def __init__(self, id, nome, senha):
        self.id = id
        self.nome = nome
        self.senha = senha

@login_manager.user_loader
def load_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, nome, senha FROM usuarios WHERE id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return User(*row)
    return None

# ---------------- DB INIT ----------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # clientes simples
    c.execute("""
    CREATE TABLE IF NOT EXISTS clientes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL
    )
    """)
    # vendas (lançamentos e pagamentos)
    c.execute("""
    CREATE TABLE IF NOT EXISTS vendas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cliente_id INTEGER,
        data TEXT,
        valor_compra REAL DEFAULT 0,
        valor_pago REAL DEFAULT 0,
        FOREIGN KEY(cliente_id) REFERENCES clientes(id)
    )
    """)
    # usuarios
    c.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT UNIQUE,
        senha TEXT
    )
    """)

    # cria usuário padrão se não existir
    c.execute("SELECT id FROM usuarios WHERE nome='admin'")
    if not c.fetchone():
        c.execute("INSERT INTO usuarios (nome, senha) VALUES (?, ?)", ("admin", "1234"))
        print("Usuário padrão criado: admin / 1234")

    conn.commit()
    conn.close()

init_db()

# ---------------- HELPERS ----------------
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    return conn

# ---------------- LOGIN ----------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        # aceitar campos 'usuario' ou 'nome' (compatibilidade)
        nome = request.form.get("usuario") or request.form.get("nome") or ""
        senha = request.form.get("senha") or ""
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT id, nome, senha FROM usuarios WHERE nome=? AND senha=?", (nome, senha))
        row = c.fetchone()
        conn.close()
        if row:
            user = User(*row)
            login_user(user)
            flash("Login efetuado!")
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

# ---------------- INDEX / DASHBOARD ----------------
@app.route("/")
@login_required
def index():
    conn = get_db_connection()
    c = conn.cursor()

    # dados por cliente (soma compras/pagos e saldo)
    c.execute("""
    SELECT clientes.id,
           clientes.nome,
           IFNULL(SUM(vendas.valor_compra),0) as total_compra,
           IFNULL(SUM(vendas.valor_pago),0) as total_pago,
           IFNULL(SUM(vendas.valor_compra),0) - IFNULL(SUM(vendas.valor_pago),0) as saldo
    FROM clientes
    LEFT JOIN vendas ON clientes.id = vendas.cliente_id
    GROUP BY clientes.id, clientes.nome
    ORDER BY clientes.nome COLLATE NOCASE
    """)
    dados = c.fetchall()

    # totais para os cards
    c.execute("SELECT COUNT(*) FROM clientes")
    total_clientes = c.fetchone()[0] or 0

    c.execute("SELECT IFNULL(SUM(valor_compra),0) FROM vendas")
    total_vendido = c.fetchone()[0] or 0.0

    c.execute("SELECT IFNULL(SUM(valor_pago),0) FROM vendas")
    total_pago = c.fetchone()[0] or 0.0

    total_devedor = total_vendido - total_pago

    conn.close()

    # prepara arrays para gráficos (opcionais)
    nomes = [row[1] for row in dados]
    saldos = [row[4] for row in dados]
    total_compras = [row[2] for row in dados]
    total_pagos = [row[3] for row in dados]

    return render_template(
        "index.html",
        dados=dados,
        nomes=nomes,
        saldos=saldos,
        total_compras=total_compras,
        total_pagos=total_pagos,
        total_clientes=total_clientes,
        total_vendido=total_vendido,
        total_pago=total_pago,
        total_devedor=total_devedor
    )

# ---------------- ADICIONAR CLIENTE (form) ----------------
@app.route("/cliente", methods=["GET", "POST"])
@login_required
def cliente():
    if request.method == "POST":
        nome = request.form.get("nome")
        if not nome:
            flash("Nome é obrigatório.")
            return redirect(url_for("cliente"))
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("INSERT INTO clientes (nome) VALUES (?)", (nome.strip(),))
        conn.commit()
        conn.close()
        flash("Cliente adicionado.")
        return redirect(url_for("index"))
    # GET -> mostra formulário (clientes.html)
    return render_template("clientes.html")

# rota alternativa /adicionar para compatibilidade com templates antigos
@app.route("/adicionar")
@login_required
def adicionar():
    return redirect(url_for("cliente"))

# ---------------- HISTÓRICO ----------------
@app.route("/cliente/<int:cliente_id>")
@login_required
def historico(cliente_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT nome FROM clientes WHERE id=?", (cliente_id,))
    r = c.fetchone()
    if not r:
        conn.close()
        abort(404)
    cliente_nome = r[0]
    c.execute("SELECT id, data, valor_compra, valor_pago FROM vendas WHERE cliente_id=? ORDER BY data DESC", (cliente_id,))
    vendas = c.fetchall()
    c.execute("SELECT IFNULL(SUM(valor_compra),0), IFNULL(SUM(valor_pago),0) FROM vendas WHERE cliente_id=?", (cliente_id,))
    totals = c.fetchone()
    total_compra = totals[0] or 0.0
    total_pago = totals[1] or 0.0
    saldo = total_compra - total_pago
    conn.close()
    return render_template("historico.html",
                           cliente_id=cliente_id,
                           cliente=cliente_nome,
                           vendas=vendas,
                           total_compra=total_compra,
                           total_pago=total_pago,
                           saldo=saldo)

# alias /historico/<id> -> redirect para /cliente/<id> (compatibilidade)
@app.route("/historico/<int:cliente_id>")
@login_required
def historico_alias(cliente_id):
    return redirect(url_for("historico", cliente_id=cliente_id))

# ---------------- LANÇAMENTO ----------------
@app.route("/lancar/<int:cliente_id>", methods=["GET", "POST"])
@login_required
def lancar(cliente_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT nome FROM clientes WHERE id=?", (cliente_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        abort(404)
    cliente_nome = row[0]
    if request.method == "POST":
        data = request.form.get("data") or datetime.today().strftime("%Y-%m-%d")
        try:
            valor_compra = float(request.form.get("valor_compra") or 0)
            valor_pago = float(request.form.get("valor_pago") or 0)
        except ValueError:
            flash("Valores inválidos.")
            return redirect(url_for("lancar", cliente_id=cliente_id))
        c.execute("INSERT INTO vendas (cliente_id, data, valor_compra, valor_pago) VALUES (?, ?, ?, ?)",
                  (cliente_id, data, valor_compra, valor_pago))
        venda_id = c.lastrowid
        conn.commit()
        conn.close()

        # registra ação para desfazer
        session["ultima_acao"] = {"tipo": "lancamento", "dados": {"id": venda_id}}
        flash("Lançamento registrado. (pode desfazer)")
        return redirect(url_for("index"))
    conn.close()
    hoje = datetime.today().strftime("%Y-%m-%d")
    return render_template("lancar.html", cliente_id=cliente_id, cliente=cliente_nome, data=hoje)

# ---------------- PAGAMENTO (via modal) ----------------
@app.route("/pagamento/<int:cliente_id>", methods=["POST"])
@login_required
def pagamento(cliente_id):
    try:
        valor_pago = float(request.form.get("valor_pago") or 0)
    except ValueError:
        flash("Valor inválido.")
        return redirect(url_for("index"))
    data = datetime.today().strftime("%Y-%m-%d")
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("INSERT INTO vendas (cliente_id, data, valor_compra, valor_pago) VALUES (?, ?, 0, ?)",
              (cliente_id, data, valor_pago))
    venda_id = c.lastrowid
    conn.commit()
    conn.close()
    session["ultima_acao"] = {"tipo": "pagamento", "dados": {"id": venda_id}}
    flash("Pagamento registrado. (pode desfazer)")
    return redirect(url_for("index"))

# ---------------- EXCLUIR CLIENTE ----------------
@app.route("/excluir/<int:cliente_id>")
@login_required
def excluir(cliente_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, nome FROM clientes WHERE id=?", (cliente_id,))
    cliente = c.fetchone()
    if not cliente:
        conn.close()
        flash("Cliente não encontrado.")
        return redirect(url_for("index"))
    c.execute("SELECT id, cliente_id, data, valor_compra, valor_pago FROM vendas WHERE cliente_id=?", (cliente_id,))
    vendas = c.fetchall()

    # salvar ultima ação na sessão para desfazer
    session["ultima_acao"] = {
        "tipo": "excluir_cliente",
        "dados": {"id": cliente[0], "nome": cliente[1], "vendas": vendas}
    }

    # remover
    c.execute("DELETE FROM vendas WHERE cliente_id=?", (cliente_id,))
    c.execute("DELETE FROM clientes WHERE id=?", (cliente_id,))
    conn.commit()
    conn.close()
    flash("Cliente excluído. (pode desfazer)")
    return redirect(url_for("index"))

# ---------------- DESFAZER ÚLTIMA AÇÃO ----------------
@app.route("/desfazer", methods=["POST"])
@login_required
def desfazer():
    ultima = session.get("ultima_acao")
    if not ultima:
        flash("Nenhuma ação para desfazer.")
        return redirect(url_for("index"))

    conn = get_db_connection()
    c = conn.cursor()
    tipo = ultima.get("tipo")

    try:
        if tipo == "excluir_cliente":
            dados = ultima["dados"]
            # recriar cliente com id original (se possível)
            c.execute("INSERT OR REPLACE INTO clientes (id, nome) VALUES (?, ?)", (dados["id"], dados["nome"]))
            # recriar vendas
            for venda in dados["vendas"]:
                # venda tuple: (id, cliente_id, data, valor_compra, valor_pago)
                c.execute("""
                    INSERT OR REPLACE INTO vendas (id, cliente_id, data, valor_compra, valor_pago)
                    VALUES (?, ?, ?, ?, ?)
                """, (venda[0], venda[1], venda[2], venda[3], venda[4]))
            flash(f"Cliente '{dados['nome']}' restaurado.")
        elif tipo in ("pagamento", "lancamento"):
            vid = ultima["dados"]["id"]
            c.execute("DELETE FROM vendas WHERE id=?", (vid,))
            flash("Última ação desfeita.")
        else:
            flash("Tipo de ação desconhecido.")
        conn.commit()
    finally:
        conn.close()
        session.pop("ultima_acao", None)

    return redirect(url_for("index"))

# ---------------- BAIXAR HISTÓRICO (PDF) ----------------
@app.route("/baixar/<int:cliente_id>")
@login_required
def baixar(cliente_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT nome FROM clientes WHERE id=?", (cliente_id,))
    r = c.fetchone()
    if not r:
        conn.close()
        abort(404)
    cliente = r[0]
    c.execute("SELECT data, valor_compra, valor_pago FROM vendas WHERE cliente_id=? ORDER BY data ASC", (cliente_id,))
    vendas = c.fetchall()
    conn.close()

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.setTitle(f"Resumo - {cliente}")

    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(40, 820, f"Resumo de {cliente}")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(40, 805, f"Data de emissão: {datetime.now().strftime('%d/%m/%Y %H:%M')}")

    y = 780
    total_compra = 0.0
    total_pago = 0.0
    for data, compra, pago in vendas:
        linha = f"{data} — Compra: R$ {compra:.2f} | Pago: R$ {pago:.2f}"
        pdf.drawString(40, y, linha)
        y -= 14
        total_compra += (compra or 0.0)
        total_pago += (pago or 0.0)
        if y < 60:
            pdf.showPage()
            y = 800
            pdf.setFont("Helvetica", 10)

    saldo = total_compra - total_pago
    y -= 10
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(40, y, f"Total Compras: R$ {total_compra:.2f}")
    pdf.drawString(260, y, f"Total Pago: R$ {total_pago:.2f}")
    y -= 18
    pdf.drawString(40, y, f"Saldo Devedor: R$ {saldo:.2f}")

    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    return send_file(buffer, as_attachment=True, download_name=f"Resumo_{cliente}.pdf", mimetype="application/pdf")

# ---------------- BACKUP DO DB ----------------
@app.route("/backup")
@login_required
def backup():
    if os.path.exists(DB_PATH):
        return send_file(DB_PATH, as_attachment=True)
    flash("Arquivo de banco de dados não encontrado.")
    return redirect(url_for("index"))

# ---------------- ERRO 404 ----------------
@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404

# ---------------- RODAR ----------------
if __name__ == "__main__":
    app.run(debug=True)
