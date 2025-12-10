from django.shortcuts import render
from . models import Product, Review
from . serializers import ProductSerializer, ReviewSerializer
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

# Create your views here.
 
class HealthProductListView(APIView):
    def get(self, request):
        product = Product.objects.filter(category ='Health')
        serializer = ProductSerializer(product, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class MerchandiseProductView(APIView):
    def get(self, request):
        product = Product.objects.filter(category ='Merchandise')
        serializer = ProductSerializer(product, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

class ProductDetailView(APIView):
    def get(self, request, pk):
        try: 
            product = Product.objects.get(pk=pk)
        except Product.DoesNotExist:
            return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)
        
        serializer = ProductSerializer(product)
        
        reviews = Review.objects.filter(product=product)
        review_serializer = ReviewSerializer(reviews, many=True)
        
        related_products = Product.objects.filter(category=product.category).exclude(id=product.id)[:4]
        related_serializer = ProductSerializer(related_products, many=True)
        
        data = serializer.data
        data['reviews'] = review_serializer.data
        data['related_products'] = related_serializer.data
        
        return Response(data, status=status.HTTP_200_OK)