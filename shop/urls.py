from django.urls import path
from . import views

urlpatterns = [
    path('health-products/', views.HealthProductListView.as_view(), name='product-list'),
    path('merchandise-products/', views.MerchandiseProductView.as_view(), name='merchandise-product-list'),
    path('products/<int:pk>/', views.ProductDetailView.as_view(), name='product-detail'),
    path('products/<int:pk>/add-to-cart/', views.AddToCartView.as_view(), name='add-to-cart'),
    path('cart/', views.CartView.as_view(), name='cart-view'),
    path('cart/remove/<int:pk>/', views.RemoveCartItemView.as_view(), name='remove-from-cart'),
    path('cart/items/increase/<int:pk>/', views.IncreaseCartItemQuantityView.as_view(), name='increase-cart-item'),
    path('cart/items/decrease/<int:pk>/', views.DecreaseCartItemQuantityView.as_view(), name='decrease-cart-item'),
    path('checkout/', views.CheckoutView.as_view(), name='checkout'),
    path('paypal/capture/', views.PayPalCaptureView.as_view(), name='paypal-capture'),
    path('orders/', views.OrderListView.as_view(), name='order-list'),
    path('orders/<int:pk>/', views.OrderDetailView.as_view(), name='order-detail'),
]
