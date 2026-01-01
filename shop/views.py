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
import stripe
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.utils import timezone

stripe.api_key = settings.STRIPE_SECRET_KEY




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

                # Prepare Stripe line items
                line_items = []
                mode = 'subscription' if is_subscription else 'payment'

                for item in cart_items:
                    if is_subscription:
                        price_id = getattr(item.product, 'stripe_subscription_price_id', None)
                    else:
                        # Force use of price_data (AUD) for one-time payments to avoid currency mismatch
                        # if the database has USD price IDs.
                        price_id = None

                    if price_id:
                        line_items.append({'price': price_id, 'quantity': item.quantity})
                    else:
                        line_items.append({
                            'price_data': {
                                'currency': 'aud',
                                'product_data': {'name': item.product.name},
                                'unit_amount': int(item.product.discounted_price * 100),
                            },
                            'quantity': item.quantity,
                        })

                if mode == 'payment':
                    line_items.append({
                        'price_data': {
                            'currency': 'aud',
                            'product_data': {'name': 'Shipping Fee'},
                            'unit_amount': int(shipping_fee * 100),
                        },
                        'quantity': 1,
                    })

                frontend_url = settings.FRONTEND_URL

                checkout_session = stripe.checkout.Session.create(
                    payment_method_types=['card'],
                    line_items=line_items,
                    mode=mode,
                    success_url=frontend_url + settings.STRIPE_SUCCESS_URL,
                    cancel_url=frontend_url + settings.STRIPE_CANCEL_URL,
                    client_reference_id=str(order.id),
                    customer_email=customer_email,
                    metadata={'order_id': order.id}
                )

                order.stripe_checkout_session_id = checkout_session.id
                order.save()

                # Clear server cart only for authenticated users
                if clear_server_cart and request.user and request.user.is_authenticated:
                    CartItem.objects.filter(user=request.user).delete()

                serializer = OrderSerializer(order)
                return Response({'order': serializer.data, 'checkout_url': checkout_session.url}, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@method_decorator(csrf_exempt, name='dispatch')
class StripeWebhookView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        payload = request.body
        sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
        event = None

        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
            )
        except ValueError as e:
            return Response(status=status.HTTP_400_BAD_REQUEST)
        except stripe.error.SignatureVerificationError as e:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        if event['type'] == 'checkout.session.completed':
            session = event['data']['object']
            order_id = session.get('client_reference_id')
            
            if order_id:
                try:
                    order = Order.objects.get(id=order_id)
                    order.is_paid = True
                    order.status = 'Processing'
                    order.save()
                except Order.DoesNotExist:
                    pass

            # Handle Subscription Creation
            if session.get('mode') == 'subscription':
                subscription_id = session.get('subscription')
                user_email = session.get('customer_email')
                
                try:
                    user = User.objects.get(email=user_email)
                    # Retrieve subscription details from Stripe to get items
                    stripe_subscription = stripe.Subscription.retrieve(subscription_id)
                    
                    for item in stripe_subscription['items']['data']:
                        price_id = item['price']['id']
                        # Find product by price_id
                        product = Product.objects.filter(stripe_subscription_price_id=price_id).first()
                        
                        if product:
                            UserSubscription.objects.create(
                                user=user,
                                product=product,
                                stripe_subscription_id=subscription_id,
                                stripe_subscription_item_id=item['id'],
                                quantity=item['quantity'],
                                status='Active'
                            )
                except Exception as e:
                    print(f"Error processing subscription webhook: {e}")
        
        return Response(status=status.HTTP_200_OK)






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

        if not all([name, whatsapp, email, project_details]):
            return Response({'error': 'All fields are required'}, status=status.HTTP_400_BAD_REQUEST)
        
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
            # Update Stripe subscription item
            if subscription.stripe_subscription_item_id:
                stripe.SubscriptionItem.modify(
                    subscription.stripe_subscription_item_id,
                    quantity=new_quantity
                )

            subscription.quantity = new_quantity
            subscription.save()

            return Response(
                {"message": "Recurring updated successfully", "quantity": new_quantity},
                status=status.HTTP_200_OK
            )

        except stripe.error.StripeError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)



class UserSubscriptionDeleteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk):
        try:
            subscription = UserSubscription.objects.get(pk=pk, user=request.user)
        except UserSubscription.DoesNotExist:
            return Response({"error": "Subscription not found"}, status=status.HTTP_404_NOT_FOUND)

        try:
            # Cancel Stripe Subscription Item
            if subscription.stripe_subscription_item_id:
                stripe.SubscriptionItem.delete(subscription.stripe_subscription_item_id)

            subscription.status = 'Cancelled'
            subscription.save()
            # Optionally delete the record
            subscription.delete() 
            
            return Response({"message": "Subscription cancelled successfully"}, status=status.HTTP_200_OK)
        except stripe.error.StripeError as e:
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