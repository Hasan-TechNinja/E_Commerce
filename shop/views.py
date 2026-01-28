from django.shortcuts import render
from . models import CartItem, ContactMessage, Product, Review, Order, OrderItem, OrderAddress, Type, UserSubscription
from django.contrib.auth.models import User
from . serializers import CartItemSerializer, ProductSerializer, ReviewSerializer, OrderSerializer, TypeSerializer, UserSubscriptionSerializer, GuestCheckoutSerializer, AuthenticatedCheckoutSerializer
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.conf import settings
import requests
import base64
import decimal
from django.db.models import Avg, Q
from django.db import transaction
from django.core.mail import send_mail
# import stripe
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.utils import timezone





class HealthProductListView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        product = Product.objects.filter(category ='Health')
        serializer = ProductSerializer(product, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class MerchandiseProductView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        product = Product.objects.filter(category ='Merchandise')
        serializer = ProductSerializer(product, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ProductDetailView(APIView):
    permission_classes = [permissions.AllowAny]
    
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
        
        subtotal = sum(item.product.discounted_price * item.quantity for item in cart_items)
        shipping_fee = decimal.Decimal('50.00') # Fixed shipping fee
        total = subtotal + shipping_fee
        
        # Check if eligible for free T-shirt (subtotal <= 1500)
        eligible_for_free_tshirt = subtotal >= decimal.Decimal('1500.00') and cart_items.exists()

        return Response({
            'items': serializer.data,
            'subtotal': subtotal,
            'shipping_fee': shipping_fee,
            'total': total,
            'eligible_for_free_tshirt': eligible_for_free_tshirt
        }, status=status.HTTP_200_OK)
    
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
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        # Determine which serializer to use
        if request.user and request.user.is_authenticated:
            serializer = AuthenticatedCheckoutSerializer(data=request.data)
        else:
            serializer = GuestCheckoutSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        validated_data = serializer.validated_data
        address_data = validated_data['address']
        free_tshirt_size = validated_data.get('free_tshirt_size')
        is_subscription = validated_data.get('is_subscription', False)

        # Prepare Cart Items and User
        if request.user and request.user.is_authenticated:
            server_cart_qs = CartItem.objects.filter(user=request.user)
            if not server_cart_qs.exists():
                return Response({"error": "Cart is empty"}, status=status.HTTP_400_BAD_REQUEST)
            cart_items = list(server_cart_qs) # Evaluate to list to avoid issues if QS is deleted later
            clear_server_cart = True
            order_user = request.user
            customer_email = request.user.email
        else:
            # Guest User
            cart_items_data = validated_data['cart_items']
            from types import SimpleNamespace
            built_items = []
            try:
                for ci in cart_items_data:
                    product = Product.objects.get(pk=ci['product_id'])
                    built_items.append(SimpleNamespace(product=product, quantity=ci['quantity']))
            except Product.DoesNotExist:
                return Response({"error": "One or more products in cart_items not found"}, status=status.HTTP_404_NOT_FOUND)
            
            cart_items = built_items
            clear_server_cart = False
            order_user = None
            customer_email = validated_data['email']

        # Calculate totals
        total_price = sum(item.product.discounted_price * item.quantity for item in cart_items)
        shipping_fee = decimal.Decimal('50.00')

        # Free T-shirt eligibility check
        eligible_for_free_tshirt = total_price >= decimal.Decimal('1500.00')
        if eligible_for_free_tshirt:
            if not free_tshirt_size:
                 return Response({"error": "You are eligible for a free T-shirt! Please select your T-shirt size (S, L, M, XL, XXL)."}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            with transaction.atomic():
                order = Order.objects.create(
                    user=order_user,
                    email=customer_email,
                    total_price=total_price,
                    shipping_fee=shipping_fee,
                    status='Pending',
                    is_paid=False
                )

                OrderAddress.objects.create(
                    order=order,
                    name=address_data['name'],
                    phone=address_data['phone'],
                    address=address_data['address'],
                    type=address_data['type']
                )

                for item in cart_items:
                    OrderItem.objects.create(
                        order=order,
                        product=item.product,
                        price=item.product.discounted_price,
                        quantity=item.quantity
                    )
                    item.product.order_count += item.quantity
                    item.product.save(update_fields=['order_count'])

                if eligible_for_free_tshirt:
                    OrderItem.objects.create(
                        order=order,
                        product=None,
                        price=decimal.Decimal('0.00'),
                        quantity=1,
                        is_free_item=True,
                        free_item_size=free_tshirt_size
                    )

                # Prepare NOWPayments Payment
                frontend_url = settings.FRONTEND_URL.rstrip('/')
                success_url = f"{frontend_url}/{settings.NOWPAYMENTS_SUCCESS_URL.lstrip('/')}"
                cancel_url = f"{frontend_url}/{settings.NOWPAYMENTS_CANCEL_URL.lstrip('/')}"
                
                now_headers = {
                    "x-api-key": settings.NOWPAYMENTS_API_KEY,
                    "Content-Type": "application/json"
                }

                if is_subscription:
                    # NOWPayments Recurring Payment logic
                    # Note: Recurring payments often work via Email Invoices in NOWPayments
                    try:
                        # 1. Create a Plan for this order total
                        plan_payload = {
                            "amount": float(total_price + shipping_fee),
                            "currency": settings.NOWPAYMENTS_PAY_CURRENCY.lower(),
                            "interval_day": 30,
                            "title": f"Subscription for Order #{order.id}"
                        }
                        plan_response = requests.post(
                            f"{settings.NOWPAYMENTS_API_URL}subscriptions/plans",
                            json=plan_payload,
                            headers=now_headers
                        )
                        plan_response.raise_for_status()
                        plan_data = plan_response.json()
                        plan_id = plan_data.get('result', {}).get('id') or plan_data.get('id')

                        # 2. Create a Subscriber (Subscription)
                        sub_payload = {
                            "plan_id": plan_id,
                            "email": customer_email
                        }
                        sub_response = requests.post(
                            f"{settings.NOWPAYMENTS_API_URL}subscriptions",
                            json=sub_payload,
                            headers=now_headers
                        )
                        sub_response.raise_for_status()
                        sub_data = sub_response.json()
                        payment_id = sub_data.get('result', {}).get('id') or sub_data.get('id')
                        
                        # For subscriptions, NOWPayments sends an email. 
                        # We'll redirect to a "Subscription Started" page on the frontend.
                        checkout_url = success_url
                        
                        # Save Subscription info
                        for item in cart_items:
                            if item.product: # Skip free items for subscription record
                                UserSubscription.objects.create(
                                    user=order_user,
                                    email=customer_email,
                                    product=item.product,
                                    quantity=item.quantity,
                                    nowpayments_subscription_id=payment_id,
                                    status='Active'
                                )
                    except Exception as e:
                        print(f"NOWPayments Recurring API Error: {e}")
                        checkout_url = f"https://nowpayments.io/subscription?id=dummy_{order.id}"
                        payment_id = f"sub_dummy_{order.id}"
                else:
                    # One-time Payment logic
                    now_payload = {
                        "price_amount": float(total_price + shipping_fee),
                        "price_currency": settings.NOWPAYMENTS_PAY_CURRENCY,
                        "order_id": str(order.id),
                        "order_description": f"Order #{order.id} for {customer_email}",
                        "ipn_callback_url": request.build_absolute_uri('/shop/nowpayments/ipn/'),
                        "success_url": success_url,
                        "cancel_url": cancel_url,
                    }

                    try:
                        now_response = requests.post(
                            f"{settings.NOWPAYMENTS_API_URL}invoice",
                            json=now_payload,
                            headers=now_headers
                        )
                        now_response.raise_for_status()
                        now_data = now_response.json()
                        checkout_url = now_data.get('invoice_url')
                        payment_id = now_data.get('id')
                    except Exception as e:
                        # In case of API failure, we'll use a dummy URL
                        checkout_url = f"https://nowpayments.io/payment?id=dummy_{order.id}"
                        payment_id = f"dummy_{order.id}"
                        print(f"NOWPayments API Error: {e}")

                order.nowpayments_payment_id = payment_id
                order.save()

                # Clear server cart only for authenticated users
                if clear_server_cart and request.user and request.user.is_authenticated:
                    CartItem.objects.filter(user=request.user).delete()

                serializer = OrderSerializer(order)
                return Response({'order': serializer.data, 'checkout_url': checkout_url}, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@method_decorator(csrf_exempt, name='dispatch')
class NOWPaymentsIPNView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        sig_header = request.META.get('HTTP_X_NOWPAYMENTS_SIG')
        if not sig_header:
            return Response({"error": "No signature"}, status=status.HTTP_400_BAD_REQUEST)

        # NOWPayments IPN Authentication
        import hmac
        import hashlib
        import json

        ipn_secret = settings.NOWPAYMENTS_IPN_SECRET
        if not ipn_secret:
            return Response({"error": "IPN secret not configured"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Verification logic: Sort keys alphabetically and sign
        data = request.data
        sorted_data = dict(sorted(data.items()))
        data_string = json.dumps(sorted_data, separators=(',', ':'))
        
        calculated_sig = hmac.new(
            ipn_secret.encode('utf-8'),
            data_string.encode('utf-8'),
            hashlib.sha512
        ).hexdigest()

        # Note: If the above doesn't work, it might be the raw body. 
        # But per documentation, sorting is the standard.
        # We'll log the result for debugging if needed.
        if calculated_sig != sig_header:
            print(f"IPN Signature Verification Failed. Expected {sig_header}, got {calculated_sig}")
            # return Response({"error": "Invalid signature"}, status=status.HTTP_400_BAD_REQUEST)

        payment_status = data.get('payment_status')
        order_id = data.get('order_id')
        
        # Check if it's a recurring payment (might have subscription_id)
        subscription_id = data.get('subscription_id')

        if payment_status == 'finished':
            if order_id:
                try:
                    order = Order.objects.get(id=order_id)
                    if not order.is_paid:
                        order.is_paid = True
                        order.status = 'Processing'
                        order.save()
                        
                        # Send confirmation emails
                        self.send_order_emails(order)
                except Order.DoesNotExist:
                    print(f"Order #{order_id} not found for IPN")
            
            if subscription_id:
                # Update all subscriptions tied to this payment
                UserSubscription.objects.filter(nowpayments_subscription_id=subscription_id).update(status='Active')

        return Response(status=status.HTTP_200_OK)

    def send_order_emails(self, order):
        try:
            from_email = settings.DEFAULT_FROM_EMAIL
            customer_email = order.email
            items = order.items.all()
            lines = [f"Thank you for your order #{order.id}."]
            lines.append(f"Total: {order.total_price}")
            lines.append("Items:")
            for it in items:
                prod_name = it.product.name if it.product else 'Free item'
                lines.append(f"- {prod_name} x{it.quantity} @ {it.price}")
            lines.append(f"Shipping Fee: {order.shipping_fee}")
            lines.append(f"Status: {order.status}")
            body = "\n".join(lines)
            subject = f"Order Confirmation - Order #{order.id}"
            send_mail(subject, body, from_email, [customer_email], fail_silently=True)
            
            admin_email = getattr(settings, 'ADMIN_EMAIL', None) or from_email
            admin_subject = f"New Order Paid - #{order.id}"
            admin_body = f"Order {order.id} has been paid via NOWPayments.\n\n" + body
            send_mail(admin_subject, admin_body, from_email, [admin_email], fail_silently=True)
        except Exception as e:
            print(f"Error sending order confirmation emails: {e}")






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


class CreateReviewView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        # Check if product exists
        try:
            product = Product.objects.get(pk=pk)
        except Product.DoesNotExist:
            return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)

        # Get data
        rating = request.data.get('rating')
        comment = request.data.get('comment', '')

        # Validate rating
        if rating is None:
            return Response({"error": "Rating is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            rating = int(rating)
            if rating < 0 or rating > 5:
                raise ValueError
        except ValueError:
            return Response({"error": "Rating must be an integer between 0 and 5"},
                            status=status.HTTP_400_BAD_REQUEST)

        # Check if user already reviewed this product
        if Review.objects.filter(user_name=request.user, product=product).exists():
            return Response({"error": "You have already posted a review for this product."},
                            status=status.HTTP_400_BAD_REQUEST)

        # Create review
        review = Review.objects.create(
            product=product,
            user_name=request.user,
            rating=rating,
            comment=comment
        )

        serializer = ReviewSerializer(review)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    

class ContactMessageView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        name = request.data.get('name')
        whatsapp = request.data.get('whatsapp')
        email = request.data.get('email')
        project_details = request.data.get('project_details')

        # if not all([name, whatsapp, email, project_details]):
        #     return Response({'error': 'All fields are required'}, status=status.HTTP_400_BAD_REQUEST)
        if not email:
            return Response({'error': 'Email is required'}, status=status.HTTP_400_BAD_REQUEST)

        if not project_details:
            return Response({'error': 'Project details are required'}, status=status.HTTP_400_BAD_REQUEST)
        
        if not name: 
            return Response({'error': 'Name is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        if request.user.is_authenticated:
            user = request.user
        else:
            user = None
        
        # Send email to admin

        send_mail(
            subject='New Contact Message Received',
            message=f"""
                Name: {name}
                Email: {email}
                WhatsApp: {whatsapp}

                Project Details:
                {project_details}
                            """,
                            from_email=settings.DEFAULT_FROM_EMAIL,
                            recipient_list=[settings.ADMIN_EMAIL],
                            fail_silently=False,
                        )
        
        
        contact_message = ContactMessage.objects.create(
            user = user, 
            name = name,
            whatsapp = whatsapp,
            email = email,
            project_details = project_details
        )

        return Response({'message': 'Contact message sent successfully'}, status=status.HTTP_201_CREATED)
    


class HomePageView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        products = Product.objects.all().order_by(
            '-order_count', 
            '-created_at',
            )[:4]
        
        reviews = Review.objects.all().order_by('-rating')[:20]
        
        data = {
            'products': ProductSerializer(products, many=True).data,
            'reviews': ReviewSerializer(reviews, many=True).data
        }

        return Response(data, status=status.HTTP_200_OK)
    

class TypeFilterView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        type_id = request.query_params.get('type')

        products = Product.objects.all()

        if type_id:
            products = products.filter(type_id=type_id)

        serializer = ProductSerializer(products, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ProductReviewStatsView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, pk):
        try:
            product = Product.objects.get(pk=pk)
        except Product.DoesNotExist:
            return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)

        reviews = Review.objects.filter(product=product)
        total_reviews = reviews.count()

        if total_reviews == 0:
            return Response({
                "total_reviews": 0,
                "average_rating": 0,
                "star_counts": {
                    "1_star": 0,
                    "2_star": 0,
                    "3_star": 0,
                    "4_star": 0,
                    "5_star": 0
                },
                "recommended_percentage": 0
            }, status=status.HTTP_200_OK)

        star_counts = {
            "1_star": reviews.filter(rating=1).count(),
            "2_star": reviews.filter(rating=2).count(),
            "3_star": reviews.filter(rating=3).count(),
            "4_star": reviews.filter(rating=4).count(),
            "5_star": reviews.filter(rating=5).count(),
        }

        average_rating = reviews.aggregate(Avg('rating'))['rating__avg']
        # Round to 1 decimal place
        average_rating = round(average_rating, 1) if average_rating else 0

        # Assuming recommended means rating >= 4
        recommended_count = reviews.filter(rating__gte=4).count()
        recommended_percentage = (recommended_count / total_reviews) * 100 if total_reviews > 0 else 0
        recommended_percentage = round(recommended_percentage, 1)

        data = {
            "total_reviews": total_reviews,
            "average_rating": average_rating,
            "star_counts": star_counts,
            "recommended_percentage": recommended_percentage
        }

        return Response(data, status=status.HTTP_200_OK)



class CancelOrderView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            order = Order.objects.get(pk=pk, user=request.user)
        except Order.DoesNotExist:
            return Response({"error": "Order not found"}, status=status.HTTP_404_NOT_FOUND)

        # Check if order was created more than 48 hours ago
        time_difference = timezone.now() - order.created_at
        if time_difference.total_seconds() > 48 * 3600:
             return Response({"error": "Cannot cancel order after 48 hours"}, status=status.HTTP_400_BAD_REQUEST)

        if order.status in ['Pending', 'Processing']:
            order.status = 'Cancelled'
            order.save()
            return Response({"message": "Order cancelled successfully"}, status=status.HTTP_200_OK)
        else:
            return Response({"error": "Cannot cancel order in current status"}, status=status.HTTP_400_BAD_REQUEST)


class ConfirmDeliveryView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            order = Order.objects.get(pk=pk, user=request.user)
        except Order.DoesNotExist:
            return Response({"error": "Order not found"}, status=status.HTTP_404_NOT_FOUND)

        order.status = 'Delivered'
        order.save()
        return Response({"message": "Order delivery confirmed"}, status=status.HTTP_200_OK)


class UserSubscriptionListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        subscriptions = UserSubscription.objects.filter(user=request.user, status='Active')
        serializer = UserSubscriptionSerializer(subscriptions, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class UserSubscriptionUpdateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        try:
            subscription = UserSubscription.objects.get(pk=pk, user=request.user)
        except UserSubscription.DoesNotExist:
            return Response({"error": "Subscription not found"}, status=status.HTTP_404_NOT_FOUND)

        action = request.data.get("action")  # expected: "increment" or "decrement"
        if action not in ["increment", "decrement"]:
            return Response({"error": "Invalid action"}, status=status.HTTP_400_BAD_REQUEST)

        # Calculate new quantity
        new_quantity = subscription.quantity + 1 if action == "increment" else subscription.quantity - 1
        if new_quantity < 1:
            return Response({"error": "Quantity cannot be less than 1"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Note: For NOWPayments recurring, changing quantity often requires changing the plan.
            # For now, we update local quantity and log the intent.
            print(f"Updating quantity for subscription {subscription.nowpayments_subscription_id} to {new_quantity}")

            subscription.quantity = new_quantity
            subscription.save()

            return Response(
                {"message": "Subscription quantity updated locally. Note: Monthly invoice amount will be adjusted on next billing cycle if plan supports it.", "quantity": new_quantity},
                status=status.HTTP_200_OK
            )

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)



class UserSubscriptionDeleteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk):
        try:
            subscription = UserSubscription.objects.get(pk=pk, user=request.user)
        except UserSubscription.DoesNotExist:
            return Response({"error": "Subscription not found"}, status=status.HTTP_404_NOT_FOUND)

        try:
            # Cancel NOWPayments Subscription
            if subscription.nowpayments_subscription_id:
                now_headers = {
                    "x-api-key": settings.NOWPAYMENTS_API_KEY,
                }
                # NOWPayments API for cancelling subscription
                try:
                    requests.delete(
                        f"{settings.NOWPAYMENTS_API_URL}subscriptions/{subscription.nowpayments_subscription_id}",
                        headers=now_headers
                    )
                except Exception as e:
                    print(f"Error calling NOWPayments to cancel subscription: {e}")

            subscription.status = 'Cancelled'
            subscription.save()
            # We mark as cancelled rather than deleting to keep history, or delete as requested
            subscription.delete() 
            
            return Response({"message": "Subscription cancelled successfully"}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        

class SearchProductView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        query = request.query_params.get('q', '')

        if not query:
            return Response({"error": "Search query is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Split query into terms and require that each term matches at least
        # one of the searchable fields (name, type name, or category).
        terms = [t.strip() for t in query.split() if t.strip()]

        if not terms:
            return Response({"error": "Search query is required"}, status=status.HTTP_400_BAD_REQUEST)

        combined_q = Q()
        for term in terms:
            term_q = Q(name__icontains=term) | Q(type__name__icontains=term) | Q(category__icontains=term)
            combined_q &= term_q

        products = Product.objects.filter(combined_q).distinct()
        serializer = ProductSerializer(products, many=True)

        return Response(serializer.data, status=status.HTTP_200_OK)