from django.shortcuts import render
from . models import CartItem, Product, Review, Order, OrderItem, OrderAddress
from . serializers import CartItemSerializer, ProductSerializer, ReviewSerializer, OrderSerializer
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.conf import settings
import requests
import base64
import decimal
from django.db import transaction
# PayPal Config
PAYPAL_CLIENT_ID = settings.PAYPAL_CLIENT_ID
PAYPAL_SECRET = settings.PAYPAL_SECRET
PAYPAL_API_BASE = settings.PAYPAL_API_BASE

def get_paypal_access_token():
    url = f"{PAYPAL_API_BASE}/v1/oauth2/token"
    headers = {
        "Accept": "application/json",
        "Accept-Language": "en_US",
    }
    data = {"grant_type": "client_credentials"}
    auth = (PAYPAL_CLIENT_ID, PAYPAL_SECRET)
    response = requests.post(url, headers=headers, data=data, auth=auth)
    response.raise_for_status()
    return response.json()["access_token"]


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


class CheckoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        cart_items = CartItem.objects.filter(user=request.user)
        if not cart_items.exists():
            return Response({"error": "Cart is empty"}, status=status.HTTP_400_BAD_REQUEST)

        # Validate Address Data First
        address_data = request.data.get('address')
        if not address_data:
             return Response({"error": "Address data is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        if not isinstance(address_data, dict):
            return Response({"error": "Address data must be a dictionary"}, status=status.HTTP_400_BAD_REQUEST)

        
        required_fields = ['name', 'phone', 'address', 'type']
        missing_fields = [field for field in required_fields if not address_data.get(field)]
        if missing_fields:
            return Response({"error": f"Missing address fields: {', '.join(missing_fields)}"}, status=status.HTTP_400_BAD_REQUEST)

        # Calculate totals
        total_price = sum(item.product.discounted_price * item.quantity for item in cart_items)
        shipping_fee = decimal.Decimal('50.00') # Fixed shipping fee for now, can be dynamic
        
        try:
            with transaction.atomic():
                # Create Order
                order = Order.objects.create(
                    user=request.user,
                    total_price=total_price,
                    shipping_fee=shipping_fee,
                    status='Pending',
                    is_paid=False
                )

                # Create Order Address
                OrderAddress.objects.create(
                    order=order,
                    name=address_data.get('name'),
                    phone=address_data.get('phone'),
                    address=address_data.get('address'),
                    type=address_data.get('type')
                )

                # Create Order Items
                for item in cart_items:
                    OrderItem.objects.create(
                        order=order,
                        product=item.product,
                        price=item.product.discounted_price,
                        quantity=item.quantity
                    )
                
                # Create PayPal Order
                access_token = get_paypal_access_token()
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {access_token}",
                }
                
                payload = {
                    "intent": "CAPTURE",
                    "purchase_units": [
                        {
                            "amount": {
                                "currency_code": "USD",
                                "value": str(total_price + shipping_fee),
                            },
                            "reference_id": str(order.id) # Link to our order
                        }
                    ],
                    "application_context": {
                        "return_url": settings.PAYPAL_RETURN_URL, 
                        "cancel_url": settings.PAYPAL_CANCEL_URL
                    }
                }
                
                response = requests.post(f"{PAYPAL_API_BASE}/v2/checkout/orders", headers=headers, json=payload)
                response.raise_for_status()
                paypal_data = response.json()
                
                order.paypal_order_id = paypal_data['id']
                order.save()

                # Clear Cart
                cart_items.delete()

                serializer = OrderSerializer(order)
                # Return approval link if needed, or just ID
                approval_link = next((link['href'] for link in paypal_data['links'] if link['rel'] == 'approve'), None)
                
                return Response({
                    'order': serializer.data, 
                    'paypal_order_id': paypal_data['id'],
                    'approval_link': approval_link
                }, status=status.HTTP_201_CREATED)

        except requests.exceptions.RequestException as e:
            return Response({"error": f"PayPal Error: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class PayPalCaptureView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        paypal_order_id = request.data.get('paypal_order_id')
        if not paypal_order_id:
            return Response({"error": "paypal_order_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Verify order exists in our DB
            order = Order.objects.get(paypal_order_id=paypal_order_id, user=request.user)
            
            if order.is_paid:
                 return Response({"message": "Order already paid"}, status=status.HTTP_200_OK)

            # Capture Payment
            access_token = get_paypal_access_token()
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {access_token}",
            }
            
            response = requests.post(f"{PAYPAL_API_BASE}/v2/checkout/orders/{paypal_order_id}/capture", headers=headers)
            response.raise_for_status()
            capture_data = response.json()
            
            if capture_data['status'] == 'COMPLETED':
                order.is_paid = True
                order.status = 'Processing'
                order.save()
                return Response({"message": "Payment successful", "status": capture_data['status']}, status=status.HTTP_200_OK)
            else:
                 return Response({"error": "Payment not completed", "details": capture_data}, status=status.HTTP_400_BAD_REQUEST)

        except Order.DoesNotExist:
            return Response({"error": "Order not found"}, status=status.HTTP_404_NOT_FOUND)
        except requests.exceptions.RequestException as e:
             return Response({"error": f"PayPal Capture Error: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)



class OrderListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        orders = Order.objects.filter(user=request.user).order_by('-created_at')
        serializer = OrderSerializer(orders, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class OrderDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        try:
            order = Order.objects.get(pk=pk, user=request.user)
        except Order.DoesNotExist:
            return Response({"error": "Order not found"}, status=status.HTTP_404_NOT_FOUND)
        
        serializer = OrderSerializer(order)
        return Response(serializer.data, status=status.HTTP_200_OK)
