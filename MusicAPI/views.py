# music_api/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from sklearn import pipeline
# Import các serializers đã cập nhật
from .serializers import (
    MusicGenreSerializer, UserSerializer, AdminSerializer,
    ArtistSerializer, AlbumSerializer, SongSerializer,
    PlaylistSerializer, AlbumSelectSerializer, ArtistSelectSerializer
)
from pymongo import MongoClient
from bson import ObjectId
from django.conf import settings # Cần cho logic media URL (mặc dù chủ yếu dùng trong serializer)
from django.contrib.auth.hashers import make_password, check_password # Import để hash password
import os
from django.core.files.storage import default_storage
from datetime import datetime, timedelta # Import datetime để xử lý ngày tháng
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken, AccessToken
from .permissions import IsAdminFromMongo # Import permission tùy chỉnh nếu cần


# --- MongoDB Connection (Giả sử cấu hình ở đây hoặc import từ nơi khác) ---
try:
    # Thay thế bằng connection string của bạn nếu cần
    client = MongoClient('mongodb://localhost:27017/')
    # Thay thế 'MusicServer' bằng tên database của bạn
    db = client['MusicDatabase']
    # Kiểm tra kết nối (tùy chọn)
    client.admin.command('ping')
    print("MongoDB connected successfully!")
except Exception as e:
    print(f"Error connecting to MongoDB: {e}")
    # Có thể raise exception hoặc xử lý khác
    db = None # Đặt db thành None để các view biết lỗi

# --- Helper Function ---
permission_classes = [AllowAny]
def get_object(collection, pk):
    """ Lấy một document từ collection bằng _id (dạng string). """
    if not db: # Kiểm tra db connection
        return None
    try:
        object_id = ObjectId(pk)
        return collection.find_one({'_id': object_id})
    except Exception: # Bắt lỗi ObjectId không hợp lệ hoặc lỗi khác
        return None
    
# --- Custom Admin Login View ---

class AdminLoginView(APIView):
    permission_classes = [AllowAny]

    @staticmethod
    def get_tokens_for_admin_user(user_doc):
        # --- Tự xây dựng Payload ---
        user_id_str = str(user_doc['_id'])
        username = user_doc.get('username')

        # Tạo Refresh Token trước (nó chứa các thông tin cơ bản)
        # Chúng ta cần tạo instance RefreshToken để lấy access_token từ nó
        # Hoặc tạo cả hai từ đầu

        # Cách 1: Tạo RefreshToken, AccessToken lấy từ RefreshToken
        try:
            refresh = RefreshToken() # Tạo instance rỗng
            # Thêm các claims cần thiết vào payload của refresh token
            refresh['user_mongo_id'] = user_id_str
            # Thêm các claims khác bạn muốn có trong refresh token (thường ít hơn access)
            # refresh['username'] = username # Tùy chọn

            # Tạo access token từ refresh token (sẽ kế thừa một số claim và có thời hạn riêng)
            access = refresh.access_token
            access['username'] = username # Thêm vào access token nếu cần
            access['is_staff'] = True     # Thêm quyền vào access token
            access['is_active'] = True    # Thêm trạng thái vào access token
            # Thêm các claims khác cho access token nếu cần

            return {
                'refresh': str(refresh),
                'access': str(access),
            }

        except Exception as e:
             print(f"Error creating tokens for {username}: {e}")
             raise e # Ném lỗi ra ngoài để view xử lý

    def post(self, request):
        if not db: return Response({"error": "Database connection failed"}, status=500)

        username = request.data.get('username')
        password = request.data.get('password')

        if not username or not password:
            return Response({"error": "Username and password are required."}, status=400)

        admin_doc = db.admin.find_one({'username': username})

        if admin_doc:
            password_valid = check_password(password, admin_doc.get('password', ''))
            if password_valid:
                user_id_from_admin = admin_doc.get('user_id')
                if not user_id_from_admin or not isinstance(user_id_from_admin, ObjectId):
                     print(f"Error: Admin record for {username} missing or invalid user_id.")
                     return Response({"detail": "Admin account configuration error."}, status=500)

                # Tạo dict thông tin user để truyền vào hàm tạo token
                user_info_for_token = {
                    '_id': user_id_from_admin, # ObjectId
                    'username': admin_doc.get('username')
                }
                try:
                    # Gọi hàm helper để tạo token
                    tokens = self.get_tokens_for_admin_user(user_info_for_token)
                    print(f"Admin login successful for: {username}")
                    return Response(tokens)
                except Exception as token_e:
                     print(f"Error generating token for admin {username}: {token_e}")
                     return Response({"detail": "Could not generate authentication token."}, status=500)
            else:
                print(f"Admin login failed for {username}: Invalid password")
        else:
             print(f"Admin login failed: Admin username '{username}' not found.")

        return Response({"detail": "Invalid credentials or not an authorized admin."}, status=401)


# --- MusicGenre Views ---
class MusicGenreList(APIView):
    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()] # Ai cũng xem được list
        # Các method khác (POST) sẽ dùng default (IsAdminFromMongo)
        return super().get_permissions()
    
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
    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()] # Ai cũng xem được list
        # Các method khác (POST) sẽ dùng default (IsAdminFromMongo)
        return super().get_permissions()
    
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
    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()] # Ai cũng xem được list
        # Các method khác (POST) sẽ dùng default (IsAdminFromMongo)
        return super().get_permissions()
    
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
    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()] # Ai cũng xem được list
        # Các method khác (POST) sẽ dùng default (IsAdminFromMongo)
        return super().get_permissions()
    
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
    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()] # Ai cũng xem được list
        # Các method khác (POST) sẽ dùng default (IsAdminFromMongo)
        return super().get_permissions()
    
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
    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()] # Ai cũng xem được list
        # Các method khác (POST) sẽ dùng default (IsAdminFromMongo)
        return super().get_permissions()
    
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
    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()] # Ai cũng xem được list
        # Các method khác (POST) sẽ dùng default (IsAdminFromMongo)
        return super().get_permissions()
    
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
    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()] # Ai cũng xem được list
        # Các method khác (POST) sẽ dùng default (IsAdminFromMongo)
        return super().get_permissions()
    
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
# --- Aggregation Pipeline Helper ---
permission_classes = [AllowAny]
def get_song_aggregation_pipeline():
    """Trả về các stages $lookup, $unwind, $project cho Song."""
    return [
        { '$lookup': { 'from': 'artists', 'localField': 'artist_ids', 'foreignField': '_id', 'as': 'artist_details' } },
        { '$lookup': { 'from': 'albums', 'localField': 'album_id', 'foreignField': '_id', 'as': 'album_details' } },
        { '$unwind': { 'path': '$album_details', 'preserveNullAndEmptyArrays': True } },
        { '$project': {
            '_id': 1, # Đảm bảo trả về _id
            'song_name': 1, 'description': 1, 'lyrics': 1, 'release_time': 1, 'duration_song': 1,
            'number_of_plays': 1, 'number_of_likes': 1, 'file_up': 1, 'status': 1,
            'artist_ids': 1, # Giữ lại ID nếu cần dùng ở đâu đó
            'album_id': 1,   # Giữ lại ID nếu cần dùng ở đâu đó
            'artists': { '$map': {
                'input': '$artist_details', 'as': 'artist',
                'in': { '_id': '$$artist._id', 'artist_name': '$$artist.artist_name', 'artist_avatar': '$$artist.artist_avatar' }
            }},
            'album': { '$cond': {
                'if': '$album_details',
                'then': { '_id': '$album_details._id', 'album_name': '$album_details.album_name', 'image': '$album_details.image' },
                'else': None
            }}
        }}
    ]

# --- Song Views ---

class SongList(APIView):
    """
    API endpoint để lấy danh sách bài hát hoặc tạo bài hát mới.
    """
    _get_pipeline_stages = staticmethod(get_song_aggregation_pipeline)

    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()] # Ai cũng xem được list
        # Các method khác (POST) sẽ dùng default (IsAdminFromMongo)
        return super().get_permissions()
    
    def get(self, request):
        """ Lấy danh sách bài hát với thông tin Artist/Album lồng nhau. """
        if not db: return Response({"error": "Database connection failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        try:
            pipeline = self._get_pipeline_stages()
            pipeline.append({'$sort': {'song_name': 1}})
            # TODO: Thêm pagination vào pipeline nếu cần ($skip, $limit)
            songs_list = list(db.songs.aggregate(pipeline))
            serializer = SongSerializer(songs_list, many=True, context={'request': request})
            return Response(serializer.data)
        except Exception as e:
            print(f"Error fetching songs with lookup: {e}")
            return Response({"error": "Could not retrieve songs"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        """ Tạo bài hát mới, xử lý upload file và đổi tên theo _id. """
        if not db: return Response({"error": "Database connection failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # --- Xử lý dữ liệu đầu vào từ request ---
        # Sử dụng request.POST.copy() để lấy dữ liệu form text
        # Sử dụng request.FILES để lấy file upload
        mutable_post_data = request.POST.copy()

        # Luôn lấy artist_ids bằng getlist để đảm bảo là list
        artist_id_list_str = mutable_post_data.getlist('artist_ids')
        print(f"[POST] Received artist_ids from POST.getlist: {artist_id_list_str}") # DEBUG

        # Validate và chuyển đổi ObjectId cho artist_ids
        valid_artist_ids = []
        for aid_str in artist_id_list_str:
            aid_str = aid_str.strip()
            if not aid_str: continue
            try:
                valid_artist_ids.append(ObjectId(aid_str))
            except Exception as e:
                print(f"[POST] Invalid Artist ObjectId received: '{aid_str}' - Error: {e}")
                return Response({"artist_ids": [f"Invalid ObjectId format provided: '{aid_str}'"]}, status=status.HTTP_400_BAD_REQUEST)

        if not valid_artist_ids:
             return Response({"artist_ids": ["At least one valid Artist ID is required."]}, status=status.HTTP_400_BAD_REQUEST)

        # Tạo dictionary dữ liệu để đưa vào serializer
        data_for_serializer = mutable_post_data.dict()
        data_for_serializer['artist_ids'] = valid_artist_ids # Gán list ObjectId đã validate

        # Validate và chuyển đổi album_id (nếu có)
        album_id_str = data_for_serializer.get('album_id', '').strip()
        if album_id_str:
            try:
                 data_for_serializer['album_id'] = ObjectId(album_id_str)
            except Exception:
                 return Response({"album_id": [f"Invalid ObjectId format provided: '{album_id_str}'"]}, status=400)
        else:
            data_for_serializer['album_id'] = None # Đặt là None nếu rỗng

        # Thêm file vào data (để serializer có thể validate nếu 'required=True')
        if 'audio_file' in request.FILES:
            data_for_serializer['audio_file'] = request.FILES['audio_file']
        else:
            # Xử lý nếu file là bắt buộc nhưng không được gửi
            # if SongSerializer().fields['audio_file'].required:
            #     return Response({"audio_file": ["This field is required."]}, status=400)
            data_for_serializer['audio_file'] = None # Hoặc đặt là None nếu không bắt buộc

        print("--- [POST] Data for Serializer ---")
        print({k: v for k, v in data_for_serializer.items() if k != 'audio_file'}) # Không in object file
        if data_for_serializer.get('audio_file'): print("audio_file: [File Object]")
        print("---------------------------------")

        # Validate dữ liệu bằng serializer
        serializer = SongSerializer(data=data_for_serializer, context={'request': request})

        if serializer.is_valid():
            song_data = serializer.validated_data
            audio_file = song_data.pop('audio_file', None) # Lấy file ra khỏi data sẽ lưu vào DB

            saved_file_path = None
            new_song_id = None

            try:
                # 1. Tạo document bài hát (chưa có file_up) để lấy _id
                mongo_data = {k: v for k, v in song_data.items()} # Dữ liệu đã clean
                if 'release_time' in mongo_data and mongo_data['release_time']:
                    mongo_data['release_time'] = datetime.combine(mongo_data['release_time'], datetime.min.time())
                # artist_ids và album_id đã là ObjectId (hoặc None) từ serializer

                insert_result = db.songs.insert_one(mongo_data)
                new_song_id = insert_result.inserted_id
                print(f"[POST] Created initial song document with ID: {new_song_id}")

                # 2. Lưu file upload (nếu có) và đổi tên
                if audio_file and new_song_id:
                    original_filename, file_extension = os.path.splitext(audio_file.name)
                    file_extension = file_extension.lower()
                    new_filename = f"{str(new_song_id)}{file_extension}"
                    relative_dir = 'audio'
                    saved_file_path_relative = os.path.join(relative_dir, new_filename).replace("\\", "/")
                    saved_file_path = default_storage.save(saved_file_path_relative, audio_file)
                    print(f"[POST] Saved uploaded file as: {saved_file_path}")

                    # 3. Cập nhật document với đường dẫn file_up
                    db.songs.update_one( {'_id': new_song_id}, {'$set': {'file_up': saved_file_path}} )
                    print(f"[POST] Updated song document {new_song_id} with file_up: {saved_file_path}")
                else:
                    saved_file_path = None

                # 4. Fetch lại dữ liệu hoàn chỉnh để trả về response
                pipeline_detail = [{'$match': {'_id': new_song_id}}] + self._get_pipeline_stages()
                created_song_agg = list(db.songs.aggregate(pipeline_detail))

                if created_song_agg:
                    response_serializer = SongSerializer(created_song_agg[0], context={'request': request})
                    return Response(response_serializer.data, status=status.HTTP_201_CREATED)
                else:
                     print(f"[POST] Error: Could not find created song {new_song_id} after aggregation.")
                     raise Exception("Could not retrieve created song details after aggregation.")

            except Exception as e:
                print(f"[POST] Error during song creation/file upload: {e}")
                # --- Rollback ---
                if new_song_id:
                    db.songs.delete_one({'_id': new_song_id})
                    print(f"[POST] Rolled back: Deleted song doc {new_song_id}")
                if saved_file_path and default_storage.exists(saved_file_path):
                     default_storage.delete(saved_file_path)
                     print(f"[POST] Rolled back: Deleted file {saved_file_path}")
                return Response({"error": f"Could not create song: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        else:
            print("[POST] Serializer errors:", serializer.errors)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SongDetail(APIView):
    """
    Lấy, cập nhật hoặc xóa một bài hát cụ thể.
    """
    
    _get_pipeline_stages = staticmethod(get_song_aggregation_pipeline)

    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()] # Ai cũng xem được list
        # Các method khác (POST) sẽ dùng default (IsAdminFromMongo)
        return super().get_permissions()
    
    def get(self, request, pk):
        """ Lấy chi tiết bài hát với thông tin Artist/Album lồng nhau. """
        if not db: return Response({"error": "Database connection failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        song_id = None
        try: song_id = ObjectId(pk)
        except Exception: return Response({"error": "Invalid Song ID format"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            pipeline_detail = [{'$match': {'_id': song_id}}] + self._get_pipeline_stages()
            song_agg = list(db.songs.aggregate(pipeline_detail))

            if song_agg:
                serializer = SongSerializer(song_agg[0], context={'request': request})
                return Response(serializer.data)
            else:
                return Response(status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            print(f"[GET /songs/{pk}] Error fetching song detail: {e}")
            return Response({"error": f"Could not retrieve song {pk}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request, pk):
        """ Cập nhật bài hát (bao gồm cả thay thế file audio). """
        if not db: return Response({"error": "Database connection failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        song_id = None
        try: song_id = ObjectId(pk)
        except Exception: return Response({"error": "Invalid Song ID format"}, status=status.HTTP_400_BAD_REQUEST)

        song = db.songs.find_one({'_id': song_id})
        if not song: return Response(status=status.HTTP_404_NOT_FOUND)

        # --- Xử lý dữ liệu đầu vào cho PUT ---
        mutable_post_data = request.POST.copy()
        data_for_serializer = mutable_post_data.dict() # Dữ liệu text

        # Xử lý artist_ids nếu được gửi lên
        if 'artist_ids' in mutable_post_data:
            artist_id_list_str = mutable_post_data.getlist('artist_ids')
            print(f"[PUT /songs/{pk}] Received artist_ids from PUT.getlist: {artist_id_list_str}") # DEBUG
            valid_artist_ids = []
            for aid_str in artist_id_list_str:
                aid_str = aid_str.strip()
                if not aid_str: continue
                try: valid_artist_ids.append(ObjectId(aid_str))
                except Exception as e: return Response({"artist_ids": [f"Invalid ObjectId format provided: '{aid_str}'"]}, status=400)
            # Nếu gửi key 'artist_ids' thì phải có ít nhất 1 ID hợp lệ
            if not valid_artist_ids: return Response({"artist_ids": ["At least one valid Artist ID is required if 'artist_ids' key is provided."]}, status=400)
            data_for_serializer['artist_ids'] = valid_artist_ids # Gán lại list ObjectId

        # Xử lý album_id nếu được gửi lên
        if 'album_id' in data_for_serializer:
            album_id_str = data_for_serializer.get('album_id', '').strip()
            if album_id_str:
                try: data_for_serializer['album_id'] = ObjectId(album_id_str)
                except Exception: return Response({"album_id": [f"Invalid ObjectId format provided: '{album_id_str}'"]}, status=400)
            else: data_for_serializer['album_id'] = None # Cho phép xóa album

        # Thêm file nếu có trong request.FILES
        if 'audio_file' in request.FILES:
            data_for_serializer['audio_file'] = request.FILES['audio_file']
        else:
             # Nếu không gửi file mới, cần kiểm tra xem có muốn xóa file cũ không
             # (Trong PUT/PATCH, không gửi field nghĩa là không thay đổi field đó,
             # trừ khi serializer có logic đặc biệt hoặc bạn thêm field 'remove_audio_file')
             pass # Serializer sẽ không thấy 'audio_file' nếu không có trong request.FILES

        print(f"--- [PUT /songs/{pk}] Data for Serializer ---")
        print({k: v for k, v in data_for_serializer.items() if k != 'audio_file'})
        if data_for_serializer.get('audio_file'): print("audio_file: [File Object]")
        print("------------------------------------------")

        # Validate dữ liệu bằng serializer, truyền instance cũ
        serializer = SongSerializer(song, data=data_for_serializer, partial=True, context={'request': request})

        if serializer.is_valid():
            update_data = serializer.validated_data
            new_audio_file = update_data.pop('audio_file', None)
            old_file_path = song.get('file_up')
            new_file_path = None
            file_path_to_save_in_db = old_file_path # Mặc định giữ cái cũ

            try:
                # 1. Xử lý file mới (nếu có)
                if new_audio_file:
                    # Tạo tên file mới và đường dẫn
                    original_filename, file_extension = os.path.splitext(new_audio_file.name); file_extension = file_extension.lower()
                    new_filename = f"{pk}{file_extension}" # Dùng pk (string _id)
                    relative_dir = 'audio'
                    new_file_path_relative = os.path.join(relative_dir, new_filename).replace("\\", "/")

                    # Xóa file cũ trước khi lưu file mới (nếu path cũ tồn tại)
                    if old_file_path and old_file_path != new_file_path_relative and default_storage.exists(old_file_path):
                        try: default_storage.delete(old_file_path); print(f"[PUT /songs/{pk}] Deleted old file: {old_file_path}")
                        except Exception as file_e: print(f"[PUT /songs/{pk}] Warning: Could not delete old file {old_file_path}: {file_e}")

                    # Lưu file mới (sẽ ghi đè nếu tên file đã tồn tại)
                    new_file_path = default_storage.save(new_file_path_relative, new_audio_file)
                    print(f"[PUT /songs/{pk}] Saved new file as: {new_file_path}")
                    file_path_to_save_in_db = new_file_path # Cập nhật path sẽ lưu vào DB

                # Cập nhật trường file_up trong data sẽ $set vào DB
                update_data['file_up'] = file_path_to_save_in_db

                # Chuyển đổi kiểu dữ liệu nếu cần (serializer đã làm)
                if 'release_time' in update_data and update_data['release_time']:
                    update_data['release_time'] = datetime.combine(update_data['release_time'], datetime.min.time())
                # artist_ids, album_id đã là ObjectId từ serializer

                # 2. Cập nhật document trong MongoDB ($set chỉ các trường thay đổi)
                if update_data: # Chỉ update nếu có dữ liệu thay đổi
                    db.songs.update_one({'_id': song_id}, {'$set': update_data})
                    print(f"[PUT /songs/{pk}] Updated song document")
                else:
                     print(f"[PUT /songs/{pk}] No data fields to update.")

                # 3. Fetch lại dữ liệu hoàn chỉnh để trả về
                pipeline_detail = [{'$match': {'_id': song_id}}] + self._get_pipeline_stages()
                updated_song_agg = list(db.songs.aggregate(pipeline_detail))

                if updated_song_agg:
                    response_serializer = SongSerializer(updated_song_agg[0], context={'request': request})
                    return Response(response_serializer.data)
                else:
                    # Rất hiếm, nhưng có thể xảy ra nếu document bị xóa ngay sau khi update?
                    return Response(status=status.HTTP_404_NOT_FOUND)

            except Exception as e:
                print(f"[PUT /songs/{pk}] Error during update/file handling: {e}")
                # Cân nhắc rollback file mới nếu update DB lỗi
                # if new_file_path and default_storage.exists(new_file_path): ...
                return Response({"error": f"Could not update song {pk}: {e}"}, status=500)
        else:
            print(f"[PUT /songs/{pk}] Serializer errors:", serializer.errors)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        """ Xóa bài hát và file media liên quan. """
        if not db: return Response({"error": "Database connection failed"}, status=500)
        song_id = None
        try: song_id = ObjectId(pk)
        except Exception: return Response({"error": "Invalid Song ID format"}, status=400)

        song = db.songs.find_one({'_id': song_id}) # Lấy path file trước khi xóa
        if song:
            try:
                file_path_to_delete = song.get('file_up')
                result = db.songs.delete_one({'_id': song_id}) # Xóa document

                if result.deleted_count == 1:
                    # Xóa file media nếu xóa DB thành công
                    if file_path_to_delete and default_storage.exists(file_path_to_delete):
                        try:
                            default_storage.delete(file_path_to_delete)
                            print(f"[DELETE /songs/{pk}] Deleted media file: {file_path_to_delete}")
                        except Exception as file_e:
                            print(f"[DELETE /songs/{pk}] Warning: Could not delete media file {file_path_to_delete}: {file_e}")
                    return Response(status=status.HTTP_204_NO_CONTENT)
                else:
                     return Response({"error": f"Could not delete song {pk} from DB"}, status=500)
            except Exception as e:
                 print(f"[DELETE /songs/{pk}] Error during deletion: {e}")
                 return Response({"error": f"Could not complete song deletion for {pk}"}, status=500)
        else:
            return Response(status=status.HTTP_404_NOT_FOUND) # Không tìm thấy bài hát

# --- Playlist Views ---
class PlaylistList(APIView):
     # TODO: Add permissions (IsAuthenticated?)
    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()] # Ai cũng xem được list
        # Các method khác (POST) sẽ dùng default (IsAdminFromMongo)
        return super().get_permissions()
    
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
    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()] # Ai cũng xem được list
        # Các method khác (POST) sẽ dùng default (IsAdminFromMongo)
        return super().get_permissions()
    
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
    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()] # Ai cũng xem được list
        # Các method khác (POST) sẽ dùng default (IsAdminFromMongo)
        return super().get_permissions()
    
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

class ArtistSelectView(APIView):
    """ Cung cấp danh sách Artist rút gọn cho select options. """
    # TODO: Thêm permission IsAdminUser?
    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()] # Ai cũng xem được list
        # Các method khác (POST) sẽ dùng default (IsAdminFromMongo)
        return super().get_permissions()
    
    def get(self, request):
        if not db: return Response({"error": "Database connection failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        try:
            # Chỉ lấy _id và artist_name, sắp xếp theo tên
            artists_cursor = db.artists.find({}, {'_id': 1, 'artist_name': 1}).sort('artist_name', 1)
            serializer = ArtistSelectSerializer(list(artists_cursor), many=True)
            return Response(serializer.data)
        except Exception as e:
            print(f"Error fetching artist options: {e}")
            return Response({"error": "Could not retrieve artist options"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class AlbumSelectView(APIView):
    """ Cung cấp danh sách Album rút gọn cho select options. """
    # TODO: Thêm permission IsAdminUser?
    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()] # Ai cũng xem được list
        # Các method khác (POST) sẽ dùng default (IsAdminFromMongo)
        return super().get_permissions()
    
    def get(self, request):
        if not db: return Response({"error": "Database connection failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        try:
            # Chỉ lấy _id và album_name, sắp xếp theo tên
            # Nếu muốn hiển thị cả tên Artist trong select, cần dùng $lookup ở đây
            albums_cursor = db.albums.find({}, {'_id': 1, 'album_name': 1}).sort('album_name', 1)
            # albums_list = []
            # for album in albums_cursor:
            #      artist = get_object(db.artists, str(album.get('artist_id')))
            #      album['artist_data'] = artist # Thêm data để serializer lấy tên
            #      albums_list.append(album)

            serializer = AlbumSelectSerializer(list(albums_cursor), many=True) # Hoặc albums_list
            return Response(serializer.data)
        except Exception as e:
            print(f"Error fetching album options: {e}")
            return Response({"error": "Could not retrieve album options"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)