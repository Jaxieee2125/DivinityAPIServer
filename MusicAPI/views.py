from django.shortcuts import render

# music_api/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import (MusicGenreSerializer, UserSerializer, AdminSerializer,
                          ArtistSerializer, AlbumSerializer, SongSerializer, PlaylistSerializer)
from pymongo import MongoClient
from bson import ObjectId

# MongoDB Connection
client = MongoClient('mongodb://localhost:27017/')  # Your MongoDB connection string
db = client.MusicDatabase  # Your MongoDB database name

# --- Helper Function ---
def get_object(collection, pk):
    """Retrieves a single document by its _id."""
    try:
        return collection.find_one({'_id': ObjectId(pk)})
    except:
        return None

# --- MusicGenre Views ---

class MusicGenreList(APIView):
    """List all music genres, or create a new music genre."""
    def get(self, request):
        genres = list(db.musicgenres.find())
        serializer = MusicGenreSerializer(genres, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = MusicGenreSerializer(data=request.data)
        if serializer.is_valid():
            result = db.musicgenres.insert_one(serializer.validated_data)
            genre = db.musicgenres.find_one({'_id' : result.inserted_id}) # Find and return
            return Response(MusicGenreSerializer(genre).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class MusicGenreDetail(APIView):
    """Retrieve, update or delete a music genre instance."""
    def get(self, request, pk):
        genre = get_object(db.musicgenres, pk)
        if genre:
            serializer = MusicGenreSerializer(genre)
            return Response(serializer.data)
        return Response(status=status.HTTP_404_NOT_FOUND)

    def put(self, request, pk):
        genre = get_object(db.musicgenres, pk)
        if genre:
            serializer = MusicGenreSerializer(genre, data=request.data)
            if serializer.is_valid():
                db.musicgenres.update_one({'_id': ObjectId(pk)}, {'$set': serializer.validated_data})
                updated_genre = db.musicgenres.find_one({'_id': ObjectId(pk)}) #Find and return updated object
                return Response(MusicGenreSerializer(updated_genre).data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, pk):
        genre = get_object(db.musicgenres, pk)
        if genre:
            db.musicgenres.delete_one({'_id': ObjectId(pk)})
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(status=status.HTTP_404_NOT_FOUND)

# --- User Views ---
# ... (Similar structure for UserList, UserDetail) ...
class UserList(APIView):
    def get(self, request):
        users = list(db.users.find())
        serializer = UserSerializer(users, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = UserSerializer(data=request.data)
        if serializer.is_valid():
            result = db.users.insert_one(serializer.validated_data)
            created_user = db.users.find_one({'_id': result.inserted_id})
            return Response(UserSerializer(created_user).data, status = status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
class UserDetail(APIView):
    def get(self, request, pk):
        user = get_object(db.users, pk)
        if user:
            serializer = UserSerializer(user)
            return Response(serializer.data)
        return Response(status=status.HTTP_404_NOT_FOUND)
    def put(self, request, pk):
        user = get_object(db.users, pk)
        if user:
            serializer = UserSerializer(user, data=request.data)
            if serializer.is_valid():
                db.users.update_one({'_id': ObjectId(pk)}, {'$set': serializer.validated_data})
                updated_user = get_object(db.users, pk)
                return Response(UserSerializer(updated_user).data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        return Response(status = status.HTTP_404_NOT_FOUND)
    def delete(self, request, pk):
        user = get_object(db.users, pk)
        if user:
            db.users.delete_one({'_id': ObjectId(pk)})
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(status=status.HTTP_404_NOT_FOUND)


# --- Admin, Artist, Album, Song, Playlist Views ---
# ... (Create similar views for the other entities) ...
#Follow same pattern as above

class AdminList(APIView):
    def get(self, request):
        admins = list(db.admin.find())
        serializer = AdminSerializer(admins, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = AdminSerializer(data=request.data)
        if serializer.is_valid():
            result = db.admin.insert_one(serializer.validated_data)
            created_admin = db.admin.find_one({'_id': result.inserted_id})
            return Response(AdminSerializer(created_admin).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
class AdminDetail(APIView):
    def get(self, request, pk):
        admin = get_object(db.admin, pk)
        if admin:
            serializer = AdminSerializer(admin)
            return Response(serializer.data)
        return Response(status=status.HTTP_404_NOT_FOUND)
    
    def put(self, request, pk):
        admin = get_object(db.admin, pk)
        if admin:
            serializer = AdminSerializer(admin, data=request.data)
            if serializer.is_valid():
                db.admin.update_one({'_id': ObjectId(pk)}, {'$set': serializer.validated_data})
                updated_admin = get_object(db.admin, pk)
                return Response(AdminSerializer(updated_admin).data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_404_NOT_FOUND)
    
    def delete(self, request, pk):
        admin = get_object(db.admin, pk)
        if admin:
            db.admin.delete_one({'_id': ObjectId(pk)})
            return Response(status = status.HTTP_204_NO_CONTENT)
        return Response(status=status.HTTP_404_NOT_FOUND)
    
class ArtistList(APIView):
    def get(self, request):
        artists = list(db.artists.find())
        serializer = ArtistSerializer(artists, many = True)
        return Response(serializer.data)
    
    def post(self, request):
        serializer = ArtistSerializer(data=request.data)
        if serializer.is_valid():
            result = db.artists.insert_one(serializer.validated_data)
            created_artist = get_object(db.artists, result.inserted_id)
            return Response(ArtistSerializer(created_artist).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
class ArtistDetail(APIView):
    def get(self, request, pk):
        artist = get_object(db.artists, pk)
        if artist:
            serializer = ArtistSerializer(artist)
            return Response(serializer.data)
        return Response(status=status.HTTP_404_NOT_FOUND)
    def put(self, request, pk):
        artist = get_object(db.artists, pk)
        if artist:
            serializer = ArtistSerializer(artist, data = request.data)
            if serializer.is_valid():
                db.artists.update_one({'_id': ObjectId(pk)}, {'$set': serializer.validated_data})
                updated_artist = get_object(db.artists, pk)
                return Response(ArtistSerializer(updated_artist).data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        return Response(status = status.HTTP_404_NOT_FOUND)
    def delete(self, request, pk):
        artist = get_object(db.artists, pk)
        if artist:
            db.artists.delete_one({'_id': ObjectId(pk)})
            return Response(status = status.HTTP_204_NO_CONTENT)
        return Response(status = status.HTTP_404_NOT_FOUND)
    
class AlbumList(APIView):
    def get(self, request):
        albums = list(db.albums.find())
        serializer = AlbumSerializer(albums, many = True)
        return Response(serializer.data)
    def post(self, request):
        serializer = AlbumSerializer(data = request.data)
        if serializer.is_valid():
            result = db.albums.insert_one(serializer.validated_data)
            created_album = get_object(db.albums, result.inserted_id)
            return Response(AlbumSerializer(created_album).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status = status.HTTP_400_BAD_REQUEST)
class AlbumDetail(APIView):
    def get(self, request, pk):
        album = get_object(db.albums, pk)
        if album:
            serializer = AlbumSerializer(album)
            return Response(serializer.data)
        return Response(status=status.HTTP_404_NOT_FOUND)
    def put(self, request, pk):
        album = get_object(db.albums, pk)
        if album:
            serializer = AlbumSerializer(album, data=request.data)
            if serializer.is_valid():
                db.albums.update_one({'_id': ObjectId(pk)}, {'$set': serializer.validated_data})
                updated_album = get_object(db.albums, pk)
                return Response(AlbumSerializer(updated_album).data)
            return Response(serializer.errors, status = status.HTTP_400_BAD_REQUEST)
        return Response(status = status.HTTP_404_NOT_FOUND)
    def delete(self, request, pk):
        album = get_object(db.albums, pk)
        if album:
            db.albums.delete_one({'_id': ObjectId(pk)})
            return Response(status = status.HTTP_204_NO_CONTENT)
        return Response(status = status.HTTP_404_NOT_FOUND)
    
class SongList(APIView):
    def get(self, request):
        songs = list(db.songs.find())
        serializer = SongSerializer(songs, many=True)
        return Response(serializer.data)
    def post(self, request):
        serializer = SongSerializer(data = request.data)
        if serializer.is_valid():
            result = db.songs.insert_one(serializer.validated_data)
            created_song = get_object(db.songs, result.inserted_id)
            return Response(SongSerializer(created_song).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
class SongDetail(APIView):
    def get(self, request, pk):
        song = get_object(db.songs, pk)
        if song:
            serializer = SongSerializer(song)
            return Response(serializer.data)
        return Response(status = status.HTTP_404_NOT_FOUND)
    def put(self, request, pk):
        song = get_object(db.songs, pk)
        if song:
            serializer = SongSerializer(song, data=request.data)
            if serializer.is_valid():
                db.songs.update_one({'_id': ObjectId(pk)}, {'$set': serializer.validated_data})
                updated_song = get_object(db.songs, pk)
                return Response(SongSerializer(updated_song).data)
            return Response(serializer.errors, status = status.HTTP_400_BAD_REQUEST)
        return Response(status = status.HTTP_404_NOT_FOUND)
    def delete(self, request, pk):
        song = get_object(db.songs, pk)
        if song:
            db.songs.delete_one({'_id':ObjectId(pk)})
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(status=status.HTTP_404_NOT_FOUND)
    
class PlaylistList(APIView):
    def get(self, request):
        playlists = list(db.playlists.find())
        serializer = PlaylistSerializer(playlists, many = True)
        return Response(serializer.data)
    def post(self, request):
        serializer = PlaylistSerializer(data = request.data)
        if serializer.is_valid():
            result = db.playlists.insert_one(serializer.validated_data)
            created_playlist = get_object(db.playlists, result.inserted_id)
            return Response(PlaylistSerializer(created_playlist).data, status = status.HTTP_201_CREATED)
        return Response(serializer.errors, status = status.HTTP_400_BAD_REQUEST)
    
class PlaylistDetail(APIView):
    def get(self, request, pk):
        playlist = get_object(db.playlists, pk)
        if playlist:
            serializer = PlaylistSerializer(playlist)
            return Response(serializer.data)
        return Response(status=status.HTTP_404_NOT_FOUND)
    def put(self, request, pk):
        playlist = get_object(db.playlists, pk)
        if playlist:
            serializer = PlaylistSerializer(playlist, data = request.data, partial = True) #partial = True allows for updating only certain fields
            if serializer.is_valid():
                db.playlists.update_one({'_id': ObjectId(pk)}, {'$set': serializer.validated_data})
                updated_playlist = get_object(db.playlists, pk)
                return Response(PlaylistSerializer(updated_playlist).data)
            return Response(serializer.errors, status = status.HTTP_400_BAD_REQUEST)
        return Response(status= status.HTTP_404_NOT_FOUND)
    def delete(self, request, pk):
        playlist = get_object(db.playlists, pk)
        if playlist:
            db.playlists.delete_one({'_id': ObjectId(pk)})
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(status=status.HTTP_404_NOT_FOUND)

