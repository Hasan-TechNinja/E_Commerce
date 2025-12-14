from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth.models import User
from .models import Product, CartItem, Order, Type
from unittest.mock import patch
import requests
import unittest

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

    @patch('shop.views.requests.post')
    def test_checkout_success(self, mock_post):
        # Mock Access Token Response
        mock_token_response = unittest.mock.Mock()
        mock_token_response.json.return_value = {'access_token': 'test_token'}
        mock_token_response.status_code = 200
        
        # Mock Create Order Response
        mock_order_response = unittest.mock.Mock()
        mock_order_response.json.return_value = {
            'id': 'paypal_order_123',
            'links': [{'href': 'http://approval.link', 'rel': 'approve'}]
        }
        mock_order_response.status_code = 201
        
        mock_post.side_effect = [mock_token_response, mock_order_response]

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
        if response.status_code != status.HTTP_201_CREATED:
            print(f"DEBUG: {response.data}")
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Order.objects.count(), 1)
        order = Order.objects.first()
        self.assertEqual(order.total_price, 180.00) # 90 * 2
        self.assertEqual(order.shipping_fee, 50.00)
        self.assertEqual(order.paypal_order_id, 'paypal_order_123')
        self.assertEqual(CartItem.objects.count(), 0)
        self.assertIn('approval_link', response.data)

    @patch('shop.views.requests.post')
    def test_checkout_paypal_error(self, mock_post):
        # Mock Access Token Response
        mock_token_response = unittest.mock.Mock()
        mock_token_response.json.return_value = {'access_token': 'test_token'}
        mock_token_response.status_code = 200
        
        # Mock Create Order Error
        mock_post.side_effect = [mock_token_response, requests.exceptions.RequestException("PayPal Error")]

        CartItem.objects.create(user=self.user, product=self.product, quantity=1)
        
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
        self.assertEqual(Order.objects.count(), 0)

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

    @patch('shop.views.requests.post')
    def test_paypal_capture_success(self, mock_post):
        # Create Order
        order = Order.objects.create(
            user=self.user,
            total_price=100.00,
            shipping_fee=50.00,
            status='Pending',
            is_paid=False,
            paypal_order_id='paypal_order_123'
        )
        
        # Mock Access Token Response
        mock_token_response = unittest.mock.Mock()
        mock_token_response.json.return_value = {'access_token': 'test_token'}
        mock_token_response.status_code = 200

        # Mock Capture Response
        mock_capture_response = unittest.mock.Mock()
        mock_capture_response.json.return_value = {'status': 'COMPLETED'}
        mock_capture_response.status_code = 200
        
        mock_post.side_effect = [mock_token_response, mock_capture_response]
        
        url = reverse('paypal-capture')
        data = {'paypal_order_id': 'paypal_order_123'}
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        order.refresh_from_db()
        self.assertTrue(order.is_paid)
        self.assertEqual(order.status, 'Processing')





