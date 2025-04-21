# music_api/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('artists/options/', views.ArtistSelectView.as_view(), name='artist-options'),
    path('albums/options/', views.AlbumSelectView.as_view(), name='album-options'),
    path('musicgenres/', views.MusicGenreList.as_view(), name='musicgenre-list'),
    path('musicgenres/<str:pk>/', views.MusicGenreDetail.as_view(), name='musicgenre-detail'),
    path('users/', views.UserList.as_view(), name='user-list'),
    path('users/<str:pk>/', views.UserDetail.as_view(), name='user-detail'),
    path('admin/', views.AdminList.as_view(), name='admin-list'),
    path('admin/<str:pk>/', views.AdminDetail.as_view(), name = 'admin-detail'),
    path('artists/', views.ArtistList.as_view(), name='artist-list'),
    path('artists/<str:pk>/', views.ArtistDetail.as_view(), name='artist-detail'),
    path('albums/', views.AlbumList.as_view(), name = 'album-list'),
    path('albums/<str:pk>/', views.AlbumDetail.as_view(), name = 'album-detail'),
    path('songs/', views.SongList.as_view(), name = 'song-list'),
    path('songs/<str:pk>/', views.SongDetail.as_view(), name = 'song-detail'),
    path('playlists/', views.PlaylistList.as_view(), name='playlist-list'),
    path('playlists/<str:pk>/', views.PlaylistDetail.as_view(), name='playlist-detail'),
    path('search/', views.SearchView.as_view(), name='search'),
]