from rest_framework import serializers
from . models import Type, Product, ProductImage, Review, CartItem, Order, OrderItem, OrderAddress, ContactMessage, UserSubscription


class TypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Type
        fields = ['id', 'name']


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ['id', 'image']


class ReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = '__all__'


class ProductSerializer(serializers.ModelSerializer):
    type = TypeSerializer()
    images = ProductImageSerializer(many=True, read_only=True)
    reviews = ReviewSerializer(many=True, read_only=True)
    class Meta:
        model = Product
        fields = '__all__'

class CartItemSerializer(serializers.ModelSerializer):
    product = ProductSerializer()
    class Meta:
        model = CartItem
        fields = '__all__'


class OrderItemSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    class Meta:
        model = OrderItem
        fields = ['id', 'order', 'product', 'price', 'quantity', 'is_free_item', 'free_item_size']


class OrderAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderAddress
        fields = '__all__'


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    address = OrderAddressSerializer(read_only=True)

    class Meta:
        model = Order
        fields = '__all__'


class ContactMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactMessage
        fields = '__all__'


class UserSubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserSubscription
        fields = '__all__'


class CheckoutAddressSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    phone = serializers.CharField(max_length=100)
    address = serializers.CharField(max_length=255)
    type = serializers.ChoiceField(choices=[('home', 'Home'), ('office', 'Office')])


class GuestCartItemSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)


class GuestCheckoutSerializer(serializers.Serializer):
    cart_items = GuestCartItemSerializer(many=True)
    address = CheckoutAddressSerializer()
    email = serializers.EmailField()
    free_tshirt_size = serializers.ChoiceField(choices=['S', 'M', 'L', 'XL', 'XXL'], required=False)
    is_subscription = serializers.BooleanField(default=False)


class AuthenticatedCheckoutSerializer(serializers.Serializer):
    address = CheckoutAddressSerializer()
    free_tshirt_size = serializers.ChoiceField(choices=['S', 'M', 'L', 'XL', 'XXL'], required=False)
    is_subscription = serializers.BooleanField(default=False)