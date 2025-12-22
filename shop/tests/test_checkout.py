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
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Address data is required', str(response.data))
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
            },
            'free_tshirt_size': 'M'  # Added since 180 <= 1500
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
            'is_subscription': True,
            'free_tshirt_size': 'S'  # Added since 90 <= 1500
        }
        
        response = self.client.post(self.url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


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

    # ✅ Free T-shirt Tests
    @patch('shop.views.stripe.checkout.Session.create')
    def test_checkout_with_free_tshirt_eligible(self, mock_stripe_create):
        """Test that orders with subtotal <= 1500 get free T-shirt when size is provided"""
        mock_session = MagicMock()
        mock_session.id = 'cs_test_free_tshirt'
        mock_session.url = 'https://checkout.stripe.com/pay/cs_test_free_tshirt'
        mock_stripe_create.return_value = mock_session

        # Create cart with total <= 1500 (product price = 90, quantity = 10 = 900)
        CartItem.objects.create(user=self.user, product=self.product, quantity=10)

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
        self.assertEqual(regular_item.quantity, 10)
        
        # Check free T-shirt item
        free_item = order.items.filter(is_free_item=True).first()
        self.assertIsNotNone(free_item)
        self.assertTrue(free_item.is_free_item)
        self.assertEqual(free_item.price, 0.00)
        self.assertEqual(free_item.quantity, 1)
        self.assertEqual(free_item.free_item_size, 'L')
        self.assertIsNone(free_item.product)

    @patch('shop.views.stripe.checkout.Session.create')
    def test_checkout_free_tshirt_missing_size(self, mock_stripe_create):
        """Test that eligible orders without size selection get error"""
        # Create cart with total <= 1500
        CartItem.objects.create(user=self.user, product=self.product, quantity=10)

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

    @patch('shop.views.stripe.checkout.Session.create')
    def test_checkout_free_tshirt_invalid_size(self, mock_stripe_create):
        """Test that invalid T-shirt size returns error"""
        CartItem.objects.create(user=self.user, product=self.product, quantity=10)

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
        self.assertIn('Invalid T-shirt size', str(response.data))
        self.assertEqual(Order.objects.count(), 0)

    @patch('shop.views.stripe.checkout.Session.create')
    def test_checkout_no_free_tshirt_for_expensive_order(self, mock_stripe_create):
        """Test that orders with subtotal > 1500 don't get free T-shirt"""
        mock_session = MagicMock()
        mock_session.id = 'cs_test_expensive'
        mock_session.url = 'https://checkout.stripe.com/pay/cs_test_expensive'
        mock_stripe_create.return_value = mock_session

        # Create expensive product
        expensive_product = Product.objects.create(
            name='Expensive Product',
            initial_price=2000.00,
            discounted_price=1600.00,
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

    @patch('shop.views.stripe.checkout.Session.create')
    def test_checkout_multiple_products_with_free_tshirt(self, mock_stripe_create):
        """Test checkout with multiple products in cart total <= 1500"""
        mock_session = MagicMock()
        mock_session.id = 'cs_test_multi'
        mock_session.url = 'https://checkout.stripe.com/pay/cs_test_multi'
        mock_stripe_create.return_value = mock_session

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

        # Add to cart: 90*5 + 40*3 + 50*2 = 450 + 120 + 100 = 670
        CartItem.objects.create(user=self.user, product=self.product, quantity=5)
        CartItem.objects.create(user=self.user, product=product2, quantity=3)
        CartItem.objects.create(user=self.user, product=product3, quantity=2)

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
        free_item = order.items.filter(is_free_item=True).first()
        self.assertEqual(free_item.free_item_size, 'XL')
