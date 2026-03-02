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
from django.core.mail import send_mail, EmailMessage
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

        # Handle reconstitute_pen
        if product.reconstitute_pen:
            reconstitute_pen_req = request.data.get('reconstitute_pen')
            if reconstitute_pen_req is None:
                return Response({"error": "reconstitute_pen status is required for this product"}, status=status.HTTP_400_BAD_REQUEST)
            reconstitute_pen_status = str(reconstitute_pen_req).lower() == 'true'
        else:
            reconstitute_pen_status = False

        cart_item, created = CartItem.objects.get_or_create(
            user=request.user,
            product=product,
            reconstitute_pen=reconstitute_pen_status
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
        extra_charge = sum(decimal.Decimal('10.00') * item.quantity for item in cart_items if item.reconstitute_pen)
        
        # Free shipping if subtotal > 250
        if subtotal > decimal.Decimal('250.00'):
            shipping_fee = decimal.Decimal('0.00')
        else:
            shipping_fee = decimal.Decimal('50.00')

        total = subtotal + shipping_fee + extra_charge
        
        # Check if eligible for free T-shirt (subtotal >= 500)
        eligible_for_free_tshirt = subtotal >= decimal.Decimal('500.00') and cart_items.exists()

        return Response({
            'items': serializer.data,
            'subtotal': subtotal,
            'extra_charge': extra_charge,
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
                    built_items.append(SimpleNamespace(product=product, quantity=ci['quantity'], reconstitute_pen=ci.get('reconstitute_pen', False)))
            except Product.DoesNotExist:
                return Response({"error": "One or more products in cart_items not found"}, status=status.HTTP_404_NOT_FOUND)
            
            cart_items = built_items
            clear_server_cart = False
            order_user = None
            customer_email = validated_data['email']

        # Validate Stock Quantity
        for item in cart_items:
            if getattr(item.product, 'stock_quantity', 0) < item.quantity:
                return Response(
                    {"error": f"Insufficient stock for '{item.product.name}'. Available: {item.product.stock_quantity}, Requested: {item.quantity}"},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Calculate totals
        total_price = sum(item.product.discounted_price * item.quantity for item in cart_items)
        
        # Free shipping if total_price > 250
        if total_price > decimal.Decimal('250.00'):
            shipping_fee = decimal.Decimal('0.00')
        else:
            shipping_fee = decimal.Decimal('50.00')
            
        extra_charge = sum(decimal.Decimal('10.00') * item.quantity for item in cart_items if getattr(item, 'reconstitute_pen', False))

        # Free T-shirt eligibility check
        eligible_for_free_tshirt = total_price >= decimal.Decimal('500.00')
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
                    extra_charge=extra_charge,
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
                        quantity=item.quantity,
                        reconstitute_pen=getattr(item, 'reconstitute_pen', False)
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

                if mode == 'payment' and shipping_fee > 0:
                    line_items.append({
                        'price_data': {
                            'currency': 'aud',
                            'product_data': {'name': 'Shipping Fee'},
                            'unit_amount': int(shipping_fee * 100),
                        },
                        'quantity': 1,
                    })
                
                if extra_charge > 0:
                    line_items.append({
                        'price_data': {
                            'currency': 'aud',
                            'product_data': {'name': 'Reconstitute Pen Charge'},
                            'unit_amount': int(extra_charge * 100),
                        },
                        'quantity': 1,
                    })
                frontend_url = settings.FRONTEND_URL

                if request.user and request.user.is_authenticated:
                    success_url = frontend_url + settings.STRIPE_SUCCESS_URL
                else:
                    success_url = frontend_url + ''

                checkout_session = stripe.checkout.Session.create(
                    payment_method_types=['card'],
                    line_items=line_items,
                    mode=mode,
                    success_url=success_url,
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
        with open('/tmp/webhook_debug.log', 'a') as f:
            import datetime
            f.write(f"\n--- {datetime.datetime.now()} ---\n")
            f.write(f"Webhook received. Request path: {request.path}\n")

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
            with open('/tmp/webhook_debug.log', 'a') as f:
                 f.write(f"Processing checkout.session.completed for session {session.get('id')}\n")
            session_id = session.get('id')
            order_id = session.get('client_reference_id')
            # Stripe metadata values are always strings
            metadata_order_id = session.get('metadata', {}).get('order_id')
            
            # Try to find order by multiple means
            order = None
            if order_id:
                order = Order.objects.filter(id=order_id).first()
            if not order and metadata_order_id:
                order = Order.objects.filter(id=metadata_order_id).first()
            if not order and session_id:
                order = Order.objects.filter(stripe_checkout_session_id=session_id).first()

            if order:
                with open('/tmp/webhook_debug.log', 'a') as f:
                    f.write(f"Order found: {order.id}. Current email in DB: {order.email}\n")
                try:
                    # Get email from multiple sources in the session
                    stripe_email = session.get('customer_email') or session.get('customer_details', {}).get('email')
                    
                    # Determine the recipient customer email strictly based on User requirement:
                    # "logged in user will get from user table and guest user will get from checkout time email address"
                    if order.user:
                        customer_email = order.user.email
                    else:
                        customer_email = order.email or stripe_email
                    
                    with open('/tmp/webhook_debug.log', 'a') as f:
                        f.write(f"Processing paid order {order.id}. Email: {customer_email}\n")

                    # Handle Guest to User conversion if needed
                    # Only convert if order.user is currently None
                    if not order.user and stripe_email:
                        # Find or create user for this email
                        user, created = User.objects.get_or_create(
                            email=stripe_email,
                            defaults={'username': stripe_email}
                        )
                        if created:
                            user.set_unusable_password()
                            user.save()
                        
                        order.user = user
                    
                    order.is_paid = True
                    order.status = 'Processing'
                    order.save()
                    
                    # Deduct stock quantity
                    for item in order.items.all():
                        if item.product and not item.stock_adjusted:
                            if item.product.stock_quantity >= item.quantity:
                                item.product.stock_quantity -= item.quantity
                            else:
                                item.product.stock_quantity = 0 
                            # Update stock status if zero
                            if item.product.stock_quantity == 0:
                                item.product.stock_status = 'out_of_stock'
                            
                            item.product.save()
                            item.stock_adjusted = True
                            item.save()

                    with open('/tmp/webhook_debug.log', 'a') as f:
                         f.write(f"Order {order.id} status updated to Processing. is_paid=True. Stock adjusted.\n")
                    print(f"Order {order.id} marked as paid successfully and stock adjusted")

                    # Send confirmation email to customer and notification to admin
                    try:
                        from_email = settings.DEFAULT_FROM_EMAIL

                        # Build order summary
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

                        pdf_bytes = None
                        try:
                            from .utils import generate_order_pdf
                            pdf_bytes = generate_order_pdf(order)
                        except Exception as pdf_err:
                            with open('/tmp/webhook_debug.log', 'a') as f:
                                f.write(f"PDF GENERATION ERROR: {str(pdf_err)}\n")
                            print(f"Error generating PDF for order {order.id}: {pdf_err}")

                        subject = f"Order Payment Successful - Order #{order.id}"
                        if customer_email:
                             if not order.email:
                                 order.email = customer_email
                                 order.save()

                             msg = EmailMessage(subject, body, from_email, [customer_email])
                             if pdf_bytes:
                                 msg.attach('Order_Details.pdf', pdf_bytes, 'application/pdf')
                             send_result = msg.send(fail_silently=False)
                             
                             with open('/tmp/webhook_debug.log', 'a') as f:
                                 f.write(f"Customer email send result: {send_result} to {customer_email}\n")
                             print(f"Email send result for order {order.id}: {send_result}")

                        admin_email = getattr(settings, 'ADMIN_EMAIL', None) or from_email
                        admin_subject = f"Order Payment Confirmed - #{order.id}"
                        admin_body = f"Order {order.id} has been paid by {customer_email}.\n\n" + body
                        
                        msg_admin = EmailMessage(admin_subject, admin_body, from_email, [admin_email])
                        if pdf_bytes:
                             msg_admin.attach('Order_Details.pdf', pdf_bytes, 'application/pdf')
                        admin_send_result = msg_admin.send(fail_silently=False)
                        
                        with open('/tmp/webhook_debug.log', 'a') as f:
                             f.write(f"Admin email send result: {admin_send_result} to {admin_email}\n")
                    except Exception as e:
                        with open('/tmp/webhook_debug.log', 'a') as f:
                             f.write(f"EMAIL ERROR: {str(e)}\n")
                        print(f"Error sending order confirmation emails for order {order.id}: {e}")
                except Exception as e:
                    with open('/tmp/webhook_debug.log', 'a') as f:
                         f.write(f"WEBHOOK ERROR: {str(e)}\n")
                    print(f"Unexpected error processing order {order.id} in webhook: {e}")
            else:
                with open('/tmp/webhook_debug.log', 'a') as f:
                     f.write(f"Order NOT FOUND. session_id: {session_id}, order_id: {order_id}\n")
                print(f"Order not found for session {session_id}, client_ref {order_id}, metadata_id {metadata_order_id}")

            # Handle Subscription Creation
            if session.get('mode') == 'subscription':
                subscription_id = session.get('subscription')
                user_email = session.get('customer_email') or session.get('customer_details', {}).get('email')
                
                if user_email:
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