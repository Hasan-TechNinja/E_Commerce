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
    # Deprecated single size field - use available_sizes instead
    size = models.CharField(choices=PRODUCT_SIZE_CHOICES, max_length=2, blank=True, null=True)
    # New fields for multiple sizes and colors
    available_sizes = models.JSONField(default=list, blank=True, help_text="Array of available sizes, e.g. ['S', 'M', 'L']")
    available_colors = models.JSONField(default=list, blank=True, help_text="Array of color objects, e.g. [{'hex': '#FF0000', 'name': 'Red'}]")
    logo = models.ImageField(upload_to='products/')
    certificate = models.FileField(upload_to='certificate/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    order_count = models.IntegerField(default=0)
    color_code = models.CharField(max_length=500, blank=True, null=True)  # Deprecated - use available_colors
    stripe_one_time_price_id = models.CharField(max_length=100, blank=True, null=True)
    stripe_subscription_price_id = models.CharField(max_length=100, blank=True, null=True)

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
    selected_size = models.CharField(max_length=3, blank=True, null=True)
    selected_color_hex = models.CharField(max_length=7, blank=True, null=True)
    selected_color_name = models.CharField(max_length=50, blank=True, null=True)
    added_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)

    def __str__(self):
        return f"{self.quantity} of {self.product.name}"
    


class Order(models.Model):
    ORDER_STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Processing', 'Processing'),
        ('Shipped', 'Shipped'),
        ('Delivered', 'Delivered'),
        ('Cancelled', 'Cancelled'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    shipping_fee = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=ORDER_STATUS_CHOICES, default='Pending')
    is_paid = models.BooleanField(default=False)
    stripe_checkout_session_id = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Order {self.id} by {self.user.username}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.IntegerField(default=1)
    ordered_size = models.CharField(max_length=3, blank=True, null=True)
    ordered_color_hex = models.CharField(max_length=7, blank=True, null=True)
    ordered_color_name = models.CharField(max_length=50, blank=True, null=True)
    is_free_item = models.BooleanField(default=False)
    free_item_size = models.CharField(max_length=3, choices=[('S', 'S'), ('L', 'L'), ('M', 'M'), ('XL', 'XL'), ('XXL', 'XXL')], blank=True, null=True)

    def __str__(self):
        if self.is_free_item:
            return f"Free T-shirt ({self.free_item_size}) in Order {self.order.id}"
        return f"{self.quantity} x {self.product.name} in Order {self.order.id}"


class OrderAddress(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=100)
    address = models.CharField(max_length=100)
    type = models.CharField(choices=[('home', 'Home'), ('office', 'Office')], max_length=10)

    def __str__(self):
        return f"Address for Order {self.order.id}"    


class ContactMessage(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, blank=True, null=True)
    name = models.CharField(max_length=255)
    whatsapp = models.CharField(max_length=20)
    email = models.EmailField()
    project_details = models.TextField()
    sent_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Message from {self.name} - {self.project_details[:30]}..."


class UserSubscription(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='subscriptions')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    stripe_subscription_id = models.CharField(max_length=255)
    stripe_subscription_item_id = models.CharField(max_length=255, blank=True, null=True)
    quantity = models.IntegerField(default=1)
    status = models.CharField(max_length=50, default='Active')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.product.name} ({self.status})"