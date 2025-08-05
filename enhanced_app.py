

# ===========================
# enhanced_app.py - Enhanced Main Application
# ===========================

from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, abort
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime
import os
import logging
from logging.handlers import RotatingFileHandler

# Import configuration
from config import config

app = Flask(__name__)

# Load configuration based on environment
config_name = os.environ.get('FLASK_ENV', 'development')
app.config.from_object(config[config_name])

db = SQLAlchemy(app)

# Set up logging for production
if not app.debug and not app.testing:
    if not os.path.exists('logs'):
        os.mkdir('logs')
    
    file_handler = RotatingFileHandler('logs/smartcart.log', maxBytes=10240, backupCount=10)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('Smart Shopping Cart startup')

# Enhanced Models with additional validation
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), default='user', index=True)
    is_active = db.Column(db.Boolean, default=True)
    last_login = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def update_last_login(self):
        self.last_login = datetime.utcnow()
        db.session.commit()
    
    def __repr__(self):
        return f'<User {self.username}>'

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    barcode = db.Column(db.String(50), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False)
    weight = db.Column(db.Float, nullable=False)
    stock = db.Column(db.Integer, default=0)
    category = db.Column(db.String(50))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<Product {self.name}>'
    
    def update_stock(self, quantity):
        """Update stock with validation"""
        if self.stock + quantity < 0:
            raise ValueError("Insufficient stock")
        self.stock += quantity
        self.updated_at = datetime.utcnow()

class Cart(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    session_id = db.Column(db.String(100), nullable=False, index=True)
    status = db.Column(db.String(20), default='active', index=True)
    total_amount = db.Column(db.Float, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user = db.relationship('User', backref='carts')
    
    def calculate_total(self):
        """Calculate total amount from cart items"""
        total = sum(item.product.price * item.quantity for item in self.items if item.product)
        self.total_amount = total
        self.updated_at = datetime.utcnow()
        return total

class CartItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cart_id = db.Column(db.Integer, db.ForeignKey('cart.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    weight_detected = db.Column(db.Float, nullable=True)
    is_validated = db.Column(db.Boolean, default=False)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    product = db.relationship('Product', backref='cart_items')
    cart = db.relationship('Cart', backref='items')
    
    def validate_weight(self, tolerance_percent=None):
        """Validate detected weight against expected weight"""
        if not self.weight_detected or not self.product:
            return False
        
        tolerance = tolerance_percent or app.config['WEIGHT_TOLERANCE_PERCENT']
        expected_weight = self.product.weight
        weight_tolerance = expected_weight * (tolerance / 100)
        
        is_valid = abs(self.weight_detected - expected_weight) <= weight_tolerance
        self.is_validated = is_valid
        return is_valid

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    cart_id = db.Column(db.Integer, db.ForeignKey('cart.id'), nullable=False)
    total_amount = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), default='pending', index=True)
    transaction_reference = db.Column(db.String(100), unique=True)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    
    user = db.relationship('User', backref='transactions')
    cart = db.relationship('Cart', backref='transaction')
    
    def generate_reference(self):
        """Generate unique transaction reference"""
        import uuid
        self.transaction_reference = f"TXN-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"
    
    def complete_transaction(self):
        """Mark transaction as completed"""
        self.status = 'completed'
        self.completed_at = datetime.utcnow()
        
        # Update product stock
        for item in self.cart.items:
            try:
                item.product.update_stock(-item.quantity)
            except ValueError as e:
                app.logger.warning(f"Stock update failed for product {item.product.id}: {e}")

# Enhanced Decorators
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Silakan login terlebih dahulu.', 'warning')
            return redirect(url_for('login'))
        
        # Check if user is still active
        user = User.query.get(session['user_id'])
        if not user or not user.is_active:
            session.clear()
            flash('Akun Anda telah dinonaktifkan.', 'danger')
            return redirect(url_for('login'))
        
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Silakan login terlebih dahulu.', 'warning')
            return redirect(url_for('login'))
        
        user = User.query.get(session['user_id'])
        if not user or user.role != 'admin' or not user.is_active:
            flash('Akses ditolak. Anda bukan administrator.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def api_key_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if not api_key or api_key != app.config['ESP32_API_KEY']:
            return jsonify({'success': False, 'message': 'Invalid API key'}), 401
        return f(*args, **kwargs)
    return decorated_function

# Enhanced Routes with error handling
@app.errorhandler(404)
def not_found_error(error):
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('errors/500.html'), 500

@app.errorhandler(403)
def forbidden_error(error):
    return render_template('errors/403.html'), 403

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        # Validation
        if not all([username, email, password, confirm_password]):
            flash('Semua field harus diisi!', 'danger')
            return render_template('register.html')
        
        if len(username) < 3:
            flash('Username minimal 3 karakter!', 'danger')
            return render_template('register.html')
        
        if len(password) < 6:
            flash('Password minimal 6 karakter!', 'danger')
            return render_template('register.html')
        
        if password != confirm_password:
            flash('Password tidak cocok!', 'danger')
            return render_template('register.html')
        
        if User.query.filter_by(username=username).first():
            flash('Username sudah digunakan!', 'danger')
            return render_template('register.html')
        
        if User.query.filter_by(email=email).first():
            flash('Email sudah digunakan!', 'danger')
            return render_template('register.html')
        
        try:
            new_user = User(username=username, email=email)
            new_user.set_password(password)
            
            db.session.add(new_user)
            db.session.commit()
            
            app.logger.info(f'New user registered: {username}')
            flash('Registrasi berhasil! Silakan login.', 'success')
            return redirect(url_for('login'))
            
        except Exception as e:
            db.session.rollback()
            app.logger.error(f'Registration error: {e}')
            flash('Terjadi kesalahan saat registrasi. Silakan coba lagi.', 'danger')
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        if not username or not password:
            flash('Username dan password harus diisi!', 'danger')
            return render_template('login.html')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            if not user.is_active:
                flash('Akun Anda telah dinonaktifkan. Hubungi administrator.', 'danger')
                return render_template('login.html')
            
            session.permanent = True
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            
            user.update_last_login()
            
            app.logger.info(f'User logged in: {user.username}')
            flash(f'Selamat datang, {user.username}!', 'success')
            
            # Redirect based on role
            if user.role == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('dashboard'))
        else:
            app.logger.warning(f'Failed login attempt for username: {username}')
            flash('Username atau password salah!', 'danger')
    
    return render_template('login.html')

@app.route('/dashboard')
@login_required  # Pastikan hanya pengguna yang sudah login yang bisa mengakses
def dashboard():
    return render_template('dashboard.html')  # Pastikan Anda memiliki template ini

@app.route('/logout')
def logout():
    username = session.get('username', 'Anonymous')
    session.clear()
    app.logger.info(f'User logged out: {username}')
    flash('Anda telah logout.', 'info')
    return redirect(url_for('index'))

# Enhanced API endpoints with better error handling
@app.route('/api/scan-barcode', methods=['POST'])
@login_required
def scan_barcode():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'Invalid JSON data'}), 400
        
        barcode = data.get('barcode', '').strip()
        weight_detected = float(data.get('weight', 0))
        
        if not barcode:
            return jsonify({'success': False, 'message': 'Barcode is required'}), 400
        
        user_id = session['user_id']
        
        # Find product
        product = Product.query.filter_by(barcode=barcode, is_active=True).first()
        if not product:
            app.logger.warning(f'Product not found for barcode: {barcode}')
            return jsonify({'success': False, 'message': 'Produk tidak ditemukan!'}), 404
        
        if product.stock <= 0:
            return jsonify({'success': False, 'message': 'Produk habis!'}), 400
        
        # Get or create active cart
        active_cart = Cart.query.filter_by(user_id=user_id, status='active').first()
        if not active_cart:
            active_cart = Cart(
                user_id=user_id,
                session_id=f"cart_{user_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
            )
            db.session.add(active_cart)
            db.session.flush()
        
        # Check if item already in cart
        existing_item = CartItem.query.filter_by(
            cart_id=active_cart.id,
            product_id=product.id
        ).first()
        
        if existing_item:
            existing_item.quantity += 1
            existing_item.weight_detected = weight_detected
            cart_item = existing_item
        else:
            cart_item = CartItem(
                cart_id=active_cart.id,
                product_id=product.id,
                weight_detected=weight_detected
            )
            db.session.add(cart_item)
        
        # Validate weight
        is_valid_weight = cart_item.validate_weight()
        
        # Update cart total
        active_cart.calculate_total()
        
        db.session.commit()
        
        app.logger.info(f'Product added to cart: {product.name} for user: {session["username"]}')
        
        return jsonify({
            'success': True,
            'product': {
                'name': product.name,
                'price': product.price,
                'expected_weight': product.weight,
                'detected_weight': weight_detected,
                'is_valid': is_valid_weight,
                'quantity': cart_item.quantity
            },
            'cart_total': active_cart.total_amount
        })
        
    except ValueError as e:
        return jsonify({'success': False, 'message': 'Invalid weight value'}), 400
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error in scan_barcode: {e}')
        return jsonify({'success': False, 'message': 'Terjadi kesalahan sistem'}), 500

@app.route('/api/checkout', methods=['POST'])
@login_required
def checkout():
    try:
        data = request.get_json()
        payment_method = data.get('payment_method', 'cash')
        
        if payment_method not in ['cash', 'card', 'ewallet']:
            return jsonify({'success': False, 'message': 'Invalid payment method'}), 400
        
        user_id = session['user_id']
        
        # Get active cart
        active_cart = Cart.query.filter_by(user_id=user_id, status='active').first()
        if not active_cart:
            return jsonify({'success': False, 'message': 'Keranjang kosong!'}), 400
        
        cart_items = CartItem.query.filter_by(cart_id=active_cart.id).all()
        if not cart_items:
            return jsonify({'success': False, 'message': 'Keranjang kosong!'}), 400
        
        # Validate all items
        for item in cart_items:
            if not item.is_validated:
                return jsonify({
                    'success': False, 
                    'message': f'Item "{item.product.name}" belum tervalidasi beratnya!'
                }), 400
        
        # Calculate total
        total_amount = active_cart.calculate_total()
        
        # Create transaction
        transaction = Transaction(
            user_id=user_id,
            cart_id=active_cart.id,
            total_amount=total_amount,
            payment_method=payment_method
        )
        transaction.generate_reference()
        
        # Update cart status
        active_cart.status = 'completed'
        
        db.session.add(transaction)
        db.session.commit()
        
        # Complete transaction (update stock)
        transaction.complete_transaction()
        db.session.commit()
        
        app.logger.info(f'Transaction completed: {transaction.transaction_reference} for user: {session["username"]}')
        
        return jsonify({
            'success': True,
            'transaction_id': transaction.id,
            'transaction_reference': transaction.transaction_reference,
            'total_amount': total_amount,
            'message': 'Checkout berhasil!'
        })
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error in checkout: {e}')
        return jsonify({'success': False, 'message': 'Terjadi kesalahan saat checkout'}), 500

# ESP32 specific API endpoint
@app.route('/api/esp32/scan', methods=['POST'])
@api_key_required
def esp32_scan():
    """Dedicated endpoint for ESP32 barcode scanning"""
    try:
        data = request.get_json()
        barcode = data.get('barcode')
        weight = float(data.get('weight', 0))
        cart_session = data.get('cart_session')  # ESP32 provides cart session ID
        
        if not all([barcode, cart_session]):
            return jsonify({'success': False, 'message': 'Missing required fields'}), 400
        
        # Find cart by session
        cart = Cart.query.filter_by(session_id=cart_session, status='active').first()
        if not cart:
            return jsonify({'success': False, 'message': 'Cart session not found'}), 404
        
        # Process similar to scan_barcode but for ESP32
        product = Product.query.filter_by(barcode=barcode, is_active=True).first()
        if not product:
            return jsonify({
                'success': False, 
                'message': 'Product not found',
                'display_message': f'Produk {barcode} tidak ditemukan'
            }), 404
        
        # Add to cart logic here...
        # (Similar to scan_barcode implementation)
        
        return jsonify({
            'success': True,
            'product_name': product.name,
            'price': product.price,
            'weight_valid': True,  # After validation
            'cart_total': cart.total_amount,
            'display_message': f'{product.name} - Rp {product.price:,.0f}'
        })
        
    except Exception as e:
        app.logger.error(f'ESP32 scan error: {e}')
        return jsonify({'success': False, 'message': 'System error'}), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        
        # Create default admin user
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin_user = User(
                username='admin',
                email='admin@smartcart.com',
                role='admin'
            )
            admin_user.set_password('admin123')
            db.session.add(admin_user)
            
            # Create demo user
            demo_user = User(
                username='user',
                email='user@smartcart.com',
                role='user'
            )
            demo_user.set_password('user123')
            db.session.add(demo_user)
            
            # Add sample products with categories
            sample_products = [
                Product(barcode='1234567890', name='Coca Cola 330ml', price=5000, weight=350, stock=50, category='Minuman'),
                Product(barcode='0987654321', name='Indomie Goreng', price=3000, weight=85, stock=100, category='Makanan Instan'),
                Product(barcode='1122334455', name='Beras Premium 1kg', price=15000, weight=1000, stock=25, category='Sembako'),
                Product(barcode='5544332211', name='Minyak Goreng 1L', price=18000, weight=900, stock=30, category='Sembako'),
                Product(barcode='9988776655', name='Susu UHT 1L', price=12000, weight=1050, stock=40, category='Minuman'),
                Product(barcode='1357924680', name='Roti Tawar', price=8000, weight=450, stock=20, category='Roti & Kue'),
            ]
            
            for product in sample_products:
                db.session.add(product)
            
            db.session.commit()
            print("Database initialized with sample data!")

            
    
    # Run application
    port = int(os.environ.get('PORT', 5000))
    debug_mode = config_name == 'development'
    
    app.run(debug=debug_mode, host='0.0.0.0', port=port)