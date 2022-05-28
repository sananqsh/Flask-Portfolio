import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True


# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    user_cash = db.execute("SELECT cash FROM users WHERE id=?", session.get("user_id"))
    cash = user_cash[0]["cash"]

    user_stocks = db.execute("SELECT * FROM portfolio WHERE user_id=?", session.get("user_id"))

    prices = []
    totals = []
    aggregate = cash
    for stock in user_stocks:
        price = stock["price"]
        total = price * stock["shares"]

        prices.append(usd(price))
        aggregate += total
        totals.append(usd(total))

    return render_template("index.html", cash=usd(cash), aggregate=usd(aggregate), stocks=user_stocks, length=len(user_stocks), prices=prices, totals=totals)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        u_id = session.get("user_id")
        symbol = request.form.get("symbol").upper()     # Has bug
        shares = float(request.form.get("shares"))
        if not symbol:
            return apology("missing symbol")
        elif not lookup(symbol):
            return apology("invalid symbol")
        elif not shares:
            return apology("missing shares")
        elif shares < 1:    #or not shares.isnumeric():
            return apology("invalid shares")

        stock = lookup(symbol)
        cash_rows = db.execute("SELECT cash FROM users WHERE id=?", u_id)
        user_cash = float(cash_rows[0]["cash"])
        symbol = stock["symbol"]
        stock_name = stock["name"]
        price = stock["price"]
        total = price * shares

        if user_cash < total:
            return apology("can`t afford")

        db.execute("INSERT INTO transactions (user_id, symbol, shares, price, transacted) VALUES(?,?,?,?, CURRENT_TIMESTAMP);",
                   u_id, symbol, shares, price)
        db.execute("UPDATE users SET cash= cash - ? WHERE id=?", total, u_id)

        user_stocks = db.execute("SELECT * FROM portfolio WHERE id=?;", u_id)

        found_stock = False
        for stock in user_stocks:
            if symbol == stock["symbol"]:
                db.execute("UPDATE portfolio SET shares=shares + ?, price=? WHERE symbol=? AND user_id=?", shares, price, symbol, u_id)
                found_stock = True
        if not found_stock:
            db.execute("INSERT INTO portfolio (user_id, symbol, name, shares, price) VALUES(?,?,?,?,?)",
                       u_id, symbol, stock_name, shares, price)
        return redirect("/")
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    user_trans = db.execute("SELECT * FROM transactions WHERE user_id=?", session.get("user_id"))

    prices = []
    for tran in user_trans:
        prices.append(usd(tran["price"]))
    return render_template("history.html", trans=user_trans, length=len(user_trans), prices=prices)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        if not request.form.get("symbol"):
            return apology("missing symbol")
        elif not lookup(request.form.get("symbol")):
            return apology("invalid symbol")
        stock = lookup(request.form.get("symbol"))
        price = usd(stock["price"])
        return render_template("quote.html", stock=stock, price=price)   # User will be shown results of their submition
    else:
        return render_template("quoted.html")    # In which user inputs stock symbols ...


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        if not request.form.get("username"):
            return apology("must provide username")
        elif not request.form.get("password"):
            return apology("must provide password")
        elif not request.form.get("confirmation"):
            return apology("must provide confirmation password")
        elif request.form.get("confirmation") != request.form.get("password"):
            return apology("passwords don`t match")

        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))
        if len(rows) != 0:
            return apology("This username already exists")

        db.execute("INSERT INTO users (username, hash) VALUES(?, ?)", request.form.get(
            "username"),  generate_password_hash(request.form.get("password")))
        return redirect("/")
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    stocks = db.execute("SELECT * FROM portfolio WHERE user_id=?", session.get("user_id"))
    symbols = []
    for stock in stocks:
        symbols.append(stock["symbol"])

    if request.method == "POST":
        symbol = request.form.get("symbol").upper()
        shares = float(request.form.get("shares"))
        u_id = session.get("user_id")

        if not symbol:
            return apology("missing symbol")
        elif symbol not in symbols:
            return apology("invalid symbol")
        elif not shares:
            return apology("missing shares")
        elif shares < 1:
            return apology("invalid shares number")

        selected_stock = db.execute("SELECT * FROM portfolio WHERE user_id=? AND symbol=?", u_id, symbol)
        if shares > selected_stock[0]["shares"]:
            return apology("too many shares")

        price = selected_stock[0]["price"]
        total = price * shares
        # db
        db.execute("INSERT INTO transactions (user_id, symbol, shares, price, transacted) VALUES(?,?,?,?, CURRENT_TIMESTAMP);",
                   u_id, symbol, (-1)*shares, price)
        db.execute("UPDATE users SET cash= cash + ? WHERE id=?", total, u_id)
        db.execute("UPDATE portfolio SET shares=shares - ?, price=? WHERE user_id=? AND symbol=?", shares, price, u_id, symbol)

        updated_shares = db.execute("SELECT shares FROM portfolio WHERE user_id=? AND symbol=?", u_id, symbol)

        if updated_shares[0]["shares"] == 0:
            db.execute("DELETE FROM portfolio WHERE user_id=? AND symbol=?", u_id, symbol)

        return redirect("/")
    else:
        return render_template("sell.html", symbols=symbols)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
