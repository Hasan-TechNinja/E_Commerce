from django.shortcuts import render
from . models import CartItem, Product, Review
from . serializers import CartItemSerializer, ProductSerializer, ReviewSerializer
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions

# Create your views here.
 
class HealthProductListView(APIView):
    def get(self, request):
        product = Product.objects.filter(category ='Health')
        serializer = ProductSerializer(product, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class MerchandiseProductView(APIView):
    def get(self, request):
        product = Product.objects.filter(category ='Merchandise')
        serializer = ProductSerializer(product, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ProductDetailView(APIView):
    def get(self, request, pk):
        try: 
            product = Product.objects.get(pk=pk)
        except Product.DoesNotExist:
            return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)
        
        serializer = ProductSerializer(product)
        
        reviews = Review.objects.filter(product=product)
        review_serializer = ReviewSerializer(reviews, many=True)
        
        related_products = Product.objects.filter(category=product.category).exclude(id=product.id)[:4]
        related_serializer = ProductSerializer(related_products, many=True)
        
        data = serializer.data
        data['reviews'] = review_serializer.data
        data['related_products'] = related_serializer.data
        
        return Response(data, status=status.HTTP_200_OK)
    

class AddToCartView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request, pk):
        try:
            product = Product.objects.get(pk=pk)
        except Product.DoesNotExist:
            return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)

        quantity = int(request.data.get('quantity', 1))

        if quantity < 1:
            return Response({"error": "Quantity must be at least 1"}, status=status.HTTP_400_BAD_REQUEST)

        cart_item, created = CartItem.objects.get_or_create(
            user=request.user,
            product=product
        )

        if not created:
            cart_item.quantity += quantity
        else:
            cart_item.quantity = quantity

        cart_item.save()

        return Response({"message": "Product added to cart"}, status=status.HTTP_200_OK)



class CartView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        cart_items = CartItem.objects.filter(user=request.user)
        serializer = CartItemSerializer(cart_items, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    def delete(self, request):
        CartItem.objects.filter(user=request.user).delete()
        return Response({'message': 'Cleared cart'}, status=status.HTTP_200_OK)
    

class RemoveCartItemView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk):
        try:
            cart_item = CartItem.objects.get(user=request.user, pk=pk)
        except CartItem.DoesNotExist:
            return Response({'error': 'Cart item not found'}, status=status.HTTP_404_NOT_FOUND)

        cart_item.delete()
        return Response({'message': 'Removed item from cart'}, status=status.HTTP_200_OK)
    

class IncreaseCartItemQuantityView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            cart_item = CartItem.objects.get(user=request.user, pk=pk)
        except CartItem.DoesNotExist:
            return Response({'error': 'Cart item not found'}, status=status.HTTP_404_NOT_FOUND)

        cart_item.quantity += 1
        cart_item.save()

        return Response({'message': 'Quantity increased', 'quantity': cart_item.quantity}, status=status.HTTP_200_OK)


class DecreaseCartItemQuantityView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            cart_item = CartItem.objects.get(user=request.user, pk=pk)
        except CartItem.DoesNotExist:
            return Response({'error': 'Cart item not found'}, status=status.HTTP_404_NOT_FOUND)

        # Prevent quantity from going below 1
        if cart_item.quantity > 1:
            cart_item.quantity -= 1
            cart_item.save()
            return Response({'message': 'Quantity decreased', 'quantity': cart_item.quantity}, status=status.HTTP_200_OK)

        return Response({'error': 'Quantity cannot be less than 1'}, status=status.HTTP_400_BAD_REQUEST)
