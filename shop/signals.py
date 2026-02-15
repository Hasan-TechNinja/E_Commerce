from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db import transaction
from .models import OrderItem, Order, Product


@receiver(post_save, sender=OrderItem)
def handle_orderitem_saved(sender, instance, created, **kwargs):
    """
    When an OrderItem is saved:
    - If the parent Order is marked paid (`is_paid` True) and this OrderItem hasn't adjusted stock yet,
      decrement the Product.stock_quantity by the OrderItem.quantity and mark `stock_adjusted=True`.
    - If the Order is cancelled and this item had previously adjusted stock, restore it (handled in order handler).
    """
    order = instance.order
    product = instance.product
    if not product:
        return

    # Decrement stock when order is paid and item not yet adjusted
    try:
        if getattr(order, 'is_paid', False) and not instance.stock_adjusted:
            with transaction.atomic():
                product.stock_quantity = (product.stock_quantity or 0) - instance.quantity
                if product.stock_quantity < 0:
                    product.stock_quantity = 0
                product.save(update_fields=['stock_quantity'])
                instance.stock_adjusted = True
                instance.save(update_fields=['stock_adjusted'])
    except Exception:
        pass


@receiver(post_delete, sender=OrderItem)
def handle_orderitem_deleted(sender, instance, **kwargs):
    """
    If an OrderItem that had adjusted stock is deleted, restore the stock.
    """
    product = instance.product
    if not product:
        return
    try:
        if instance.stock_adjusted:
            with transaction.atomic():
                product.stock_quantity = (product.stock_quantity or 0) + instance.quantity
                product.save(update_fields=['stock_quantity'])
    except Exception:
        pass


@receiver(post_save, sender=Order)
def handle_order_saved(sender, instance, created, **kwargs):
    """
    Handle order-level transitions:
    - If an Order becomes paid (`is_paid` True), ensure all items decrement stock if not yet adjusted.
    - If an Order's status becomes 'Cancelled', restore stock for items that were adjusted and mark them unadjusted.
    """
    # Ensure items exist
    try:
        # When order is paid: decrement remaining items
        if getattr(instance, 'is_paid', False):
            for item in instance.items.filter(stock_adjusted=False):
                product = item.product
                if not product:
                    continue
                with transaction.atomic():
                    product.stock_quantity = (product.stock_quantity or 0) - item.quantity
                    if product.stock_quantity < 0:
                        product.stock_quantity = 0
                    product.save(update_fields=['stock_quantity'])
                    item.stock_adjusted = True
                    item.save(update_fields=['stock_adjusted'])

        # When order is cancelled: restore previously adjusted items
        if getattr(instance, 'status', '') == 'Cancelled':
            for item in instance.items.filter(stock_adjusted=True):
                product = item.product
                if not product:
                    continue
                with transaction.atomic():
                    product.stock_quantity = (product.stock_quantity or 0) + item.quantity
                    product.save(update_fields=['stock_quantity'])
                    item.stock_adjusted = False
                    item.save(update_fields=['stock_adjusted'])
    except Exception:
        pass
