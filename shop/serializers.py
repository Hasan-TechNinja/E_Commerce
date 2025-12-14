from rest_framework import serializers
from . models import Type, Product, ProductImage, Review, CartItem, Order, OrderItem, OrderAddress, ContactMessage


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
    product = ProductSerializer()
    class Meta:
        model = OrderItem
        fields = '__all__'


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