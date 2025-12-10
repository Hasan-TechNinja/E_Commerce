from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator

# Create your models here.


CATEGORY_CHOICES = [
    ('Health', 'Health'),
    ('Merchandise', 'Merchandise'),
]

PRODUCT_SIZE_CHOICES = [
    ('', ''),
    ('S', 'Small'),
    ('M', 'Medium'),
    ('L', 'Large'),
    ('XL', 'Extra Large'),
]


class Type(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name
    

class Product(models.Model):
    category = models.CharField(choices=CATEGORY_CHOICES, max_length=20)
    type = models.ForeignKey(Type, on_delete=models.CASCADE, blank=True, null=True)
    name = models.CharField(max_length=100)
    initial_price = models.DecimalField(max_digits=10, decimal_places=2)
    discounted_price = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(max_length=10000)
    size = models.CharField(choices=PRODUCT_SIZE_CHOICES, max_length=2)
    logo = models.ImageField(upload_to='products/')
    created_at = models.DateTimeField(auto_now_add=True)
    order_count = models.IntegerField(default=0)

    def __str__(self):
        return self.name
    

class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='product_images/')

    def __str__(self):
        return f"Image for {self.product.name}"
    

class Review(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='reviews')
    user_name = models.ForeignKey(User, on_delete=models.CASCADE)
    rating = models.IntegerField(validators=[MinValueValidator(0), MaxValueValidator(5)])
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Review by {self.user_name} for {self.product.name}"
    


class CartItem(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='cart_items', blank=True, null=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.IntegerField(default=1)
    added_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)

    def __str__(self):
        return f"{self.quantity} of {self.product.name}"
    


class Order(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    items = models.ManyToManyField(CartItem)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.IntegerField()
    shipping_fee = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Order {self.id} by {self.user.username}"


class OrderAddress(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=100)
    address = models.CharField(max_length=100)
    type = models.CharField(choices=[('home', 'Home'), ('office', 'Office')], max_length=10)

    def __str__(self):
        return f"Address for Order {self.order.id}"    
