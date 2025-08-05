#!/usr/bin/env python
import os
import click
from flask import Flask
from flask.cli import with_appcontext
from enhanced_app import app, db, User, Product, Cart, CartItem, Transaction

@app.cli.command()
def init_db():
    """Initialize the database."""
    db.create_all()
    click.echo('Database initialized.')

@app.cli.command()
def create_admin():
    """Create admin user."""
    username = click.prompt('Admin username')
    email = click.prompt('Admin email')
    password = click.prompt('Admin password', hide_input=True)
    
    admin = User.query.filter_by(username=username).first()
    if admin:
        click.echo('Admin user already exists!')
        return
    
    admin_user = User(
        username=username,
        email=email,
        role='admin'
    )
    admin_user.set_password(password)
    
    db.session.add(admin_user)
    db.session.commit()
    
    click.echo(f'Admin user {username} created successfully!')

@app.cli.command()
@click.option('--count', default=10, help='Number of sample products to create')
def seed_products(count):
    """Create sample products."""
    products = [
        ('1234567890', 'Coca Cola 330ml', 5000, 350, 'Minuman'),
        ('0987654321', 'Indomie Goreng', 3000, 85, 'Makanan Instan'),
        ('1122334455', 'Beras Premium 1kg', 15000, 1000, 'Sembako'),
        ('5544332211', 'Minyak Goreng 1L', 18000, 900, 'Sembako'),
        ('9988776655', 'Susu UHT 1L', 12000, 1050, 'Minuman'),
        ('1357924680', 'Roti Tawar', 8000, 450, 'Roti & Kue'),
        ('2468135790', 'Gula Pasir 1kg', 14000, 1000, 'Sembako'),
        ('1111222233', 'Teh Kotak 200ml', 3500, 220, 'Minuman'),
        ('4444555566', 'Biskuit Marie', 6000, 120, 'Snack'),
        ('7777888899', 'Sabun Mandi', 8500, 85, 'Toiletries'),
    ]
    
    for i, (barcode, name, price, weight, category) in enumerate(products[:count]):
        if not Product.query.filter_by(barcode=barcode).first():
            product = Product(
                barcode=barcode,
                name=name,
                price=price,
                weight=weight,
                category=category,
                stock=50
            )
            db.session.add(product)
    
    db.session.commit()
    click.echo(f'{count} sample products created!')

@app.cli.command()
def clear_carts():
    """Clear all active carts."""
    active_carts = Cart.query.filter_by(status='active').all()
    for cart in active_carts:
        CartItem.query.filter_by(cart_id=cart.id).delete()
        db.session.delete(cart)
    
    db.session.commit()
    click.echo(f'Cleared {len(active_carts)} active carts.')

@app.cli.command()
@click.option('--days', default=30, help='Keep transactions from last N days')
def cleanup_old_data(days):
    """Cleanup old transaction data."""
    from datetime import datetime, timedelta
    
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    old_transactions = Transaction.query.filter(
        Transaction.created_at < cutoff_date,
        Transaction.status == 'completed'
    ).all()
    
    for transaction in old_transactions:
        # Archive transaction data if needed
        pass
    
    click.echo(f'Found {len(old_transactions)} old transactions.')

if __name__ == '__main__':
    app.cli()