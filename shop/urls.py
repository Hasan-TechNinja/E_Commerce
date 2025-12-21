from django.urls import path
from . import views

urlpatterns = [
    path('home/', views.HomePageView.as_view(), name='home'),
    path('health-products/', views.HealthProductListView.as_view(), name='product-list'),
    path('merchandise-products/', views.MerchandiseProductView.as_view(), name='merchandise-product-list'),
    path('products/<int:pk>/', views.ProductDetailView.as_view(), name='product-detail'),
    path('products/<int:pk>/add-to-cart/', views.AddToCartView.as_view(), name='add-to-cart'),
    path('cart/', views.CartView.as_view(), name='cart-view'),
    path('cart/remove/<int:pk>/', views.RemoveCartItemView.as_view(), name='remove-from-cart'),
    path('cart/items/increase/<int:pk>/', views.IncreaseCartItemQuantityView.as_view(), name='increase-cart-item'),
    path('cart/items/decrease/<int:pk>/', views.DecreaseCartItemQuantityView.as_view(), name='decrease-cart-item'),
    path('checkout/', views.CheckoutView.as_view(), name='checkout'),
    path('stripe/webhook/', views.StripeWebhookView.as_view(), name='stripe-webhook'),

    path('orders/', views.OrderListView.as_view(), name='order-list'),
    path('orders/<int:pk>/', views.OrderDetailView.as_view(), name='order-detail'),
    path('post/review/<int:pk>/', views.CreateReviewView.as_view(), name='post-review'),
    path('contact-message/', views.ContactMessageView.as_view(), name='contact-message'),
    path('filter/product/', views.TypeFilterView.as_view(), name='filter-products'),
    path('products/<int:pk>/reviews/stats/', views.ProductReviewStatsView.as_view(), name='product-review-stats'),
    path('orders/<int:pk>/cancel/', views.CancelOrderView.as_view(), name='cancel-order'),
    path('orders/<int:pk>/confirm-delivery/', views.ConfirmDeliveryView.as_view(), name='confirm-delivery'),
]
