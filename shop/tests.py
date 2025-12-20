from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth.models import User
from .models import Product, CartItem, Order, Type
from unittest.mock import patch
import requests
import unittest
from unittest.mock import patch, MagicMock


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
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error'], 'Cart is empty')

    def test_checkout_missing_address(self):
        CartItem.objects.create(user=self.user, product=self.product, quantity=1)
        response = self.client.post(self.url, {}, format='json')
        # Based on current implementation, it might create order then fail, or fail early.
        # The current implementation creates order first, then checks address.
        # We expect 400.
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Address data is required', str(response.data))
        # Verify order was deleted/not created
        self.assertEqual(Order.objects.count(), 0)

    @patch('shop.views.stripe.checkout.Session.create')
    def test_checkout_success(self, mock_stripe_create):
        # Mock Stripe Session
        mock_session = MagicMock()
        mock_session.id = 'cs_test_123'
        mock_session.url = 'https://checkout.stripe.com/pay/cs_test_123'
        mock_stripe_create.return_value = mock_session

        CartItem.objects.create(user=self.user, product=self.product, quantity=2)
        
        data = {
            'address': {
                'name': 'Test User',
                'phone': '1234567890',
                'address': '123 Test St',
                'type': 'home'
            }
        }
        
        response = self.client.post(self.url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Order.objects.count(), 1)
        order = Order.objects.first()
        self.assertEqual(order.total_price, 180.00) # 90 * 2
        self.assertEqual(order.shipping_fee, 50.00)
        self.assertEqual(order.stripe_checkout_session_id, 'cs_test_123')
        self.assertEqual(CartItem.objects.count(), 0)
        self.assertEqual(response.data['checkout_url'], 'https://checkout.stripe.com/pay/cs_test_123')

    @patch('shop.views.stripe.checkout.Session.create')
    def test_checkout_subscription_success(self, mock_stripe_create):
        # Mock Stripe Session
        mock_session = MagicMock()
        mock_session.id = 'cs_test_sub_123'
        mock_session.url = 'https://checkout.stripe.com/pay/cs_test_sub_123'
        mock_stripe_create.return_value = mock_session

        # Set stripe_price_id for product
        self.product.stripe_price_id = 'price_123'
        self.product.save()

        CartItem.objects.create(user=self.user, product=self.product, quantity=1)
        
        data = {
            'address': {
                'name': 'Test User',
                'phone': '1234567890',
                'address': '123 Test St',
                'type': 'home'
            },
            'is_subscription': True
        }
        
        response = self.client.post(self.url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        mock_stripe_create.assert_called_with(
            payment_method_types=['card'],
            line_items=[{'price': 'price_123', 'quantity': 1}],
            mode='subscription',
            success_url=unittest.mock.ANY,
            cancel_url=unittest.mock.ANY,
            client_reference_id=unittest.mock.ANY,
            customer_email=self.user.email,
            metadata={'order_id': unittest.mock.ANY}
        )

    @patch('shop.views.stripe.Webhook.construct_event')
    def test_stripe_webhook_success(self, mock_construct_event):
        # Create Order
        order = Order.objects.create(
            user=self.user,
            total_price=100.00,
            shipping_fee=50.00,
            status='Pending',
            is_paid=False,
            stripe_checkout_session_id='cs_test_123'
        )

        mock_event = {
            'type': 'checkout.session.completed',
            'data': {
                'object': {
                    'client_reference_id': str(order.id)
                }
            }
        }
        mock_construct_event.return_value = mock_event

        url = reverse('stripe-webhook')
        data = {'some': 'payload'} # Payload doesn't matter as we mock construct_event
        
        # Set HTTP_STRIPE_SIGNATURE header
        response = self.client.post(url, data, format='json', HTTP_STRIPE_SIGNATURE='test_sig')
        
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
        self.assertIn('Missing address fields', str(response.data))
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







