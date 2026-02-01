from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from shop.models import Order, Product
from django.conf import settings
import decimal
import json
from unittest.mock import patch, MagicMock
from rest_framework.test import APIClient

class OrderStatusFlowTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='testuser', password='password')
        self.client.force_authenticate(user=self.user)
        self.product = Product.objects.create(
            name='Test Product',
            initial_price=decimal.Decimal('100.00'),
            discounted_price=decimal.Decimal('90.00'),
            category='Merchandise',
            available_sizes=['M'],
            available_colors=[{'name': 'Red', 'hex': '#FF0000'}]
        )

    def test_order_lifecycle_delivery(self):
        # 1. Create Order (Checkout)
        # We'll simulate the order creation directly or via checkout view if possible.
        # Using model creation to simulate the state after checkout view.
        order = Order.objects.create(
            user=self.user,
            total_price=decimal.Decimal('140.00'),
            shipping_fee=decimal.Decimal('50.00'),
            status='Pending',
            is_paid=False
        )
        self.assertEqual(order.status, 'Pending')

        # 2. Payment Success (IPN)
        payload = {
            'payment_status': 'finished',
            'order_id': order.id,
            'price_amount': 190.0,
            'price_currency': 'AUD'
        }
        
        import hmac
        import hashlib
        import json
        
        sorted_data = dict(sorted(payload.items()))
        data_string = json.dumps(sorted_data, separators=(',', ':'))
        sig = hmac.new(settings.NOWPAYMENTS_IPN_SECRET.encode(), data_string.encode(), hashlib.sha512).hexdigest()

        url = reverse('nowpayments-ipn')
        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_X_NOWPAYMENTS_SIG=sig
        )
        self.assertEqual(response.status_code, 200)
            
        order.refresh_from_db()
        self.assertEqual(order.status, 'Processing')
        self.assertTrue(order.is_paid)

        # 3. Confirm Delivery
        url = reverse('confirm-delivery', args=[order.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        
        order.refresh_from_db()
        self.assertEqual(order.status, 'Delivered')

    def test_order_lifecycle_cancellation(self):
        # 1. Create Order
        order = Order.objects.create(
            user=self.user,
            total_price=decimal.Decimal('140.00'),
            shipping_fee=decimal.Decimal('50.00'),
            status='Pending',
            is_paid=False
        )
        
        # 2. Cancel Order
        url = reverse('cancel-order', args=[order.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        
        order.refresh_from_db()
        self.assertEqual(order.status, 'Cancelled')

    def test_cancel_order_time_limit(self):
        # Create an old order
        from django.utils import timezone
        import datetime
        
        old_time = timezone.now() - datetime.timedelta(hours=49)
        order = Order.objects.create(
            user=self.user,
            total_price=decimal.Decimal('140.00'),
            shipping_fee=decimal.Decimal('50.00'),
            status='Pending',
            is_paid=False
        )
        order.created_at = old_time
        order.save()
        
        url = reverse('cancel-order', args=[order.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 400)
        self.assertIn('Cannot cancel order after 48 hours', str(response.content))
