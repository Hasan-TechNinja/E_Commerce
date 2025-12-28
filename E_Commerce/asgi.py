# import os
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
import os
# 1️⃣ Set the Django settings module first
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'E_Commerce.settings')

# 2️⃣ Initialize Django before importing anything that uses models
django_application = get_asgi_application()

# 3️⃣ Import middleware and routing AFTER Django is setup
from chat.middleware import JWTAuthMiddleware
import chat.routing

# 4️⃣ Build the ASGI application
application = ProtocolTypeRouter(
    {
        "http": django_application,
        "websocket": JWTAuthMiddleware(
            URLRouter(
                chat.routing.websocket_urlpatterns
            )
        ),
    }
)
