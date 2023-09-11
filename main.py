import stripe
from flask import Flask, render_template, redirect, url_for, flash, session
from flask_bootstrap import Bootstrap
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship
from flask_login import UserMixin, login_user, LoginManager, current_user, logout_user
import forms
from flask_wtf.csrf import CSRFProtect
import os
import random
import string
from product_manager import create_products, get_fruits

app = Flask(__name__)
app.config[
    'STRIPE_PUBLIC_KEY'] = 'pk_live_51NnqhlI7F4VhDfSMqgWOX9E6WQyrfSWbF2m8sbkFtHsYlJYgdZhEs1QbSmLQHEiT89ZgelZyyxfR16bsH7JPkeoR000TmlQAE7'
app.config['STRIPE_SECRET_KEY'] = os.environ.get("STRIPE_API_KEY")
stripe.api_key = app.config['STRIPE_SECRET_KEY']
app.config['SECRET_KEY'] = os.environ['SECRET_KEY']  # GENERATE YOUR OWN KEY
Bootstrap(app)
login_manager = LoginManager()
login_manager.init_app(app)
csrf = CSRFProtect(app)


@login_manager.user_loader
def load_user(user_id):
    return db.session.execute(db.select(User).where(User.id == int(user_id))).scalar_one_or_none()


app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///onlineshop.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(200), nullable=False)
    password = db.Column(db.String(200), nullable=False)
    cart_items = relationship("CartItem")


class Product(db.Model):
    __tablename__ = "products"
    id = db.Column(db.Integer, primary_key=True)
    product_name = db.Column(db.String(200), nullable=False)
    product_img = db.Column(db.String(500), nullable=False)
    product_description = db.Column(db.String(200), nullable=False)
    product_price = db.Column(db.Float(), nullable=False)
    price_id = db.Column(db.String(200), nullable=False)
    purchases = relationship("CartItem")


class CartItem(db.Model):
    __tablename__ = "cart-items"
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"))
    amount = db.Column(db.Integer, default=1)
    selected_product = db.relationship("Product")


with app.app_context():
    db.create_all()


def generate_random_identifier(length=10):
    characters = string.digits
    return int(''.join(random.choice(characters) for _ in range(length)))


def calculate_item_count(user_id):
    if user_id is None:
        # Anonymous user
        user_identifier = session.get("user_identifier")
        if user_identifier:
            anonymous_user_bag = db.session.execute(
                db.select(CartItem).where(CartItem.owner_id == user_identifier)
            ).all()
            item_count = sum(item.CartItem.amount for item in anonymous_user_bag)
        else:
            item_count = 0
    else:
        # Logged-in user
        user_bag = db.session.execute(
            db.select(CartItem).where(CartItem.owner_id == user_id)
        ).all()
        item_count = sum(item.CartItem.amount for item in user_bag)
    return item_count


@app.route("/")
def home():
    # Check if the examples are in the database, if not, add them
    if not db.session.execute(db.select(Product)).first():
        # The line below will only create the products on stripe if they don't already exist
        create_products()
        # get_fruits() will add the price_id to every fruit in fruit_dict and return the updated
        # dictionary
        fruit_dict = get_fruits()
        for fruit in fruit_dict:
            new_fruit = Product(product_name=fruit, product_img=fruit_dict[fruit]['image'],
                                product_description=fruit_dict[fruit]['description'],
                                product_price=fruit_dict[fruit]['price'], price_id=fruit_dict[fruit]['price_id'])
            db.session.add(new_fruit)
            db.session.commit()
    products = db.session.execute(db.select(Product).order_by(Product.product_name)).scalars()
    # The next two lines are used throughout all pages so that the shopping bag up top can keep track of the
    # number of items currently in the bag
    user_id = current_user.id if current_user.is_authenticated else None
    item_count = calculate_item_count(user_id)
    return render_template("index.html", products=products, user_bag=item_count)


@app.route("/register", methods=["GET", "POST"])
def register():
    user_id = current_user.id if current_user.is_authenticated else None
    item_count = calculate_item_count(user_id)
    form = forms.RegisterForm()
    if form.validate_on_submit():
        user_email = form.email.data
        user_password = form.password.data
        try:
            if db.session.execute(db.select(User).where(User.email == user_email)).scalar_one_or_none():
                flash("You've already registered with this e-mail, log in instead!")
                return redirect(url_for("login"))
            else:
                hashed_password = generate_password_hash(user_password, method="pbkdf2:sha256", salt_length=6)
                new_user = User(email=user_email, password=hashed_password)
                db.session.add(new_user)
                db.session.commit()
                login_user(new_user)
                user_items = db.session.execute(
                    db.select(CartItem).where(CartItem.owner_id == session["user_identifier"])).all()
                if user_items:
                    for item in user_items:
                        item.CartItem.owner_id = new_user.id
                        db.session.commit()
            return redirect(url_for("home"))
        except Exception as e:
            db.session.rollback()
            flash(f"Registration failed: {str(e)}")
    return render_template("register.html", form=form, user_bag=item_count)


@app.route("/login", methods=["GET", "POST"])
def login():
    user_id = current_user.id if current_user.is_authenticated else None
    item_count = calculate_item_count(user_id)
    form = forms.LoginForm()
    if form.validate_on_submit():
        email = form.email.data
        password = form.password.data
        user = db.session.execute(db.select(User).where(User.email == email)).scalar_one_or_none()
        if user:
            is_authenticated = check_password_hash(user.password, password)
            if is_authenticated:
                login_user(user)
                return redirect(url_for("home"))
            else:
                flash("Wrong password, please try again...")
        else:
            flash("Sorry, this e-mail was not found in our database")
    return render_template("login.html", form=form, user_bag=item_count)


@app.route("/my-fruits", methods=["GET", "POST"])
def edit_cart():
    user_id = current_user.id if current_user.is_authenticated else None
    item_count = calculate_item_count(user_id)
    try:
        user_items = db.session.execute(
            db.select(CartItem).where(CartItem.owner_id == current_user.id)).all()
    except AttributeError:
        user_items = db.session.execute(
            db.select(CartItem).where(CartItem.owner_id == session["user_identifier"])).all()
        if not user_items:
            return render_template("unavailable.html")
    total_price = 0
    for item in user_items:
        total_price += (item.CartItem.selected_product.product_price * item.CartItem.amount)
    return render_template("edit_cart.html", cart_items=user_items, user_bag=item_count, total=round(total_price, 2))


@app.route("/add-fruit/<int:product_id>")
def add_fruit(product_id):
    try:
        already_in_bag = db.session.execute(db.select(CartItem).where(CartItem.owner_id == current_user.id,
                                                                      CartItem.product_id == product_id)).scalar_one_or_none()
    except AttributeError:
        user_identifier = session.get("user_identifier")
        if not user_identifier:
            user_identifier = generate_random_identifier()
            session["user_identifier"] = user_identifier
        already_in_bag = db.session.execute(db.select(CartItem).where(CartItem.owner_id == session["user_identifier"],
                                                                      CartItem.product_id == product_id)).scalar_one_or_none()
    if already_in_bag:
        already_in_bag.amount += 1
    else:
        try:
            new_item = CartItem(product_id=product_id, owner_id=int(current_user.id))
        except AttributeError:
            new_item = CartItem(product_id=product_id, owner_id=session["user_identifier"])
        db.session.add(new_item)
    db.session.commit()
    return redirect(url_for("edit_cart"))


@app.route("/remove-from-bag/<int:product_id>")
def remove_product(product_id):
    try:
        product_to_remove = db.session.execute(db.select(CartItem).where(CartItem.owner_id == current_user.id,
                                                                         CartItem.product_id == product_id)).scalar_one_or_none()
    except AttributeError:
        product_to_remove = db.session.execute(
            db.select(CartItem).where(CartItem.owner_id == session["user_identifier"],
                                      CartItem.product_id == product_id)).scalar_one_or_none()
    if product_to_remove.amount > 1:
        product_to_remove.amount -= 1
    elif product_to_remove.amount >= 0:
        db.session.delete(product_to_remove)
    db.session.commit()
    return redirect(url_for("edit_cart") + '#bottom')


@app.route("/plus-one/<int:product_id>")
def add_one(product_id):
    try:
        product_to_increase = db.session.execute(db.select(CartItem).where(CartItem.owner_id == current_user.id,
                                                                           CartItem.product_id == product_id)).scalar_one_or_none()
    except AttributeError:
        product_to_increase = db.session.execute(
            db.select(CartItem).where(CartItem.owner_id == session["user_identifier"],
                                      CartItem.product_id == product_id)).scalar_one_or_none()
    if product_to_increase:
        product_to_increase.amount += 1
        db.session.commit()
    return redirect(url_for("edit_cart") + '#bottom')


@app.route('/create-checkout-session', methods=['GET', 'POST'])
def create_checkout_session():
    if current_user.is_authenticated:
        cart_items = db.session.execute(
            db.select(CartItem).where(CartItem.owner_id == current_user.id)).all()
    else:
        cart_items = db.session.execute(
            db.select(CartItem).where(CartItem.owner_id == session["user_identifier"])).all()
    try:
        checkout_session = stripe.checkout.Session.create(
            line_items=[{'price': item.CartItem.selected_product.price_id, 'quantity': item.CartItem.amount} for item in
                        cart_items],
            mode='payment',
            success_url=url_for('success', _external=True),
            cancel_url=url_for('edit_cart', _external=True),
        )
        return redirect(checkout_session.url, code=303)

    except Exception as e:
        return str(e)


@app.route("/success")
def success():
    return render_template("success.html")


@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("home"))


if __name__ == '__main__':
    app.run(debug=True)
