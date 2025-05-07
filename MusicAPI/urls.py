# music_api/urls.py
from django.urls import path
# Import các view bạn cần từ file views.py cùng cấp
from . import views
# Import các view cần thiết từ Simple JWT
from rest_framework_simplejwt.views import (
    TokenRefreshView,
    TokenVerifyView,
)
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # --- Authentication & User Management URLs ---
    # URL đăng nhập Admin (trước đây ở urls.py gốc)
    path('token/', views.AdminLoginView.as_view(), name='admin_token_obtain_pair'),
    # URL làm mới token (cho cả admin và user nếu dùng chung cơ chế JWT)
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    # URL kiểm tra token (tùy chọn)
    path('token/verify/', TokenVerifyView.as_view(), name='token_verify'),

    # # URL Đăng ký User thường
    path('users/register/', views.UserRegistrationView.as_view(), name='user_register'),
    # # URL Đăng nhập User thường
    path('users/login/', views.UserLoginView.as_view(), name='user_login'),

    # URL quản lý User (ví dụ: xem danh sách, chi tiết - cần bảo vệ bằng permission)
    path('users/', views.UserList.as_view(), name='user-list'),
    path('users/<str:pk>/', views.UserDetail.as_view(), name='user-detail'),

    # --- Admin Specific URLs ---
    path('admin/stats/', views.AdminStatsView.as_view(), name='admin-stats'),
    path('admin/', views.AdminList.as_view(), name='admin-list'), # Có thể trùng với trang admin Django? Xem xét đổi tên
    path('admin/<str:pk>/', views.AdminDetail.as_view(), name='admin-detail'),

    # --- Other API Resource URLs ---
    path('artists/options/', views.ArtistSelectView.as_view(), name='artist-options'),
    path('albums/options/', views.AlbumSelectView.as_view(), name='album-options'),
    path('musicgenres/options/', views.MusicGenreSelectView.as_view(), name='musicgenre-options'),
    path('musicgenres/', views.MusicGenreList.as_view(), name='musicgenre-list'),
    path('musicgenres/<str:pk>/', views.MusicGenreDetail.as_view(), name='musicgenre-detail'),
    path('artists/', views.ArtistList.as_view(), name='artist-list'),
    path('artists/<str:pk>/', views.ArtistDetail.as_view(), name='artist-detail'),
    path('albums/', views.AlbumList.as_view(), name='album-list'),
    path('albums/<str:pk>/', views.AlbumDetail.as_view(), name='album-detail'),
    path('songs/', views.SongList.as_view(), name='song-list'),
    path('songs/<str:pk>/', views.SongDetail.as_view(), name='song-detail'),
    path('playlists/', views.PlaylistList.as_view(), name='playlist-list'),
    path('playlists/<str:pk>/', views.PlaylistDetail.as_view(), name='playlist-detail'),
    path('search/', views.SearchView.as_view(), name='search'),
    path('albums/<str:pk>/songs/', views.AlbumSongsView.as_view(), name='album-songs'),
    path('artists/<str:pk>/albums/', views.ArtistAlbumsView.as_view(), name='artist-albums'),
    path('artists/<str:pk>/top-tracks/', views.ArtistTopTracksView.as_view(), name='artist-top-tracks'),
    path('musicgenres/<str:pk>/tracks/', views.GenreTracksView.as_view(), name='genre-tracks'),
    path('home/featured/', views.FeaturedContentView.as_view(), name='home-featured'),
    path('home/most-played/', views.MostPlayedView.as_view(), name='home-most-played'),
    path('home/library-highlights/', views.LibraryHighlightsView.as_view(), name='home-library-highlights'),
    path('home/new-releases/', views.RecentlyAddedReleasesView.as_view(), name='home-new-releases'),
]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)