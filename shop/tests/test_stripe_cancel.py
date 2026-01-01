from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from shop.models import Order, Product
from django.core import signing
from django.conf import settings
import decimal

class StripeCancelTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='testuser', password='password')
        self.order = Order.objects.create(
            user=self.user,
            total_price=decimal.Decimal('100.00'),
            shipping_fee=decimal.Decimal('10.00'),
            status='Pending',
            is_paid=False
        )

    def test_stripe_cancel_deletes_order(self):
        # Generate token
        signer = signing.Signer()
        token = signer.sign(self.order.id)
        
        url = reverse('stripe-cancel', args=[token])
        response = self.client.get(url)
        
        # Check redirect
        expected_url = settings.FRONTEND_URL + settings.STRIPE_CANCEL_URL
        self.assertRedirects(response, expected_url, fetch_redirect_response=False)
        
        # Check order is deleted
        with self.assertRaises(Order.DoesNotExist):
            Order.objects.get(id=self.order.id)

    def test_stripe_cancel_invalid_token(self):
        url = reverse('stripe-cancel', args=['invalid:token'])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 400)
        
        # Order should still exist
        self.assertTrue(Order.objects.filter(id=self.order.id).exists())

    def test_stripe_cancel_paid_order(self):
        self.order.is_paid = True
        self.order.save()
        
        signer = signing.Signer()
        token = signer.sign(self.order.id)
        
        url = reverse('stripe-cancel', args=[token])
        response = self.client.get(url)
        
        # Check redirect
        expected_url = settings.FRONTEND_URL + settings.STRIPE_CANCEL_URL
        self.assertRedirects(response, expected_url, fetch_redirect_response=False)
        
        # Order should NOT be deleted
        self.assertTrue(Order.objects.filter(id=self.order.id).exists())
