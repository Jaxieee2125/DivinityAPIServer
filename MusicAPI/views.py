# music_api/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
# Import các serializers đã cập nhật
from .serializers import (
    MusicGenreSerializer, UserSerializer, AdminSerializer,
    ArtistSerializer, AlbumSerializer, SongSerializer,
    PlaylistSerializer
)
from pymongo import MongoClient
from bson import ObjectId
from django.conf import settings # Cần cho logic media URL (mặc dù chủ yếu dùng trong serializer)
from django.contrib.auth.hashers import make_password, check_password # Import để hash password

# --- MongoDB Connection (Giả sử cấu hình ở đây hoặc import từ nơi khác) ---
try:
    # Thay thế bằng connection string của bạn nếu cần
    client = MongoClient(settings.MONGO_DB_URL if hasattr(settings, 'MONGO_DB_URL') else 'mongodb://localhost:27017/')
    # Thay thế 'MusicServer' bằng tên database của bạn
    db = client[settings.MONGO_DB_NAME if hasattr(settings, 'MONGO_DB_NAME') else 'MusicDatabase']
    # Kiểm tra kết nối (tùy chọn)
    client.admin.command('ping')
    print("MongoDB connected successfully!")
except Exception as e:
    print(f"Error connecting to MongoDB: {e}")
    # Có thể raise exception hoặc xử lý khác
    db = None # Đặt db thành None để các view biết lỗi

# --- Helper Function ---
def get_object(collection, pk):
    """ Lấy một document từ collection bằng _id (dạng string). """
    if not db: # Kiểm tra db connection
        return None
    try:
        object_id = ObjectId(pk)
        return collection.find_one({'_id': object_id})
    except Exception: # Bắt lỗi ObjectId không hợp lệ hoặc lỗi khác
        return None

# --- MusicGenre Views ---
class MusicGenreList(APIView):
    def get(self, request):
        if not db: return Response({"error": "Database connection failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        genres = list(db.musicgenres.find())
        # Không cần context vì MusicGenreSerializer không xử lý media URL
        serializer = MusicGenreSerializer(genres, many=True)
        return Response(serializer.data)

    def post(self, request):
        if not db: return Response({"error": "Database connection failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        serializer = MusicGenreSerializer(data=request.data)
        if serializer.is_valid():
            result = db.musicgenres.insert_one(serializer.validated_data)
            created_genre = db.musicgenres.find_one({'_id': result.inserted_id})
            return Response(MusicGenreSerializer(created_genre).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class MusicGenreDetail(APIView):
    def get(self, request, pk):
        genre = get_object(db.musicgenres, pk)
        if genre:
            serializer = MusicGenreSerializer(genre)
            return Response(serializer.data)
        return Response(status=status.HTTP_404_NOT_FOUND)

    def put(self, request, pk):
        genre = get_object(db.musicgenres, pk)
        if genre:
            serializer = MusicGenreSerializer(genre, data=request.data, partial=True)
            if serializer.is_valid():
                db.musicgenres.update_one({'_id': ObjectId(pk)}, {'$set': serializer.validated_data})
                updated_genre = get_object(db.musicgenres, pk)
                return Response(MusicGenreSerializer(updated_genre).data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, pk):
        result = db.musicgenres.delete_one({'_id': ObjectId(pk)})
        if result.deleted_count == 1:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(status=status.HTTP_404_NOT_FOUND)


# --- User Views ---
class UserList(APIView):
    def get(self, request):
        if not db: return Response({"error": "Database connection failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        users = list(db.users.find())
        serializer = UserSerializer(users, many=True, context={'request': request}) # Thêm context
        return Response(serializer.data)

    def post(self, request):
        if not db: return Response({"error": "Database connection failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        serializer = UserSerializer(data=request.data, context={'request': request}) # Thêm context
        if serializer.is_valid():
            user_data = serializer.validated_data
            # TODO: Kiểm tra email/username đã tồn tại chưa
            # Hash password trước khi lưu
            user_data['password'] = make_password(user_data['password'])
            # TODO: Xử lý lưu file 'profile_picture' nếu có upload
            result = db.users.insert_one(user_data)
            created_user = db.users.find_one({'_id': result.inserted_id})
            if created_user:
                response_serializer = UserSerializer(created_user, context={'request': request}) # Thêm context
                return Response(response_serializer.data, status=status.HTTP_201_CREATED)
            return Response({"error": "Could not retrieve created user"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class UserDetail(APIView):
    # TODO: Thêm permission checks (IsAuthenticated, IsOwnerOrAdmin?)
    def get(self, request, pk):
        user = get_object(db.users, pk)
        if user:
            serializer = UserSerializer(user, context={'request': request}) # Thêm context
            return Response(serializer.data)
        return Response(status=status.HTTP_404_NOT_FOUND)

    def put(self, request, pk):
        user = get_object(db.users, pk)
        if user:
            # TODO: Check permissions (chỉ user đó hoặc admin được sửa)
            serializer = UserSerializer(user, data=request.data, partial=True, context={'request': request}) # Thêm context
            if serializer.is_valid():
                update_data = serializer.validated_data
                # Hash password mới nếu được cung cấp
                if 'password' in update_data:
                    update_data['password'] = make_password(update_data['password'])
                # TODO: Xử lý upload/xóa file 'profile_picture' nếu có
                db.users.update_one({'_id': ObjectId(pk)}, {'$set': update_data})
                updated_user = get_object(db.users, pk)
                if updated_user:
                     response_serializer = UserSerializer(updated_user, context={'request': request}) # Thêm context
                     return Response(response_serializer.data)
                return Response(status=status.HTTP_404_NOT_FOUND) # Should not happen if update succeeded
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, pk):
        # TODO: Check permissions (admin?)
        # TODO: Xử lý xóa file 'profile_picture' trên storage
        result = db.users.delete_one({'_id': ObjectId(pk)})
        if result.deleted_count == 1:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(status=status.HTTP_404_NOT_FOUND)


# --- Admin Views ---
class AdminList(APIView):
    # TODO: Add permission checks (IsAdminUser?)
    def get(self, request):
        if not db: return Response({"error": "Database connection failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        admins = list(db.admin.find())
        serializer = AdminSerializer(admins, many=True) # Không cần context nếu AdminSerializer ko có media
        return Response(serializer.data)

    def post(self, request):
        if not db: return Response({"error": "Database connection failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        serializer = AdminSerializer(data=request.data) # Không cần context
        if serializer.is_valid():
            admin_data = serializer.validated_data
            admin_data['password'] = make_password(admin_data['password'])
            # TODO: Kiểm tra user_id có tồn tại và chưa phải admin?
            result = db.admin.insert_one(admin_data)
            created_admin = db.admin.find_one({'_id': result.inserted_id})
            if created_admin:
                 return Response(AdminSerializer(created_admin).data, status=status.HTTP_201_CREATED)
            return Response({"error": "Could not retrieve created admin"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class AdminDetail(APIView):
     # TODO: Add permission checks (IsAdminUser?)
    def get(self, request, pk):
        admin = get_object(db.admin, pk)
        if admin:
            serializer = AdminSerializer(admin)
            return Response(serializer.data)
        return Response(status=status.HTTP_404_NOT_FOUND)

    def put(self, request, pk):
        admin = get_object(db.admin, pk)
        if admin:
            serializer = AdminSerializer(admin, data=request.data, partial=True)
            if serializer.is_valid():
                update_data = serializer.validated_data
                if 'password' in update_data:
                    update_data['password'] = make_password(update_data['password'])
                db.admin.update_one({'_id': ObjectId(pk)}, {'$set': update_data})
                updated_admin = get_object(db.admin, pk)
                if updated_admin:
                    return Response(AdminSerializer(updated_admin).data)
                return Response(status=status.HTTP_404_NOT_FOUND)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, pk):
        result = db.admin.delete_one({'_id': ObjectId(pk)})
        if result.deleted_count == 1:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(status=status.HTTP_404_NOT_FOUND)


# --- Artist Views ---
class ArtistList(APIView):
    def get(self, request):
        if not db: return Response({"error": "Database connection failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        artists = list(db.artists.find())
        serializer = ArtistSerializer(artists, many=True, context={'request': request}) # Thêm context
        return Response(serializer.data)

    def post(self, request):
        if not db: return Response({"error": "Database connection failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        serializer = ArtistSerializer(data=request.data, context={'request': request}) # Thêm context
        if serializer.is_valid():
            # TODO: Xử lý lưu file 'artist_avatar' nếu có upload
            result = db.artists.insert_one(serializer.validated_data)
            created_artist = db.artists.find_one({'_id': result.inserted_id})
            if created_artist:
                response_serializer = ArtistSerializer(created_artist, context={'request': request}) # Thêm context
                return Response(response_serializer.data, status=status.HTTP_201_CREATED)
            return Response({"error": "Could not retrieve created artist"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ArtistDetail(APIView):
    def get(self, request, pk):
        artist = get_object(db.artists, pk)
        if artist:
            # TODO: Cần lấy thêm albums/songs của artist để trả về nếu serializer yêu cầu
            serializer = ArtistSerializer(artist, context={'request': request}) # Thêm context
            return Response(serializer.data)
        return Response(status=status.HTTP_404_NOT_FOUND)

    def put(self, request, pk):
        # TODO: Add permission checks?
        artist = get_object(db.artists, pk)
        if artist:
            serializer = ArtistSerializer(artist, data=request.data, partial=True, context={'request': request}) # Thêm context
            if serializer.is_valid():
                 # TODO: Xử lý upload/xóa file 'artist_avatar' nếu có
                update_data = serializer.validated_data
                db.artists.update_one({'_id': ObjectId(pk)}, {'$set': update_data})
                updated_artist = get_object(db.artists, pk)
                if updated_artist:
                     response_serializer = ArtistSerializer(updated_artist, context={'request': request}) # Thêm context
                     return Response(response_serializer.data)
                return Response(status=status.HTTP_404_NOT_FOUND)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, pk):
         # TODO: Add permission checks?
         # TODO: Xử lý xóa file 'artist_avatar' trên storage
        result = db.artists.delete_one({'_id': ObjectId(pk)})
        if result.deleted_count == 1:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(status=status.HTTP_404_NOT_FOUND)


# --- Album Views ---
class AlbumList(APIView):
    def get(self, request):
        if not db: return Response({"error": "Database connection failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        # TODO: Cần fetch dữ liệu artist lồng vào đây bằng $lookup hoặc xử lý sau
        # Ví dụ đơn giản (chưa tối ưu, không có $lookup):
        albums_cursor = db.albums.find()
        albums_list = []
        for album in albums_cursor:
            artist_info = get_object(db.artists, str(album.get('artist_id'))) # Chuyển ObjectId thành str
            album['artist'] = artist_info # Gán artist vào document album
            albums_list.append(album)

        serializer = AlbumSerializer(albums_list, many=True, context={'request': request}) # Thêm context
        return Response(serializer.data)

    def post(self, request):
        if not db: return Response({"error": "Database connection failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        serializer = AlbumSerializer(data=request.data, context={'request': request}) # Thêm context
        if serializer.is_valid():
             # TODO: Xử lý lưu file 'image' nếu có upload
            result = db.albums.insert_one(serializer.validated_data)
            # TODO: Fetch lại album cùng với artist lồng nhau để trả về
            created_album_raw = db.albums.find_one({'_id': result.inserted_id})
            if created_album_raw:
                 artist_info = get_object(db.artists, str(created_album_raw.get('artist_id')))
                 created_album_raw['artist'] = artist_info
                 response_serializer = AlbumSerializer(created_album_raw, context={'request': request}) # Thêm context
                 return Response(response_serializer.data, status=status.HTTP_201_CREATED)
            return Response({"error": "Could not retrieve created album"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AlbumDetail(APIView):
    def get(self, request, pk):
        # TODO: Cần fetch dữ liệu artist và songs lồng vào đây bằng $lookup hoặc xử lý sau
        album = get_object(db.albums, pk)
        if album:
             artist_info = get_object(db.artists, str(album.get('artist_id')))
             album['artist'] = artist_info
             # Ví dụ lấy songs (chưa tối ưu):
             # album['songs'] = list(db.songs.find({'album_id': album['_id']}))
             serializer = AlbumSerializer(album, context={'request': request}) # Thêm context
             return Response(serializer.data)
        return Response(status=status.HTTP_404_NOT_FOUND)

    def put(self, request, pk):
        album = get_object(db.albums, pk)
        if album:
            serializer = AlbumSerializer(album, data=request.data, partial=True, context={'request': request}) # Thêm context
            if serializer.is_valid():
                # TODO: Xử lý upload/xóa file 'image' nếu có
                update_data = serializer.validated_data
                db.albums.update_one({'_id': ObjectId(pk)}, {'$set': update_data})
                # TODO: Fetch lại album cùng với artist lồng nhau để trả về
                updated_album_raw = get_object(db.albums, pk)
                if updated_album_raw:
                    artist_info = get_object(db.artists, str(updated_album_raw.get('artist_id')))
                    updated_album_raw['artist'] = artist_info
                    response_serializer = AlbumSerializer(updated_album_raw, context={'request': request}) # Thêm context
                    return Response(response_serializer.data)
                return Response(status=status.HTTP_404_NOT_FOUND)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, pk):
        # TODO: Xử lý xóa file 'image' trên storage
        result = db.albums.delete_one({'_id': ObjectId(pk)})
        if result.deleted_count == 1:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(status=status.HTTP_404_NOT_FOUND)


# --- Song Views (Đảm bảo context đã được thêm ở lần trước) ---
class SongList(APIView):
    def get(self, request):
        if not db: return Response({"error": "Database connection failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        # TODO: Cần $lookup để lấy artist/album lồng vào hiệu quả
        songs_cursor = db.songs.find()
        songs_list = []
        for song in songs_cursor:
            # Lấy thông tin artists (ví dụ đơn giản)
            artist_ids = song.get('artist_ids', [])
            song['artists'] = [get_object(db.artists, str(aid)) for aid in artist_ids if aid]
            # Lấy thông tin album (ví dụ đơn giản)
            album_id = song.get('album_id')
            if album_id:
                song['album'] = get_object(db.albums, str(album_id))
            else:
                song['album'] = None
            songs_list.append(song)

        serializer = SongSerializer(songs_list, many=True, context={'request': request}) # Thêm context
        return Response(serializer.data)

    def post(self, request):
        if not db: return Response({"error": "Database connection failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        serializer = SongSerializer(data=request.data, context={'request': request}) # Thêm context
        if serializer.is_valid():
            song_data = serializer.validated_data
            # TODO: Xử lý lưu file 'file_up' nếu có upload
            # Lưu ý: validated_data chỉ chứa các write_only fields như artist_ids, album_id
            result = db.songs.insert_one(song_data)
            # TODO: Fetch lại bài hát với artist/album lồng nhau để trả về
            created_song_raw = db.songs.find_one({'_id': result.inserted_id})
            if created_song_raw:
                 artist_ids = created_song_raw.get('artist_ids', [])
                 created_song_raw['artists'] = [get_object(db.artists, str(aid)) for aid in artist_ids if aid]
                 album_id = created_song_raw.get('album_id')
                 created_song_raw['album'] = get_object(db.albums, str(album_id)) if album_id else None

                 response_serializer = SongSerializer(created_song_raw, context={'request': request}) # Thêm context
                 return Response(response_serializer.data, status=status.HTTP_201_CREATED)
            return Response({"error": "Could not retrieve created song"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class SongDetail(APIView):
    def get(self, request, pk):
         # TODO: Cần $lookup để lấy artist/album lồng vào hiệu quả
        song = get_object(db.songs, pk)
        if song:
            artist_ids = song.get('artist_ids', [])
            song['artists'] = [get_object(db.artists, str(aid)) for aid in artist_ids if aid]
            album_id = song.get('album_id')
            song['album'] = get_object(db.albums, str(album_id)) if album_id else None
            serializer = SongSerializer(song, context={'request': request}) # Thêm context
            return Response(serializer.data)
        return Response(status=status.HTTP_404_NOT_FOUND)

    def put(self, request, pk):
        song = get_object(db.songs, pk)
        if song:
            serializer = SongSerializer(song, data=request.data, partial=True, context={'request': request}) # Thêm context
            if serializer.is_valid():
                # TODO: Xử lý upload/xóa file 'file_up' nếu có
                update_data = serializer.validated_data
                db.songs.update_one({'_id': ObjectId(pk)}, {'$set': update_data})
                # TODO: Fetch lại bài hát với artist/album lồng nhau
                updated_song_raw = get_object(db.songs, pk)
                if updated_song_raw:
                    artist_ids = updated_song_raw.get('artist_ids', [])
                    updated_song_raw['artists'] = [get_object(db.artists, str(aid)) for aid in artist_ids if aid]
                    album_id = updated_song_raw.get('album_id')
                    updated_song_raw['album'] = get_object(db.albums, str(album_id)) if album_id else None
                    response_serializer = SongSerializer(updated_song_raw, context={'request': request}) # Thêm context
                    return Response(response_serializer.data)
                return Response(status=status.HTTP_404_NOT_FOUND)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, pk):
        # TODO: Xử lý xóa file 'file_up' trên storage
        result = db.songs.delete_one({'_id': ObjectId(pk)})
        if result.deleted_count == 1:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(status=status.HTTP_404_NOT_FOUND)


# --- Playlist Views ---
class PlaylistList(APIView):
     # TODO: Add permissions (IsAuthenticated?)
    def get(self, request):
        if not db: return Response({"error": "Database connection failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        # TODO: Lọc playlist theo user hiện tại? request.user.id
        # TODO: Nếu PlaylistSerializer lồng SongSerializer, cần fetch cả song details
        playlists = list(db.playlists.find()) # Ví dụ lấy tất cả
        # Thêm context nếu PlaylistSerializer hoặc serializer lồng nhau cần request
        serializer = PlaylistSerializer(playlists, many=True, context={'request': request})
        return Response(serializer.data)

    def post(self, request):
        # TODO: Add permissions (IsAuthenticated?)
        if not db: return Response({"error": "Database connection failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        # Thêm context nếu cần trong quá trình validate hoặc trả về response
        serializer = PlaylistSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            playlist_data = serializer.validated_data
            # TODO: Gán user_id = request.user.id
            # TODO: Validate song_ids/songs trong playlist nếu cần
            result = db.playlists.insert_one(playlist_data)
            created_playlist = db.playlists.find_one({'_id': result.inserted_id})
            if created_playlist:
                 # Thêm context nếu cần khi trả về
                 response_serializer = PlaylistSerializer(created_playlist, context={'request': request})
                 return Response(response_serializer.data, status=status.HTTP_201_CREATED)
            return Response({"error": "Could not retrieve created playlist"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PlaylistDetail(APIView):
    # TODO: Add permissions (IsAuthenticated and IsOwnerOrPublic?)
    def get(self, request, pk):
        # TODO: Fetch playlist và có thể cả chi tiết bài hát lồng nhau
        playlist = get_object(db.playlists, pk)
        if playlist:
             # TODO: Check permission xem user có được xem playlist này không
             # Thêm context nếu cần
             serializer = PlaylistSerializer(playlist, context={'request': request})
             return Response(serializer.data)
        return Response(status=status.HTTP_404_NOT_FOUND)

    def put(self, request, pk):
        # TODO: Add permissions (IsAuthenticated and IsOwner?)
        playlist = get_object(db.playlists, pk)
        if playlist:
             # TODO: Check permission
             # Thêm context nếu cần
            serializer = PlaylistSerializer(playlist, data=request.data, partial=True, context={'request': request})
            if serializer.is_valid():
                # TODO: Validate songs/song_ids nếu có thay đổi
                update_data = serializer.validated_data
                db.playlists.update_one({'_id': ObjectId(pk)}, {'$set': update_data})
                updated_playlist = get_object(db.playlists, pk)
                if updated_playlist:
                    # Thêm context nếu cần
                    response_serializer = PlaylistSerializer(updated_playlist, context={'request': request})
                    return Response(response_serializer.data)
                return Response(status=status.HTTP_404_NOT_FOUND)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, pk):
        # TODO: Add permissions (IsAuthenticated and IsOwner?)
        result = db.playlists.delete_one({'_id': ObjectId(pk)})
        if result.deleted_count == 1:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(status=status.HTTP_404_NOT_FOUND)

class SearchView(APIView):
    def get(self, request):
        query = request.GET.get('q', '').strip()
        limit = 5 # Giới hạn số lượng kết quả mỗi loại

        if not query:
            return Response({"albums": [], "tracks": [], "artists": []})

        # TODO: Sử dụng $text search hoặc $regex hiệu quả hơn
        # Ví dụ đơn giản với $regex (không phân biệt hoa thường)
        regex_query = {'$regex': query, '$options': 'i'}

        try:
            # Tìm albums
            albums_cursor = db.albums.find({'album_name': regex_query}).limit(limit)
            albums_list = []
            for album in albums_cursor:
                # Lấy artist lồng vào (cần tối ưu bằng $lookup)
                artist_info = get_object(db.artists, str(album.get('artist_id')))
                album['artist'] = artist_info
                albums_list.append(album)
            album_serializer = AlbumSerializer(albums_list, many=True, context={'request': request})

            # Tìm tracks
            tracks_cursor = db.songs.find({'song_name': regex_query}).limit(limit)
            tracks_list = []
            for track in tracks_cursor:
                 # Lấy artist/album lồng vào (cần tối ưu bằng $lookup)
                 artist_ids = track.get('artist_ids', [])
                 track['artists'] = [get_object(db.artists, str(aid)) for aid in artist_ids if aid]
                 album_id = track.get('album_id')
                 track['album'] = get_object(db.albums, str(album_id)) if album_id else None
                 tracks_list.append(track)
            # Có thể tạo SongBasicSerializer hoặc dùng SongSerializer đầy đủ
            track_serializer = SongSerializer(tracks_list, many=True, context={'request': request})


            # Tìm artists
            artists_cursor = db.artists.find({'artist_name': regex_query}).limit(limit)
            artist_serializer = ArtistSerializer(list(artists_cursor), many=True, context={'request': request})

            return Response({
                "albums": album_serializer.data,
                "tracks": track_serializer.data,
                "artists": artist_serializer.data
            })
        except Exception as e:
             print(f"Search error: {e}")
             return Response({"error": "Search failed"}, status=500)