from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth.models import User
from shop.models import Product, Order, Type
from unittest.mock import patch, MagicMock
import decimal

class GuestCheckoutUserCreationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.type = Type.objects.create(name='Test Type')
        self.product = Product.objects.create(
            name='Test Product',
            initial_price=100.00,
            discounted_price=90.00,
            description='Test Description',
            category='Merchandise',
            type=self.type,
            stock_quantity=10
        )
        self.checkout_url = reverse('checkout')
        self.webhook_url = reverse('stripe-webhook')

    @patch('shop.views.stripe.checkout.Session.create')
    @patch('shop.views.stripe.Webhook.construct_event')
    @patch('shop.views.send_mail')
    def test_guest_checkout_creates_user_and_links_order(self, mock_send_mail, mock_construct_event, mock_stripe_checkout_create):
        # 1. Perform Guest Checkout
        mock_session = MagicMock()
        mock_session.id = 'cs_test_guest'
        mock_session.url = 'https://checkout.stripe.com/pay/cs_test_guest'
        mock_stripe_checkout_create.return_value = mock_session

        guest_email = 'guest_new@example.com'
        data = {
            'cart_items': [
                {'product_id': self.product.id, 'quantity': 1}
            ],
            'address': {
                'name': 'Guest User',
                'phone': '0412345678',
                'address': '123 Guest St, Extremely Long Address Line to Test Inconsistency with model field length if it was still 100 characters',
                'type': 'home'
            },
            'email': guest_email
        }

        response = self.client.post(self.checkout_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        order = Order.objects.get(email=guest_email)
        self.assertIsNone(order.user)

        # 2. Verify NO Checkout Email
        # Check that no emails were sent yet
        self.assertEqual(mock_send_mail.call_count, 0, "No emails should be sent during checkout initiation")

        # 3. Simulate Stripe Webhook
        mock_event = {
            'type': 'checkout.session.completed',
            'data': {
                'object': {
                    'client_reference_id': str(order.id),
                    'customer_email': guest_email
                }
            }
        }
        mock_construct_event.return_value = mock_event

        webhook_response = self.client.post(self.webhook_url, {}, format='json', HTTP_STRIPE_SIGNATURE='test_sig')
        self.assertEqual(webhook_response.status_code, status.HTTP_200_OK)

        # 4. Verify User Creation and Linking
        order.refresh_from_db()
        self.assertTrue(order.is_paid)
        self.assertIsNotNone(order.user)
        self.assertEqual(order.user.email, guest_email)
        self.assertEqual(User.objects.filter(email=guest_email).count(), 1)
        
        # 5. Verify Paid Order Email
        # After webhook, we expect emails (Customer + Admin)
        call_args_list = mock_send_mail.call_args_list
        # Check for customer email
        found_paid_customer_email = False
        for call in call_args_list:
            subject = call.args[0]
            recipients = call.args[3]
            if "Order Payment Successful" in subject and guest_email in recipients:
                found_paid_customer_email = True
                break
        self.assertTrue(found_paid_customer_email, "Post-payment 'Order Payment Successful' email should be sent to customer")
