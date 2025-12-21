from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth.models import User
from shop.models import Order, Product, Type

class OrderStatusViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='testuser', password='testpassword')
        self.other_user = User.objects.create_user(username='otheruser', password='otherpassword')
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

        self.order = Order.objects.create(
            user=self.user,
            total_price=100.00,
            shipping_fee=50.00,
            status='Pending',
            is_paid=True
        )

    def test_cancel_order_success(self):
        url = reverse('cancel-order', args=[self.order.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'Cancelled')

    def test_cancel_order_processing_success(self):
        self.order.status = 'Processing'
        self.order.save()
        url = reverse('cancel-order', args=[self.order.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'Cancelled')

    def test_cancel_order_invalid_status(self):
        self.order.status = 'Shipped'
        self.order.save()
        url = reverse('cancel-order', args=[self.order.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'Shipped')

    def test_cancel_order_after_48_hours(self):
        from django.utils import timezone
        from datetime import timedelta
        
        # Mock creation time to be 49 hours ago
        self.order.created_at = timezone.now() - timedelta(hours=49)
        self.order.save()
        
        url = reverse('cancel-order', args=[self.order.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error'], "Cannot cancel order after 48 hours")
        
        self.order.refresh_from_db()
        self.assertNotEqual(self.order.status, 'Cancelled')

    def test_cancel_other_user_order(self):
        other_order = Order.objects.create(
            user=self.other_user,
            total_price=100.00,
            shipping_fee=50.00,
            status='Pending',
            is_paid=True
        )
        url = reverse('cancel-order', args=[other_order.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_confirm_delivery_success(self):
        self.order.status = 'Shipped'
        self.order.save()
        url = reverse('confirm-delivery', args=[self.order.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'Delivered')
