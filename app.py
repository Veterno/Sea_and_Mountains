from flask import Flask, render_template, redirect, url_for, request, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
import uuid
import os
from yookassa import Configuration, Payment

app = Flask(__name__)

# Роут для раздачи картинок из папки images
@app.route('/images/<path:filename>')
def custom_static(filename):
    return send_from_directory('images', filename)

# Настройки
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///travel.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'dev-secret-key'

db = SQLAlchemy(app)

# --- МОДЕЛИ ---

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    balance = db.Column(db.Float, default=0.0)

class Tour(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    price = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(500))
    image_url = db.Column(db.String(500))

class CartItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    tour_id = db.Column(db.Integer, db.ForeignKey('tour.id'), nullable=False)
    tour = db.relationship('Tour', backref='in_carts')

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='pending')
    payment_id = db.Column(db.String(100), unique=True)

# --- ЮKASSA ---
# Тестовые ключи (замени на свои из ЛК ЮKassa)
Configuration.configure('123456', 'test_...')

# --- ИНИЦИАЛИЗАЦИЯ ---

def init_db():
    with app.app_context():
        db.create_all()
        if User.query.count() == 0:
            user = User(username='Traveler', balance=0.0)
            db.session.add(user)
            
            tours = [
                Tour(title="Лазурный берег", category="Море", price=50000, description="Отдых на юге Франции", image_url="images\Лазурный берег.jpg"),
                Tour(title="Тропический рай", category="Море", price=75000, description="Мальдивские острова", image_url="images\Тропический рай.jpg"),
                Tour(title="Альпийская сказка", category="Горы", price=60000, description="Горнолыжный курорт в Альпах", image_url="images\Альпийская сказка.jpg"),
                Tour(title="Вершины Кавказа", category="Горы", price=35000, description="Поход по горам Кавказа", image_url="images\Вершины Кавказа.jpg"),
                Tour(title="Огни Токио", category="Страны", price=120000, description="Путешествие в Японию", image_url="images\Огни Токио.jpg"),
                Tour(title="Римские каникулы", category="Страны", price=55000, description="Исторический тур по Риму", image_url="images\Римские каникулы.jpg"),
            ]
            db.session.add_all(tours)
            db.session.commit()

# --- РОУТЫ ---

@app.route('/')
def index():
    tours = Tour.query.all()
    user = User.query.first()
    return render_template('index.html', tours=tours, user=user)

@app.route('/add-to-cart/<int:tour_id>', methods=['POST'])
def add_to_cart(tour_id):
    user = User.query.first()
    item = CartItem(user_id=user.id, tour_id=tour_id)
    db.session.add(item)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/profile')
def profile():
    user = User.query.first()
    cart_items = CartItem.query.filter_by(user_id=user.id).all()
    orders = Order.query.filter_by(user_id=user.id).order_by(Order.id.desc()).all()
    total_cart = sum(item.tour.price for item in cart_items)
    return render_template('profile.html', user=user, cart_items=cart_items, orders=orders, total_cart=total_cart)

@app.route('/pay', methods=['POST'])
def pay():
    user = User.query.first()
    cart_items = CartItem.query.filter_by(user_id=user.id).all()
    if not cart_items:
        return redirect(url_for('profile'))
    
    total_amount = sum(item.tour.price for item in cart_items)
    
    try:
        payment = Payment.create({
            "amount": {"value": str(total_amount), "currency": "RUB"},
            "confirmation": {"type": "redirect", "return_url": url_for('profile', _external=True)},
            "capture": True,
            "description": f"Оплата туров для {user.username}"
        }, str(uuid.uuid4()))
        
        order = Order(user_id=user.id, amount=total_amount, payment_id=payment.id)
        db.session.add(order)
        db.session.commit()
        
        return redirect(payment.confirmation.confirmation_url)
    except Exception as e:
        return f"Ошибка ЮKassa: {e}", 500

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    if data.get('event') == 'payment.succeeded':
        payment_id = data['object']['id']
        order = Order.query.filter_by(payment_id=payment_id).first()
        if order and order.status != 'succeeded':
            order.status = 'succeeded'
            user = User.query.get(order.user_id)
            user.balance += order.amount
            CartItem.query.filter_by(user_id=user.id).delete()
            db.session.commit()
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=8010)
