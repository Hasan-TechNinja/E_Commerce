from django.contrib import admin
from .models import Type, Product, ProductImage, Review, Order, OrderItem, OrderAddress, ContactMessage

# Register your models here.

class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1

class ReviewInline(admin.TabularInline):
    model = Review
    extra = 1


@admin.register(Type)
class TypeAdmin(admin.ModelAdmin):
    list_display = ('id', 'name',)
    search_fields = ('name',)

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'category', 'type', 'initial_price', 'discounted_price', 'size', 'order_count', 'created_at')
    list_filter = ('category', 'type', 'size', 'created_at')
    search_fields = ('name', 'description')
    readonly_fields = ('order_count',)
    inlines = [ProductImageInline, ReviewInline]

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('product', 'user_name', 'rating', 'created_at')
    list_filter = ('rating', 'created_at')
    search_fields = ('product__name', 'user_name__username', 'comment')

@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ('product', 'image')
    search_fields = ('product__name',)


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('product', 'price', 'quantity')

class OrderAddressInline(admin.StackedInline):
    model = OrderAddress
    extra = 0

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'total_price', 'status', 'is_paid', 'paypal_order_id', 'created_at')
    list_filter = ('status', 'is_paid', 'created_at')
    search_fields = ('user__username', 'paypal_order_id')
    inlines = [OrderItemInline, OrderAddressInline]
    readonly_fields = ('paypal_order_id',)

@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'whatsapp', 'email', 'project_details', 'sent_at')
    search_fields = ('name', 'email', 'whatsapp', 'project_details')
    list_filter = ('sent_at',)




admin.site.site_header = "E-Commerce Admin"
admin.site.site_title = "E-Commerce Admin Portal"
admin.site.index_title = "Welcome to E-Commerce Admin Portal" 
admin.site.enable_nav_sidebar = True