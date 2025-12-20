from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from shop.models import Product, Review, Type
from rest_framework import status
from rest_framework.test import APIClient

class ProductReviewStatsTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='testuser', password='testpassword')
        self.type = Type.objects.create(name='Test Type')
        self.product = Product.objects.create(
            category='Health',
            type=self.type,
            name='Test Product',
            initial_price=100.00,
            discounted_price=80.00,
            description='Test Description',
            size='M',
            order_count=0
        )
        self.url = reverse('product-review-stats', args=[self.product.id])

    def test_get_review_stats_no_reviews(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total_reviews'], 0)
        self.assertEqual(response.data['average_rating'], 0)
        self.assertEqual(response.data['recommended_percentage'], 0)
        self.assertEqual(response.data['star_counts']['5_star'], 0)

    def test_get_review_stats_with_reviews(self):
        # Create reviews
        Review.objects.create(product=self.product, user_name=self.user, rating=5, comment="Great")
        Review.objects.create(product=self.product, user_name=self.user, rating=5, comment="Excellent")
        Review.objects.create(product=self.product, user_name=self.user, rating=4, comment="Good")
        Review.objects.create(product=self.product, user_name=self.user, rating=3, comment="Average")
        Review.objects.create(product=self.product, user_name=self.user, rating=1, comment="Bad")

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Total reviews: 5
        self.assertEqual(response.data['total_reviews'], 5)
        
        # Average rating: (5+5+4+3+1) / 5 = 18 / 5 = 3.6
        self.assertEqual(response.data['average_rating'], 3.6)
        
        # Recommended count (rating >= 4): 3 (5, 5, 4)
        # Percentage: (3 / 5) * 100 = 60.0
        self.assertEqual(response.data['recommended_percentage'], 60.0)
        
        # Star counts
        self.assertEqual(response.data['star_counts']['5_star'], 2)
        self.assertEqual(response.data['star_counts']['4_star'], 1)
        self.assertEqual(response.data['star_counts']['3_star'], 1)
        self.assertEqual(response.data['star_counts']['2_star'], 0)
        self.assertEqual(response.data['star_counts']['1_star'], 1)

    def test_get_review_stats_product_not_found(self):
        url = reverse('product-review-stats', args=[999])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
