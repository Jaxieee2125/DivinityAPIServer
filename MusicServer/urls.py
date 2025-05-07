"""
URL configuration for MusicServer project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include # Đảm bảo có include
from MusicAPI.views import serve_media_with_range # Import view tùy chỉnh
from django.urls import re_path # Import re_path để sử dụng cho URL tùy chỉnh

# from MusicAPI.views import AdminLoginView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('MusicAPI.urls')), 
]

if settings.DEBUG:
    urlpatterns += [
        re_path(r'^media/(?P<path>.*)$', serve_media_with_range),
    ]