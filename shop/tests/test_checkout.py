from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth.models import User
from shop.models import Product, CartItem, Order, Type
from unittest.mock import patch
import requests
import unittest
from unittest.mock import patch, MagicMock
from django.conf import settings


class CheckoutViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='testuser', password='testpassword')
        self.client.force_authenticate(user=self.user)
        self.type = Type.objects.create(name='Test Type')
        self.product = Product.objects.create(
            name='Test Product',
            initial_price=100.00,
            discounted_price=90.00,
            description='Test Description',
            size='M',
            category='Merchandise',
            type=self.type
        )
        self.url = reverse('checkout')

    def test_checkout_empty_cart(self):
        data = {
            'address': {
                'name': 'Test User',
                'phone': '1234567890',
                'address': '123 Test St',
                'type': 'home'
            }
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error'], 'Cart is empty')

    def test_checkout_missing_address(self):
        CartItem.objects.create(user=self.user, product=self.product, quantity=1)
        response = self.client.post(self.url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('address', response.data)
        self.assertEqual(Order.objects.count(), 0)

    @patch('shop.views.requests.post')
    def test_checkout_success(self, mock_nowpayments_post):
        # Mock NOWPayments Invoice Response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'invoice_url': 'https://nowpayments.io/payment?id=test_payment_123',
            'id': 'test_payment_123'
        }
        mock_nowpayments_post.return_value = mock_response

        CartItem.objects.create(user=self.user, product=self.product, quantity=2)
        
        data = {
            'address': {
                'name': 'Test User',
                'phone': '1234567890',
                'address': '123 Test St',
                'type': 'home'
            },
            'free_tshirt_size': 'M'  # Added since 180 <= 1500
        }
        
        response = self.client.post(self.url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Order.objects.count(), 1)
        order = Order.objects.first()
        self.assertEqual(order.total_price, 180.00) # 90 * 2
        self.assertEqual(order.shipping_fee, 50.00)
        self.assertEqual(order.nowpayments_payment_id, 'test_payment_123')
        self.assertEqual(CartItem.objects.count(), 0)
        self.assertEqual(response.data['checkout_url'], 'https://nowpayments.io/payment?id=test_payment_123')

    @patch('shop.views.requests.post')
    def test_checkout_subscription_success(self, mock_requests_post):
        # Mock Plan creation
        mock_plan_resp = MagicMock()
        mock_plan_resp.status_code = 200
        mock_plan_resp.json.return_value = {'result': {'id': 'plan_123'}}
        
        # Mock Subscription creation
        mock_sub_resp = MagicMock()
        mock_sub_resp.status_code = 200
        mock_sub_resp.json.return_value = {'result': {'id': 'sub_123'}}
        
        mock_requests_post.side_effect = [mock_plan_resp, mock_sub_resp]

        CartItem.objects.create(user=self.user, product=self.product, quantity=1)
        
        data = {
            'address': {
                'name': 'Test User',
                'phone': '1234567890',
                'address': '123 Test St',
                'type': 'home'
            },
            'is_subscription': True,
            'free_tshirt_size': 'S'
        }
        
        response = self.client.post(self.url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(response.data['checkout_url'], f"{settings.FRONTEND_URL.rstrip('/')}/{settings.NOWPAYMENTS_SUCCESS_URL.lstrip('/')}")


    def test_nowpayments_ipn_success(self):
        # Create Order
        order = Order.objects.create(
            user=self.user,
            total_price=100.00,
            shipping_fee=50.00,
            status='Pending',
            is_paid=False,
            nowpayments_payment_id='test_payment_123'
        )

        data = {
            'payment_status': 'finished',
            'order_id': order.id,
            'price_amount': 150.0,
            'price_currency': 'AUD'
        }

        import hmac
        import hashlib
        import json
        
        sorted_data = dict(sorted(data.items()))
        data_string = json.dumps(sorted_data, separators=(',', ':'))
        sig = hmac.new(settings.NOWPAYMENTS_IPN_SECRET.encode(), data_string.encode(), hashlib.sha512).hexdigest()

        url = reverse('nowpayments-ipn')
        
        response = self.client.post(url, data, format='json', HTTP_X_NOWPAYMENTS_SIG=sig)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        order.refresh_from_db()
        self.assertTrue(order.is_paid)
        self.assertEqual(order.status, 'Processing')



    @patch('shop.views.requests.post')
    def test_checkout_incomplete_address(self, mock_post):
        # Should not call PayPal if address validation fails
        CartItem.objects.create(user=self.user, product=self.product, quantity=1)
        
        # Missing 'name'
        data = {
            'address': {
                'phone': '1234567890',
                'address': '123 Test St',
                'type': 'home'
            }
        }
        
        response = self.client.post(self.url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('address', response.data)
        self.assertIn('name', response.data['address'])
        self.assertEqual(Order.objects.count(), 0)
        mock_post.assert_not_called()

    def test_checkout_address_is_string(self):
        CartItem.objects.create(user=self.user, product=self.product, quantity=1)
        
        data = {
            'address': "123 Test St"
        }
        
        try:
            response = self.client.post(self.url, data, format='json')
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        except AttributeError:
            self.fail("AttributeError raised when address is a string")

    # ✅ Free T-shirt Tests
    @patch('shop.views.requests.post')
    def test_checkout_with_free_tshirt_eligible(self, mock_nowpayments_post):
        """Test that orders with subtotal <= 1500 get free T-shirt when size is provided"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'invoice_url': 'https://nowpayments.io/payment?id=free_tshirt',
            'id': 'free_tshirt'
        }
        mock_nowpayments_post.return_value = mock_response

        # Create cart with total >= 1500 (product price = 90, quantity = 20 = 1800)
        CartItem.objects.create(user=self.user, product=self.product, quantity=20)

        data = {
            'address': {
                'name': 'Test User',
                'phone': '1234567890',
                'address': '123 Test St',
                'type': 'home'
            },
            'free_tshirt_size': 'L'
        }

        response = self.client.post(self.url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        order = Order.objects.first()
        
        # Verify regular item + free T-shirt item
        self.assertEqual(order.items.count(), 2)
        
        # Check regular item
        regular_item = order.items.filter(is_free_item=False).first()
        self.assertIsNotNone(regular_item)
        self.assertEqual(regular_item.product, self.product)
        self.assertEqual(regular_item.quantity, 20)
        
        # Check free T-shirt item
        free_item = order.items.filter(is_free_item=True).first()
        self.assertIsNotNone(free_item)
        self.assertTrue(free_item.is_free_item)
        self.assertEqual(free_item.price, 0.00)
        self.assertEqual(free_item.quantity, 1)
        self.assertEqual(free_item.free_item_size, 'L')
        self.assertIsNone(free_item.product)

    @patch('shop.views.requests.post')
    def test_checkout_free_tshirt_missing_size(self, mock_requests_post):
        """Test that eligible orders without size selection get error"""
        CartItem.objects.create(user=self.user, product=self.product, quantity=20)

        data = {
            'address': {
                'name': 'Test User',
                'phone': '1234567890',
                'address': '123 Test St',
                'type': 'home'
            }
            # Missing 'free_tshirt_size'
        }

        response = self.client.post(self.url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('eligible for a free T-shirt', str(response.data))
        self.assertIn('select your T-shirt size', str(response.data))
        self.assertEqual(Order.objects.count(), 0)

    @patch('shop.views.requests.post')
    def test_checkout_free_tshirt_invalid_size(self, mock_requests_post):
        """Test that invalid T-shirt size returns error"""
        CartItem.objects.create(user=self.user, product=self.product, quantity=20)

        data = {
            'address': {
                'name': 'Test User',
                'phone': '1234567890',
                'address': '123 Test St',
                'type': 'home'
            },
            'free_tshirt_size': 'XXXL'  # Invalid size
        }

        response = self.client.post(self.url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('free_tshirt_size', response.data)
        self.assertEqual(Order.objects.count(), 0)

    @patch('shop.views.requests.post')
    def test_checkout_no_free_tshirt_for_cheap_order(self, mock_requests_post):
        """Test that orders with subtotal < 1500 don't get free T-shirt"""
        # Mock NOWPayments response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'invoice_url': 'http://test.com', 'id': '123'}
        mock_requests_post.return_value = mock_response

        # Create expensive product (but still under 1500 limit if quantity=1)
        expensive_product = Product.objects.create(
            name='Expensive Product',
            initial_price=1000.00,
            discounted_price=800.00,
            description='Expensive Description',
            size='L',
            category='Health',
            type=self.type
        )
        CartItem.objects.create(user=self.user, product=expensive_product, quantity=1)

        data = {
            'address': {
                'name': 'Test User',
                'phone': '1234567890',
                'address': '123 Test St',
                'type': 'home'
            }
            # No free_tshirt_size needed
        }

        response = self.client.post(self.url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        order = Order.objects.first()
        
        # Verify only 1 item (no free T-shirt)
        self.assertEqual(order.items.count(), 1)
        self.assertFalse(order.items.filter(is_free_item=True).exists())

    @patch('shop.views.requests.post')
    def test_checkout_multiple_products_with_free_tshirt(self, mock_requests_post):
        """Test checkout with multiple products in cart total <= 1500"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'invoice_url': 'http://test.com', 'id': '123'}
        mock_requests_post.return_value = mock_response

        # Create additional products
        product2 = Product.objects.create(
            name='Product 2',
            initial_price=50.00,
            discounted_price=40.00,
            description='Product 2',
            size='S',
            category='Merchandise',
            type=self.type
        )
        product3 = Product.objects.create(
            name='Product 3',
            initial_price=60.00,
            discounted_price=50.00,
            description='Product 3',
            size='M',
            category='Health',
            type=self.type
        )

        # Add to cart: 90*5 + 40*3 + 50*2 = 450 + 120 + 100 = 670 -> Not eligible
        # Need to increase quantity to be eligible
        CartItem.objects.create(user=self.user, product=self.product, quantity=15) # 90*15 = 1350
        CartItem.objects.create(user=self.user, product=product2, quantity=3) # 40*3 = 120
        CartItem.objects.create(user=self.user, product=product3, quantity=2) # 50*2 = 100
        # Total = 1350 + 120 + 100 = 1570

        data = {
            'address': {
                'name': 'Test User',
                'phone': '1234567890',
                'address': '123 Test St',
                'type': 'home'
            },
            'free_tshirt_size': 'XL'
        }

        response = self.client.post(self.url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        order = Order.objects.first()
        
        # Verify 3 regular items + 1 free T-shirt = 4 total
        self.assertEqual(order.items.count(), 4)
        self.assertEqual(order.items.filter(is_free_item=False).count(), 3)
        self.assertEqual(order.items.filter(is_free_item=True).count(), 1)
        
        # Verify free T-shirt

        # Verify success_url for guest
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_guest_checkout_invalid_payload(self):
        self.client.force_authenticate(user=None)
        
        # Missing email
        data = {
            'cart_items': [
                {'product_id': self.product.id, 'quantity': 1}
            ],
            'address': {
                'name': 'Guest User',
                'phone': '0412345678',
                'address': '123 Guest St',
                'type': 'home'
            }
        }
        
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data)

    @patch('shop.views.requests.post')
    def test_guest_checkout_subscription(self, mock_requests_post):
        # Mock Plan creation
        mock_plan_resp = MagicMock()
        mock_plan_resp.status_code = 200
        mock_plan_resp.json.return_value = {'result': {'id': 'plan_guest_123'}}
        
        # Mock Subscription creation
        mock_sub_resp = MagicMock()
        mock_sub_resp.status_code = 200
        mock_sub_resp.json.return_value = {'result': {'id': 'sub_guest_123'}}
        
        mock_requests_post.side_effect = [mock_plan_resp, mock_sub_resp]

        self.product.stripe_subscription_price_id = 'price_sub_123'
        self.product.save()

        self.client.force_authenticate(user=None)

        data = {
            'cart_items': [
                {'product_id': self.product.id, 'quantity': 1}
            ],
            'address': {
                'name': 'Guest User',
                'phone': '0412345678',
                'address': '123 Guest St',
                'type': 'home'
            },
            'email': 'guest@example.com',
            'is_subscription': True
        }

        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        order = Order.objects.first()
        self.assertEqual(order.email, 'guest@example.com')

