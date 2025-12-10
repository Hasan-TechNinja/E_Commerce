from django.urls import path
from . import views

urlpatterns = [
    path('health-products/', views.HealthProductListView.as_view(), name='product-list'),
    path('merchandise-products/', views.MerchandiseProductView.as_view(), name='merchandise-product-list'),
    path('products/<int:pk>/', views.ProductDetailView.as_view(), name='product-detail'),
]
