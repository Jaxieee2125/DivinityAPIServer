# music_api/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from sklearn import pipeline
# Import các serializers đã cập nhật
from .serializers import (
    MusicGenreSerializer, UserSerializer, AdminSerializer,
    ArtistSerializer, AlbumSerializer, SongSerializer,
    PlaylistSerializer, AlbumSelectSerializer, ArtistSelectSerializer,
    MusicGenreSelectSerializer, UserRegistrationSerializer,
    UserSerializer, UserUpdateSerializer, ChangePasswordSerializer
)
from datetime import datetime, timezone
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
from django.contrib.auth.hashers import check_password # Để kiểm tra mật khẩu
from rest_framework.exceptions import ValidationError as DRFValidationError # Bắt lỗi validation
from math import ceil
import random
import os
import mimetypes # Để đoán content type
from wsgiref.util import FileWrapper # Để stream file hiệu quả
from django.http import HttpResponse, StreamingHttpResponse, Http404, HttpResponseNotModified, HttpResponseForbidden, HttpResponseServerError
from django.conf import settings
from django.utils.http import http_date, parse_etags, quote_etag
from django.utils.encoding import escape_uri_path
import stat # Để lấy thông tin file
import re


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
        # user_id ở đây là user_id từ collection 'admin', KHÔNG phải _id của admin document
        user_id_str = str(user_doc['_id']) # <<< Lấy _id của USER được liên kết với admin
        username = user_doc.get('username') # Username của admin

        try:
            refresh = RefreshToken()
            # --- Thêm claim vào REFRESH token ---
            # ID của USER liên kết với admin (không phải _id của admin document)
            refresh[settings.SIMPLE_JWT['USER_ID_CLAIM']] = user_id_str # Dùng setting USER_ID_CLAIM

            # --- Thêm claim vào ACCESS token ---
            access = refresh.access_token
            # ID của USER liên kết với admin
            access[settings.SIMPLE_JWT['USER_ID_CLAIM']] = user_id_str # Dùng setting USER_ID_CLAIM
            access['username'] = username # Username của admin
            access['is_staff'] = True     # <<< QUAN TRỌNG: Đánh dấu là admin
            access['is_active'] = True    # Giả sử admin luôn active khi đăng nhập được

            print(f"[_get_tokens_for_admin_user] Generated tokens for admin '{username}' linked to user_id '{user_id_str}'")

            return {
                'refresh': str(refresh),
                'access': str(access),
            }

        except Exception as e:
             print(f"Error creating tokens for admin {username}: {e}")
             raise e
        
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

class AdminStatsView(APIView):
    permission_classes = [IsAdminFromMongo] # Chỉ admin được xem thống kê

    def get(self, request):
        if not db: return Response({"error": "Database connection failed"}, 500)
        try:
            stats = {
                'total_songs': db.songs.count_documents({}),
                'total_artists': db.artists.count_documents({}),
                'total_albums': db.albums.count_documents({}),
                'total_users': db.users.count_documents({}),
                'total_genres': db.musicgenres.count_documents({}),
                'total_playlists': db.playlists.count_documents({}),
                # Thêm các thống kê khác nếu muốn (vd: active users)
                # 'active_users': db.users.count_documents({'is_active': True}),
            }
            return Response(stats)
        except Exception as e:
            print(f"Error fetching admin stats: {e}")
            return Response({"error": "Could not retrieve statistics"}, 500)

# --- VIEW ĐĂNG KÝ TÀI KHOẢN USER ---
# ------------------------------------------
class UserRegistrationView(APIView):
    """
    Endpoint cho phép người dùng mới đăng ký tài khoản.
    Bất kỳ ai cũng có thể truy cập (AllowAny).
    """
    permission_classes = [AllowAny]     # Rất quan trọng!
    authentication_classes = []         # Không yêu cầu xác thực cho view này

    def post(self, request, *args, **kwargs):
        print("[UserRegistrationView] Received POST request.")

        if not db:
            print("[UserRegistrationView] ERROR: Database connection is not available.")
            return Response(
                {"error": "Lỗi hệ thống: Không thể kết nối cơ sở dữ liệu."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        # Tạo serializer, truyền request.data và context chứa db
        serializer = UserRegistrationSerializer(data=request.data, context={'db': db})

        if serializer.is_valid():
            print("[UserRegistrationView] Serializer is valid. Attempting to save user...")
            try:
                # Hàm save() sẽ gọi hàm create() trong serializer
                created_user_data = serializer.save()
                print(f"[UserRegistrationView] User '{created_user_data.get('username')}' created successfully.")
                # Chỉ trả về thông báo thành công, không lộ thông tin user vừa tạo
                return Response(
                    {"message": "Đăng ký tài khoản thành công!"},
                    status=status.HTTP_201_CREATED
                )
            except DRFValidationError as e:
                # Bắt lỗi Validation được raise từ hàm create (ví dụ: lỗi ghi DB)
                print(f"[UserRegistrationView] ERROR during save (ValidationError): {e.detail}")
                error_detail = e.detail if isinstance(e.detail, dict) else {"error": str(e)}
                return Response(error_detail, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            except Exception as e:
                 # Các lỗi không mong muốn khác trong quá trình lưu
                 print(f"[UserRegistrationView] ERROR during save (Unexpected Exception): {e}")
                 return Response(
                     {"error": "Đã xảy ra lỗi không mong muốn trong quá trình đăng ký."},
                     status=status.HTTP_500_INTERNAL_SERVER_ERROR
                 )
        else:
            # Dữ liệu đầu vào không hợp lệ (thiếu trường, sai định dạng, username/email đã tồn tại,...)
            print(f"[UserRegistrationView] Serializer is invalid. Errors: {serializer.errors}")
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# ------------------------------------------
# --- VIEW ĐĂNG NHẬP TÀI KHOẢN USER ---
# ------------------------------------------
class UserLoginView(APIView):
    """
    Endpoint cho phép người dùng thường đăng nhập bằng username/email và password.
    Bất kỳ ai cũng có thể truy cập (AllowAny).
    Trả về access token, refresh token và thông tin cơ bản của user.
    """
    permission_classes = [AllowAny]     # Rất quan trọng!
    authentication_classes = []         # Không yêu cầu xác thực cho view này

    @staticmethod
    def _generate_tokens_for_user(user_doc):
        """ Helper tạo JWT access và refresh tokens cho user document từ MongoDB. """
        print(f"[_generate_tokens_for_user] Generating tokens for user: {user_doc.get('username')}")
        try:
            refresh = RefreshToken() # Tạo refresh token mới

            # Lấy các thông tin cần thiết từ user document
            user_id_str = str(user_doc['_id'])
            username = user_doc.get('username')
            is_staff = user_doc.get('is_staff', False) # Mặc định False
            is_active = user_doc.get('is_active', True) # Mặc định True
            email = user_doc.get('email')

            # Thêm các claims (thông tin) vào payload của token
            # Quan trọng: Chỉ thêm những thông tin không nhạy cảm và cần thiết
            refresh['user_mongo_id'] = user_id_str # Định danh user trong DB Mongo

            # Access token thường chứa nhiều thông tin hơn để kiểm tra nhanh
            access = refresh.access_token
            access['username'] = username
            access['email'] = email
            access['is_staff'] = is_staff
            access['is_active'] = is_active
            # Thêm các claims khác nếu cần (vd: vai trò, quyền hạn cụ thể)

            print(f"[_generate_tokens_for_user] Tokens generated successfully for {username}")
            return {'refresh': str(refresh), 'access': str(access)}
        except Exception as e:
            print(f"ERROR [_generate_tokens_for_user] Failed to create tokens for {user_doc.get('username', 'UNKNOWN')}: {e}")
            # Ném lỗi ra ngoài để phương thức post xử lý và trả về lỗi 500
            raise Exception("Token generation failed")

    def post(self, request, *args, **kwargs):
        print("[UserLoginView] Received POST request.")

        if not db:
            print("[UserLoginView] ERROR: Database connection is not available.")
            return Response(
                {"error": "Lỗi hệ thống: Không thể kết nối cơ sở dữ liệu."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        # Lấy thông tin đăng nhập từ body của request
        identifier = request.data.get('identifier') # Frontend sẽ gửi username hoặc email qua field này
        password = request.data.get('password')

        # Kiểm tra xem có đủ thông tin không
        if not identifier or not password:
            print("[UserLoginView] Missing identifier or password in request.")
            return Response(
                {"error": "Vui lòng cung cấp tên đăng nhập (hoặc email) và mật khẩu."},
                status=status.HTTP_400_BAD_REQUEST
            )

        print(f"[UserLoginView] Attempting login for identifier: '{identifier}'")

        # Tìm kiếm user trong collection 'users' bằng username hoặc email
        try:
            users_collection = db.users
            user_doc = users_collection.find_one({
                '$or': [
                    {'username': identifier},
                    {'email': identifier}
                ]
            })
        except Exception as e:
            print(f"[UserLoginView] ERROR during database find_one: {e}")
            return Response(
                {"error": "Lỗi truy vấn cơ sở dữ liệu."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        # --- Xử lý kết quả tìm kiếm ---
        if user_doc:
            print(f"[UserLoginView] User document found for identifier '{identifier}': username='{user_doc.get('username')}'")
            stored_password_hash = user_doc.get('password') # Lấy mật khẩu đã hash từ DB

            # 1. Kiểm tra mật khẩu
            if stored_password_hash and check_password(password, stored_password_hash):
                print(f"[UserLoginView] Password for '{identifier}' is valid.")

                # 2. Kiểm tra tài khoản có active không
                if not user_doc.get('is_active', True):
                     print(f"[UserLoginView] Login failed - inactive user: '{identifier}'")
                     # Trả về lỗi 401 nhưng với thông báo cụ thể hơn (tùy chọn)
                     return Response({"detail": "Tài khoản này hiện đang bị khóa."}, status=status.HTTP_401_UNAUTHORIZED)

                # 3. Mật khẩu đúng và tài khoản active -> Tạo Tokens
                try:
                    tokens = self._generate_tokens_for_user(user_doc)
                    print(f"[UserLoginView] Login successful for '{identifier}'.")

                    # Chuẩn bị thông tin user cơ bản để trả về (không bao gồm password)
                    user_info = {
                        'id': str(user_doc['_id']),
                        'username': user_doc.get('username'),
                        'email': user_doc.get('email'),
                        'is_staff': user_doc.get('is_staff', False),
                        # Thêm các trường khác nếu frontend cần (vd: tên, ảnh đại diện url...)
                    }
                    # Trả về tokens và thông tin user
                    return Response({**tokens, "user": user_info}, status=status.HTTP_200_OK)

                except Exception as token_e:
                     # Bắt lỗi từ hàm _generate_tokens_for_user
                     print(f"[UserLoginView] ERROR during token generation for '{identifier}': {token_e}")
                     return Response({"detail": "Đã xảy ra lỗi trong quá trình tạo mã xác thực."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            else:
                # Sai mật khẩu
                print(f"[UserLoginView] Login failed - invalid password for: '{identifier}'")
                # Trả về lỗi chung chung để bảo mật
                return Response({"detail": "Tên đăng nhập hoặc mật khẩu không chính xác."}, status=status.HTTP_401_UNAUTHORIZED)
        else:
            # Không tìm thấy user với identifier cung cấp
            print(f"[UserLoginView] Login failed - user not found for identifier: '{identifier}'")
            # Trả về lỗi chung chung
            return Response({"detail": "Tên đăng nhập hoặc mật khẩu không chính xác."}, status=status.HTTP_401_UNAUTHORIZED)
# --- MusicGenre Views ---
class MusicGenreList(APIView):
    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()] # Ai cũng xem được list
        # Các method khác (POST) sẽ dùng default (IsAdminFromMongo)
        return super().get_permissions()
    
    def get(self, request):
        if not db: return Response({"error": "Database connection failed"}, 500)

        query_params = request.query_params
        mongo_filter = {}

        # --- KIỂM TRA LOGIC LỌC THEO _id ---
        genre_id_param = query_params.get('_id')
        if genre_id_param:
            try:
                mongo_filter['_id'] = ObjectId(genre_id_param)
                print(f"Filtering musicgenres by _id: {mongo_filter['_id']}") # DEBUG
            except Exception:
                return Response({"error": f"Invalid _id format: {genre_id_param}"}, status=400)
        # ---------------------------------

        # Sắp xếp nếu có
        sort_field = query_params.get('sort', 'musicgenre_name')
        sort_order_str = query_params.get('order', 'asc').lower()
        sort_order = 1 if sort_order_str == 'asc' else -1

        try:
            # Áp dụng filter và sort
            genres_cursor = db.musicgenres.find(mongo_filter).sort(sort_field, sort_order)
            # Nếu dùng pagination, cần thêm limit, skip và count
            genres_list = list(genres_cursor)

            # Nếu đây là request chỉ lấy 1 genre theo ID, trả về object thay vì mảng
            if genre_id_param and len(genres_list) == 1:
                 serializer = MusicGenreSerializer(genres_list[0], context={'request': request})
                 return Response(serializer.data) # Trả về object
            elif genre_id_param and not genres_list:
                 return Response({"detail": "Not found."}, status=404)


            # Mặc định trả về list cho /api/musicgenres/ (không có _id param)
            serializer = MusicGenreSerializer(genres_list, many=True, context={'request': request})
            # Cần cấu trúc response có "results" nếu frontend dùng pagination
            return Response({"results": serializer.data, "count": len(genres_list)})
        except Exception as e:
            print(f"Error fetching music genres: {e}")
            return Response({"error": "Could not retrieve music genres"}, status=500)

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


def get_object(collection, pk_str):
    if not db: return None
    try: return collection.find_one({'_id': ObjectId(pk_str)})
    except: return None

# --- User Views (CRUD cho Admin) ---

class UserList(APIView):
    """ API endpoint để admin lấy danh sách hoặc tạo user mới. """
    permission_classes = [IsAdminFromMongo] # Chỉ admin được truy cập

    def get(self, request):
        """ Lấy danh sách tất cả người dùng. """
        if not db: return Response({"error": "Database connection failed"}, 500)
        try:
            # TODO: Thêm pagination
            # Loại bỏ trường password khi fetch
            users_cursor = db.users.find({}, {'password': 0})
            serializer = UserSerializer(list(users_cursor), many=True, context={'request': request})
            return Response(serializer.data)
        except Exception as e:
            print(f"[GET /users/] Error: {e}")
            return Response({"error": "Could not retrieve users"}, 500)

    def post(self, request):
        """ Admin tạo user mới. """
        if not db: return Response({"error": "Database connection failed"}, 500)

        # Chuẩn bị dữ liệu (tương tự Song/Artist)
        mutable_post_data = request.POST.copy()
        data_for_serializer = mutable_post_data.dict()
        if 'profile_picture' in request.FILES:
            data_for_serializer['profile_picture'] = request.FILES['profile_picture']
        else:
            data_for_serializer['profile_picture'] = None

        # Serializer sẽ validate username/email trùng, required fields
        serializer = UserSerializer(data=data_for_serializer, context={'request': request})

        if serializer.is_valid():
            user_data = serializer.validated_data
            profile_picture_file = user_data.pop('profile_picture', None)
            password = user_data.pop('password', None) # Lấy password ra

            # --- BẮT BUỘC CÓ PASSWORD KHI TẠO MỚI ---
            if not password:
                 return Response({"password": ["Password is required for new users."]}, status=status.HTTP_400_BAD_REQUEST)
            # -----------------------------------------

            saved_picture_path = None
            new_user_id = None

            try:
                # 1. Hash password
                user_data['password'] = make_password(password)
                # Mặc định is_staff=False, is_active=True (có thể cho phép admin set)
                user_data['is_staff'] = user_data.get('is_staff', False) # Ví dụ nếu cho phép set
                user_data['is_active'] = user_data.get('is_active', True)
                if 'date_of_birth' in user_data and user_data['date_of_birth']:
                     user_data['date_of_birth'] = datetime.combine(user_data['date_of_birth'], datetime.min.time())
                else: user_data['date_of_birth'] = None

                # 2. Insert document user (chưa có path ảnh)
                insert_result = db.users.insert_one(user_data)
                new_user_id = insert_result.inserted_id
                print(f"[POST User] Created initial user doc: {new_user_id}")

                # 3. Lưu ảnh profile nếu có
                if profile_picture_file and new_user_id:
                    original_filename, file_extension = os.path.splitext(profile_picture_file.name); file_extension = file_extension.lower()
                    new_filename = f"{str(new_user_id)}{file_extension}"
                    relative_dir = os.path.join('users', 'avatars').replace("\\", "/")
                    saved_picture_path_relative = os.path.join(relative_dir, new_filename).replace("\\", "/")
                    saved_picture_path = default_storage.save(saved_picture_path_relative, profile_picture_file)
                    print(f"[POST User] Saved avatar as: {saved_picture_path}")

                    # 4. Cập nhật document với path ảnh
                    db.users.update_one( {'_id': new_user_id}, {'$set': {'profile_picture': saved_picture_path}} )
                    print(f"[POST User] Updated doc {new_user_id} with avatar path: {saved_picture_path}")
                else: saved_picture_path = None

                # 5. Fetch lại dữ liệu (loại bỏ password) và trả về
                created_user_doc = db.users.find_one({'_id': new_user_id}, {'password': 0})
                if created_user_doc:
                     response_serializer = UserSerializer(created_user_doc, context={'request': request})
                     return Response(response_serializer.data, status=status.HTTP_201_CREATED)
                else: raise Exception("Could not retrieve created user.")

            except Exception as e:
                 # Rollback
                 print(f"[POST User] Error: {e}")
                 if new_user_id: db.users.delete_one({'_id': new_user_id}); print(f"Rolled back user doc {new_user_id}")
                 if saved_picture_path and default_storage.exists(saved_picture_path): default_storage.delete(saved_picture_path); print(f"Rolled back avatar file {saved_picture_path}")
                 return Response({"error": f"Could not create user: {e}"}, status=500)
        else:
            print("[POST User] Serializer Errors:", serializer.errors)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserDetail(APIView):
    """ API endpoint để admin,user lấy, sửa, xóa thông tin user. """
    permission_classes = [IsAuthenticated] #  admin, user đều có thể xem thông tin của mình

    def get(self, request, pk):
        """ Lấy chi tiết user (không bao gồm password). """
        if not db: return Response({"error": "Database connection failed"}, 500)
        user = get_object(db.users, pk)
        if user:
            # Loại bỏ password trước khi serialize
            user.pop('password', None)
            serializer = UserSerializer(user, context={'request': request})
            return Response(serializer.data)
        return Response(status=status.HTTP_404_NOT_FOUND)

    def put(self, request, pk):
        """ Cập nhật thông tin user. """
        if not db: return Response({"error": "Database connection failed"}, 500)

        user_id = None
        try: user_id = ObjectId(pk)
        except Exception: return Response({"error": "Invalid User ID format"}, 400)

        user = db.users.find_one({'_id': user_id})
        if not user: return Response(status=status.HTTP_404_NOT_FOUND)

        # Chuẩn bị dữ liệu
        mutable_post_data = request.POST.copy()
        data_for_serializer = mutable_post_data.dict()
        if 'profile_picture' in request.FILES:
            data_for_serializer['profile_picture'] = request.FILES['profile_picture']

        # Truyền instance cũ để serializer biết là update
        serializer = UserSerializer(user, data=data_for_serializer, partial=True, context={'request': request})

        if serializer.is_valid():
            update_data = serializer.validated_data
            new_picture_file = update_data.pop('profile_picture', None)
            new_password = update_data.pop('password', None) # Lấy password mới (nếu có)
            old_picture_path = user.get('profile_picture')
            new_picture_path = None
            picture_path_to_save = old_picture_path

            try:
                # 1. Xử lý ảnh profile mới (nếu có)
                if new_picture_file:
                    # ... (Logic xóa file cũ, lưu file mới, cập nhật picture_path_to_save tương tự Album/Artist) ...
                    original_filename, file_extension = os.path.splitext(new_picture_file.name); file_extension = file_extension.lower()
                    new_filename = f"{pk}{file_extension}"; relative_dir = os.path.join('users', 'avatars').replace("\\","/")
                    new_picture_path_relative = os.path.join(relative_dir, new_filename).replace("\\","/")
                    if old_picture_path and old_picture_path != new_picture_path_relative and default_storage.exists(old_picture_path):
                        try: default_storage.delete(old_picture_path); print(f"[PUT User/{pk}] Deleted old picture")
                        except Exception as file_e: print(f"Warning: Could not delete old picture {old_picture_path}: {file_e}")
                    new_picture_path = default_storage.save(new_picture_path_relative, new_picture_file); print(f"[PUT User/{pk}] Saved new picture as: {new_picture_path}")
                    picture_path_to_save = new_picture_path

                update_data['profile_picture'] = picture_path_to_save # Cập nhật path vào data

                # 2. Hash password mới nếu có
                if new_password:
                    update_data['password'] = make_password(new_password)
                # Else: không cập nhật password

                # 3. Chuyển đổi kiểu dữ liệu khác nếu cần
                if 'date_of_birth' in update_data and update_data['date_of_birth']:
                    update_data['date_of_birth'] = datetime.combine(update_data['date_of_birth'], datetime.min.time())
                elif 'date_of_birth' in update_data: update_data['date_of_birth'] = None

                # 4. Cập nhật MongoDB
                if update_data:
                    db.users.update_one({'_id': user_id}, {'$set': update_data})
                    print(f"[PUT User/{pk}] Updated user document")
                else: print(f"[PUT User/{pk}] No data fields to update.")

                # 5. Fetch lại dữ liệu (bỏ password) và trả về
                updated_user_doc = db.users.find_one({'_id': user_id}, {'password': 0})
                if updated_user_doc:
                    response_serializer = UserSerializer(updated_user_doc, context={'request': request})
                    return Response(response_serializer.data)
                else: return Response(status=status.HTTP_404_NOT_FOUND)

            except Exception as e:
                print(f"[PUT User/{pk}] Error: {e}")
                # Cân nhắc rollback file mới
                return Response({"error": f"Could not update user {pk}: {e}"}, 500)
        else:
            print(f"[PUT User/{pk}] Serializer Errors:", serializer.errors)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        """ Xóa user và ảnh profile liên quan. """
        if not db: return Response({"error": "Database connection failed"}, 500)
        user_id = None
        try: user_id = ObjectId(pk)
        except Exception: return Response({"error": "Invalid User ID format"}, 400)

        user = db.users.find_one({'_id': user_id})
        if user:
            try:
                picture_path_to_delete = user.get('profile_picture')
                # TODO: Cân nhắc xóa các bản ghi liên quan khác (ví dụ: trong collection 'admin' nếu user này là admin?)
                # result_admin = db.admin.delete_many({'user_id': user_id})
                # print(f"Deleted {result_admin.deleted_count} admin records for user {pk}")

                result = db.users.delete_one({'_id': user_id}) # Xóa user

                if result.deleted_count == 1:
                    # Xóa ảnh profile
                    if picture_path_to_delete and default_storage.exists(picture_path_to_delete):
                        try:
                            default_storage.delete(picture_path_to_delete)
                            print(f"[DELETE User/{pk}] Deleted profile picture: {picture_path_to_delete}")
                        except Exception as file_e:
                            print(f"[DELETE User/{pk}] Warning: Could not delete profile picture {picture_path_to_delete}: {file_e}")
                    return Response(status=status.HTTP_204_NO_CONTENT)
                else: return Response({"error": f"Could not delete user {pk} from DB"}, 500)
            except Exception as e:
                 print(f"[DELETE User/{pk}] Error: {e}")
                 return Response({"error": f"Could not complete user deletion for {pk}"}, 500)
        else:
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
        """ Tạo nghệ sĩ mới, xử lý upload avatar. """
        if not db: return Response({"error": "Database connection failed"}, status=500)

        # Xử lý dữ liệu đầu vào
        mutable_post_data = request.POST.copy()
        data_for_serializer = mutable_post_data.dict()

        # Xử lý musicgenre_ids
        if 'musicgenre_ids' in mutable_post_data:
            genre_id_list_str = mutable_post_data.getlist('musicgenre_ids')
            valid_genre_ids = []
            for gid_str in genre_id_list_str:
                gid_str = gid_str.strip()
                if not gid_str: continue
                try: valid_genre_ids.append(ObjectId(gid_str))
                except Exception: return Response({"musicgenre_ids": [f"Invalid ObjectId format: '{gid_str}'"]}, status=400)
            data_for_serializer['musicgenre_ids'] = valid_genre_ids
        else:
             data_for_serializer['musicgenre_ids'] = [] # Đảm bảo là list rỗng nếu không gửi

        # Thêm file vào data cho serializer validate
        if 'artist_avatar' in request.FILES:
            data_for_serializer['artist_avatar'] = request.FILES['artist_avatar']
        else:
            data_for_serializer['artist_avatar'] = None # Hoặc bỏ key này nếu field không bắt buộc

        print("--- [POST Artist] Data for Serializer ---")
        print({k: v for k, v in data_for_serializer.items() if k != 'artist_avatar'})
        if data_for_serializer.get('artist_avatar'): print("artist_avatar: [File Object]")
        print("--------------------------------------")

        serializer = ArtistSerializer(data=data_for_serializer, context={'request': request})

        if serializer.is_valid():
            artist_data = serializer.validated_data
            avatar_file = artist_data.pop('artist_avatar', None)

            saved_avatar_path = None
            new_artist_id = None

            try:
                # 1. Insert document artist (chưa có avatar path) để lấy ID
                mongo_data = {k: v for k, v in artist_data.items()}
                if 'date_of_birth' in mongo_data and mongo_data['date_of_birth']:
                    mongo_data['date_of_birth'] = datetime.combine(mongo_data['date_of_birth'], datetime.min.time())
                else: mongo_data['date_of_birth'] = None

                # Đảm bảo genre_ids là list ObjectId (serializer đã validate)
                # mongo_data['musicgenre_ids'] = [ObjectId(gid) for gid in mongo_data.get('musicgenre_ids', [])]

                insert_result = db.artists.insert_one(mongo_data)
                new_artist_id = insert_result.inserted_id
                print(f"[POST Artist] Created initial artist doc: {new_artist_id}")

                # 2. Lưu avatar nếu có
                if avatar_file and new_artist_id:
                    original_filename, file_extension = os.path.splitext(avatar_file.name)
                    file_extension = file_extension.lower()
                    new_filename = f"{str(new_artist_id)}{file_extension}"
                    relative_dir = os.path.join('artists', 'avatars').replace("\\","/")
                    saved_avatar_path_relative = os.path.join(relative_dir, new_filename).replace("\\", "/")

                    saved_avatar_path = default_storage.save(saved_avatar_path_relative, avatar_file)
                    print(f"[POST Artist] Saved avatar as: {saved_avatar_path}")

                    # 3. Cập nhật document với avatar path
                    db.artists.update_one(
                        {'_id': new_artist_id},
                        {'$set': {'artist_avatar': saved_avatar_path}} # Lưu path tương đối trả về
                    )
                    print(f"[POST Artist] Updated doc {new_artist_id} with avatar path: {saved_avatar_path}")
                else:
                    saved_avatar_path = None

                # 4. Fetch lại và trả về response
                created_artist_doc = db.artists.find_one({'_id': new_artist_id})
                if created_artist_doc:
                     response_serializer = ArtistSerializer(created_artist_doc, context={'request': request})
                     return Response(response_serializer.data, status=status.HTTP_201_CREATED)
                else: raise Exception("Could not retrieve created artist.")

            except Exception as e:
                 # Rollback
                 print(f"[POST Artist] Error: {e}")
                 if new_artist_id: db.artists.delete_one({'_id': new_artist_id}); print(f"Rolled back artist doc {new_artist_id}")
                 if saved_avatar_path and default_storage.exists(saved_avatar_path): default_storage.delete(saved_avatar_path); print(f"Rolled back avatar file {saved_avatar_path}")
                 return Response({"error": f"Could not create artist: {e}"}, status=500)
        else:
            print("[POST Artist] Serializer Errors:", serializer.errors)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ArtistDetail(APIView):
    permission_classes = [AllowAny] # Ai cũng có thể xem chi tiết nghệ sĩ

    def get(self, request, pk):
        """ Lấy chi tiết nghệ sĩ, có thể kèm thông tin tổng hợp. """
        if not db: return Response({"error": "Database connection failed"}, 500)
        artist_id = None
        try:
            artist_id = ObjectId(pk)
        except Exception:
            return Response({"error": "Invalid Artist ID format"}, status=400)

        try:
            artist = db.artists.find_one({'_id': artist_id})
            if not artist:
                return Response(status=status.HTTP_404_NOT_FOUND)

            # --- Tính toán thông tin tổng hợp (Ví dụ) ---
            # Cách 1: Đếm trực tiếp (Có thể chậm nếu dữ liệu lớn)
            total_albums = db.albums.count_documents({'artist_id': artist_id})
            total_tracks = db.songs.count_documents({'artist_ids': artist_id}) # Tìm trong mảng artist_ids

            # Cách 2: Dùng Aggregation để tính tổng lượt nghe (Hiệu quả hơn nếu cần tính tổng)
            # pipeline_plays = [
            #     {'$match': {'artist_ids': artist_id}},
            #     {'$group': {'_id': None, 'total_plays': {'$sum': '$number_of_plays'}}}
            # ]
            # play_result = list(db.songs.aggregate(pipeline_plays))
            # total_plays = play_result[0]['total_plays'] if play_result else 0

            # Gán các giá trị tính toán vào dict để serializer có thể dùng (nếu cần)
            # Hoặc serializer tự xử lý các trường read_only này
            artist['total_albums'] = total_albums
            artist['total_tracks'] = total_tracks
            # artist['total_plays'] = total_plays # Nếu tính
            # -----------------------------------------

            # Truyền context để tạo URL avatar
            serializer = ArtistSerializer(artist, context={'request': request})
            return Response(serializer.data)

        except Exception as e:
            print(f"[GET /artists/{pk}] Error: {e}")
            return Response({"error": f"Could not retrieve artist {pk}"}, 500)

    def put(self, request, pk):
        """ Cập nhật thông tin nghệ sĩ, bao gồm cả avatar. """
        if not db: return Response({"error": "Database connection failed"}, status=500)

        artist_id = None
        try: artist_id = ObjectId(pk)
        except Exception: return Response({"error": "Invalid Artist ID format"}, status=400)

        artist = db.artists.find_one({'_id': artist_id}) # Lấy dữ liệu hiện tại
        if not artist: return Response(status=status.HTTP_404_NOT_FOUND)

        # --- Xử lý dữ liệu đầu vào cho PUT ---
        mutable_post_data = request.POST.copy()
        data_for_serializer = mutable_post_data.dict()

        # Xử lý musicgenre_ids nếu được gửi lên
        if 'musicgenre_ids' in mutable_post_data:
            genre_id_list_str = mutable_post_data.getlist('musicgenre_ids')
            valid_genre_ids = []
            for gid_str in genre_id_list_str:
                gid_str = gid_str.strip()
                if not gid_str: continue
                try: valid_genre_ids.append(ObjectId(gid_str))
                except Exception: return Response({"musicgenre_ids": [f"Invalid ObjectId format: '{gid_str}'"]}, status=400)
            # Cho phép gửi mảng rỗng để xóa hết genres
            data_for_serializer['musicgenre_ids'] = valid_genre_ids

        # Thêm file nếu có
        if 'artist_avatar' in request.FILES:
            data_for_serializer['artist_avatar'] = request.FILES['artist_avatar']
        # Không cần else, nếu không có file thì serializer sẽ bỏ qua

        print(f"--- [PUT Artist/{pk}] Data for Serializer ---")
        print({k: v for k, v in data_for_serializer.items() if k != 'artist_avatar'})
        if data_for_serializer.get('artist_avatar'): print("artist_avatar: [File Object]")
        print("------------------------------------------")

        serializer = ArtistSerializer(artist, data=data_for_serializer, partial=True, context={'request': request})

        if serializer.is_valid():
            update_data = serializer.validated_data
            new_avatar_file = update_data.pop('artist_avatar', None)
            old_avatar_path = artist.get('artist_avatar')
            new_avatar_path = None
            avatar_path_to_save_in_db = old_avatar_path # Mặc định giữ path cũ

            try:
                # 1. Xử lý avatar mới (nếu có)
                if new_avatar_file:
                    # Tạo tên file và đường dẫn
                    original_filename, file_extension = os.path.splitext(new_avatar_file.name)
                    file_extension = file_extension.lower()
                    new_filename = f"{pk}{file_extension}" # Dùng pk (string _id)
                    relative_dir = os.path.join('artists', 'avatars').replace("\\", "/")
                    new_avatar_path_relative = os.path.join(relative_dir, new_filename).replace("\\", "/")

                    # Xóa file cũ trước khi lưu file mới (nếu có và khác tên)
                    if old_avatar_path and old_avatar_path != new_avatar_path_relative and default_storage.exists(old_avatar_path):
                        try: default_storage.delete(old_avatar_path); print(f"[PUT Artist/{pk}] Deleted old avatar: {old_avatar_path}")
                        except Exception as file_e: print(f"[PUT Artist/{pk}] Warning: Could not delete old avatar {old_avatar_path}: {file_e}")

                    # Lưu file mới
                    new_avatar_path = default_storage.save(new_avatar_path_relative, new_avatar_file)
                    print(f"[PUT Artist/{pk}] Saved new avatar as: {new_avatar_path}")
                    avatar_path_to_save_in_db = new_avatar_path # Cập nhật path sẽ lưu

                # Cập nhật trường artist_avatar trong data sẽ $set
                update_data['artist_avatar'] = avatar_path_to_save_in_db

                # Chuyển đổi kiểu dữ liệu nếu cần (serializer đã làm)
                if 'date_of_birth' in update_data and update_data['date_of_birth']:
                    update_data['date_of_birth'] = datetime.combine(update_data['date_of_birth'], datetime.min.time())
                elif 'date_of_birth' in update_data: update_data['date_of_birth'] = None # Cho phép xóa

                # 2. Cập nhật document trong MongoDB
                if update_data: # Chỉ update nếu có trường thay đổi
                    db.artists.update_one({'_id': artist_id}, {'$set': update_data})
                    print(f"[PUT Artist/{pk}] Updated artist document")
                else:
                    print(f"[PUT Artist/{pk}] No data fields to update.")

                # 3. Fetch lại dữ liệu hoàn chỉnh để trả về
                updated_artist_doc = db.artists.find_one({'_id': artist_id})
                if updated_artist_doc:
                    response_serializer = ArtistSerializer(updated_artist_doc, context={'request': request})
                    return Response(response_serializer.data)
                else:
                    return Response(status=status.HTTP_404_NOT_FOUND)

            except Exception as e:
                print(f"[PUT Artist/{pk}] Error during update/file handling: {e}")
                # Cân nhắc rollback file mới nếu update DB lỗi
                return Response({"error": f"Could not update artist {pk}: {e}"}, status=500)
        else:
            print(f"[PUT Artist/{pk}] Serializer Errors:", serializer.errors)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
         # TODO: Add permission checks?
         # TODO: Xử lý xóa file 'artist_avatar' trên storage
        result = db.artists.delete_one({'_id': ObjectId(pk)})
        if result.deleted_count == 1:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(status=status.HTTP_404_NOT_FOUND)


# --- Aggregation Pipeline Helper cho Album (Lấy Artist lồng nhau) ---
def get_album_aggregation_pipeline():
    return [
        { '$lookup': {
            'from': 'artists', # Tên collection artists
            'localField': 'artist_id',
            'foreignField': '_id',
            'as': 'artist_details'
        }},
        { '$unwind': { # Giả sử mỗi album chỉ có 1 artist
            'path': '$artist_details',
            'preserveNullAndEmptyArrays': True # Giữ album nếu không tìm thấy artist
        }},
        { '$project': {
            '_id': 1, 'album_name': 1, 'release_time': 1, 'description': 1,
            'image': 1, # Giữ lại path gốc để serializer tạo URL
            'artist_id': 1, # Giữ lại ID gốc
            'number_of_songs': 1, 'number_of_plays': 1, 'number_of_likes': 1, # Nếu các trường này có trong DB
            # Tạo trường artist lồng nhau
            'artist': { '$cond': {
                'if': '$artist_details',
                'then': {
                    '_id': '$artist_details._id',
                    'artist_name': '$artist_details.artist_name',
                    'artist_avatar': '$artist_details.artist_avatar' # Cho ArtistBasicSerializer
                 },
                'else': None
            }}
        }}
    ]

# --- Views cho Select Options ---
class ArtistSelectView(APIView): 
    permission_classes = [IsAdminFromMongo] # Chỉ admin mới cần lấy list này?
    def get(self, request):
        if not db: return Response({"error": "Database connection failed"}, 500)
        try:
            artists = list(db.artists.find({}, {'_id': 1, 'artist_name': 1}).sort('artist_name', 1))
            serializer = ArtistSelectSerializer(artists, many=True) # Sử dụng ArtistSelectSerializer
            return Response(serializer.data)
        except Exception as e: return Response({"error": f"Could not retrieve artist options: {e}"}, 500)


# --- >>> THÊM VIEW NÀY <<< ---
class AlbumSelectView(APIView):
    """ Cung cấp danh sách Album rút gọn cho select options. """
    permission_classes = [IsAdminFromMongo] # Chỉ admin?
    def get(self, request):
        if not db: return Response({"error": "Database connection failed"}, status=500)
        try:
            # Chỉ lấy _id và album_name, sắp xếp theo tên
            # Nếu cần tên artist: pipeline = [{ '$lookup': ... }, {'$project':{...}}]
            albums_cursor = db.albums.find({}, {'_id': 1, 'album_name': 1}).sort('album_name', 1)
            serializer = AlbumSelectSerializer(list(albums_cursor), many=True)
            return Response(serializer.data)
        except Exception as e:
            print(f"Error fetching album options: {e}")
            return Response({"error": "Could not retrieve album options"}, status=500)
# ----------------------------

# --- Album Views ---

class AlbumList(APIView):
    _get_pipeline_stages = staticmethod(get_album_aggregation_pipeline)

    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()] # Ai cũng có thể xem danh sách album
        return [IsAdminFromMongo()] # Chỉ admin được tạo album

    def get(self, request):
        """ Lấy danh sách album với thông tin artist lồng nhau. """
        if not db: return Response({"error": "Database connection failed"}, 500)
        try:
            pipeline = self._get_pipeline_stages()
            pipeline.append({'$sort': {'album_name': 1}})
            # TODO: Add pagination ($skip, $limit)
            albums_list = list(db.albums.aggregate(pipeline))
            serializer = AlbumSerializer(albums_list, many=True, context={'request': request})
            return Response(serializer.data)
        except Exception as e:
            print(f"[GET /albums/] Error: {e}")
            return Response({"error": "Could not retrieve albums"}, 500)

    def post(self, request):
        """ Tạo album mới, xử lý upload ảnh bìa. """
        if not db: return Response({"error": "Database connection failed"}, 500)

        # Chuẩn bị dữ liệu cho serializer (kết hợp text và file)
        data_for_serializer = request.data.copy() # Dùng request.data vì có thể là multipart

        # Kiểm tra và thêm file nếu có
        if 'image' in request.FILES:
            data_for_serializer['image'] = request.FILES['image']
        else:
            # Nếu field 'image' là bắt buộc trong serializer, lỗi sẽ xảy ra ở is_valid()
             data_for_serializer['image'] = None # Đặt là None nếu không bắt buộc

        print("--- [POST Album] Data for Serializer ---")
        print({k: v for k, v in data_for_serializer.items() if k != 'image'})
        if data_for_serializer.get('image'): print("image: [File Object]")
        print("--------------------------------------")

        serializer = AlbumSerializer(data=data_for_serializer, context={'request': request})

        if serializer.is_valid():
            album_data = serializer.validated_data
            image_file = album_data.pop('image', None) # Lấy file ra

            saved_image_path = None
            new_album_id = None

            try:
                # 1. Insert document album (chưa có image path) để lấy ID
                mongo_data = {k: v for k, v in album_data.items()}
                if 'release_time' in mongo_data and mongo_data['release_time']:
                    mongo_data['release_time'] = datetime.combine(mongo_data['release_time'], datetime.min.time())
                else: mongo_data['release_time'] = None
                # artist_id đã được validate và là ObjectId từ serializer

                insert_result = db.albums.insert_one(mongo_data)
                new_album_id = insert_result.inserted_id
                print(f"[POST Album] Created initial album doc: {new_album_id}")

                # 2. Lưu ảnh nếu có
                if image_file and new_album_id:
                    original_filename, file_extension = os.path.splitext(image_file.name)
                    file_extension = file_extension.lower()
                    new_filename = f"{str(new_album_id)}{file_extension}"
                    relative_dir = os.path.join('albums', 'covers').replace("\\", "/") # Thư mục con
                    saved_image_path_relative = os.path.join(relative_dir, new_filename).replace("\\", "/")

                    saved_image_path = default_storage.save(saved_image_path_relative, image_file)
                    print(f"[POST Album] Saved image as: {saved_image_path}")

                    # 3. Cập nhật document với image path
                    db.albums.update_one(
                        {'_id': new_album_id},
                        {'$set': {'image': saved_image_path}}
                    )
                    print(f"[POST Album] Updated doc {new_album_id} with image path: {saved_image_path}")
                else:
                    saved_image_path = None # Không có file để rollback

                # 4. Fetch lại dữ liệu hoàn chỉnh (có $lookup) để trả về
                pipeline_detail = [{'$match': {'_id': new_album_id}}] + self._get_pipeline_stages()
                created_album_agg = list(db.albums.aggregate(pipeline_detail))

                if created_album_agg:
                    response_serializer = AlbumSerializer(created_album_agg[0], context={'request': request})
                    return Response(response_serializer.data, status=status.HTTP_201_CREATED)
                else: raise Exception("Could not retrieve created album details.")

            except Exception as e:
                 # Rollback
                 print(f"[POST Album] Error: {e}")
                 if new_album_id: db.albums.delete_one({'_id': new_album_id}); print(f"Rolled back album doc {new_album_id}")
                 if saved_image_path and default_storage.exists(saved_image_path): default_storage.delete(saved_image_path); print(f"Rolled back image file {saved_image_path}")
                 return Response({"error": f"Could not create album: {e}"}, status=500)
        else:
            print("[POST Album] Serializer Errors:", serializer.errors)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AlbumDetail(APIView):
    _get_pipeline_stages = staticmethod(get_album_aggregation_pipeline)

    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAdminFromMongo()]

    def get(self, request, pk):
        """ Lấy chi tiết album với thông tin artist lồng nhau. """
        if not db: return Response({"error": "Database connection failed"}, 500)
        album_id = None
        try: album_id = ObjectId(pk)
        except Exception: return Response({"error": "Invalid Album ID format"}, 400)

        try:
            # TODO: Thêm $lookup cho songs nếu cần hiển thị danh sách bài hát
            pipeline_detail = [{'$match': {'_id': album_id}}] + self._get_pipeline_stages()
            album_agg = list(db.albums.aggregate(pipeline_detail))

            if album_agg:
                serializer = AlbumSerializer(album_agg[0], context={'request': request})
                return Response(serializer.data)
            else:
                return Response(status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            print(f"[GET /albums/{pk}] Error: {e}")
            return Response({"error": f"Could not retrieve album {pk}"}, 500)

    def put(self, request, pk):
        """ Cập nhật thông tin album, bao gồm cả ảnh bìa. """
        if not db: return Response({"error": "Database connection failed"}, 500)

        album_id = None
        try: album_id = ObjectId(pk)
        except Exception: return Response({"error": "Invalid Album ID format"}, 400)

        album = db.albums.find_one({'_id': album_id})
        if not album: return Response(status=status.HTTP_404_NOT_FOUND)

        # Chuẩn bị dữ liệu cho serializer
        data_for_serializer = request.data.copy()
        if 'image' in request.FILES:
            data_for_serializer['image'] = request.FILES['image']
        # Xử lý artist_id nếu được gửi (cần validate ObjectId và tồn tại)
        if 'artist_id' in data_for_serializer:
            artist_id_str = data_for_serializer['artist_id']
            if artist_id_str and ObjectId.is_valid(artist_id_str):
                 if get_object(db.artists, artist_id_str):
                      data_for_serializer['artist_id'] = ObjectId(artist_id_str)
                 else: return Response({"artist_id": ["Artist does not exist."]}, 400)
            elif artist_id_str: # Nếu gửi nhưng không hợp lệ
                 return Response({"artist_id": ["Invalid ObjectId format."]}, 400)
            # Nếu không gửi artist_id, serializer với partial=True sẽ bỏ qua

        print(f"--- [PUT Album/{pk}] Data for Serializer ---")
        print({k: v for k, v in data_for_serializer.items() if k != 'image'})
        if data_for_serializer.get('image'): print("image: [File Object]")
        print("----------------------------------------")

        serializer = AlbumSerializer(album, data=data_for_serializer, partial=True, context={'request': request})

        if serializer.is_valid():
            update_data = serializer.validated_data
            new_image_file = update_data.pop('image', None)
            old_image_path = album.get('image')
            new_image_path = None
            image_path_to_save_in_db = old_image_path

            try:
                # 1. Xử lý ảnh mới nếu có
                if new_image_file:
                    original_filename, file_extension = os.path.splitext(new_image_file.name); file_extension = file_extension.lower()
                    new_filename = f"{pk}{file_extension}"
                    relative_dir = os.path.join('albums', 'covers').replace("\\", "/")
                    new_image_path_relative = os.path.join(relative_dir, new_filename).replace("\\", "/")

                    # Xóa ảnh cũ trước
                    if old_image_path and old_image_path != new_image_path_relative and default_storage.exists(old_image_path):
                        try: default_storage.delete(old_image_path); print(f"[PUT Album/{pk}] Deleted old image: {old_image_path}")
                        except Exception as file_e: print(f"[PUT Album/{pk}] Warning: Could not delete old image {old_image_path}: {file_e}")

                    # Lưu ảnh mới
                    new_image_path = default_storage.save(new_image_path_relative, new_image_file)
                    print(f"[PUT Album/{pk}] Saved new image as: {new_image_path}")
                    image_path_to_save_in_db = new_image_path

                # Cập nhật trường image trong update_data
                update_data['image'] = image_path_to_save_in_db

                # Chuyển đổi kiểu dữ liệu nếu cần
                if 'release_time' in update_data and update_data['release_time']:
                    update_data['release_time'] = datetime.combine(update_data['release_time'], datetime.min.time())
                elif 'release_time' in update_data: update_data['release_time'] = None
                # artist_id đã là ObjectId nếu có trong update_data

                # 2. Cập nhật MongoDB
                if update_data:
                    db.albums.update_one({'_id': album_id}, {'$set': update_data})
                    print(f"[PUT Album/{pk}] Updated album document")
                else:
                    print(f"[PUT Album/{pk}] No data fields to update.")

                # 3. Fetch lại dữ liệu hoàn chỉnh trả về
                pipeline_detail = [{'$match': {'_id': album_id}}] + self._get_pipeline_stages()
                updated_album_agg = list(db.albums.aggregate(pipeline_detail))

                if updated_album_agg:
                    response_serializer = AlbumSerializer(updated_album_agg[0], context={'request': request})
                    return Response(response_serializer.data)
                else: return Response(status=status.HTTP_404_NOT_FOUND)

            except Exception as e:
                print(f"[PUT Album/{pk}] Error during update/file handling: {e}")
                return Response({"error": f"Could not update album {pk}: {e}"}, status=500)
        else:
            print(f"[PUT Album/{pk}] Serializer Errors:", serializer.errors)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        """ Xóa album và ảnh bìa liên quan. """
        if not db: return Response({"error": "Database connection failed"}, 500)
        album_id = None
        try: album_id = ObjectId(pk)
        except Exception: return Response({"error": "Invalid Album ID format"}, 400)

        album = db.albums.find_one({'_id': album_id})
        if album:
            try:
                image_path_to_delete = album.get('image')
                result = db.albums.delete_one({'_id': album_id})

                if result.deleted_count == 1:
                    if image_path_to_delete and default_storage.exists(image_path_to_delete):
                        try:
                            default_storage.delete(image_path_to_delete)
                            print(f"[DELETE Album/{pk}] Deleted image file: {image_path_to_delete}")
                        except Exception as file_e:
                            print(f"[DELETE Album/{pk}] Warning: Could not delete image file {image_path_to_delete}: {file_e}")
                    return Response(status=status.HTTP_204_NO_CONTENT)
                else: return Response({"error": f"Could not delete album {pk} from DB"}, 500)
            except Exception as e:
                 print(f"[DELETE Album/{pk}] Error: {e}")
                 return Response({"error": f"Could not complete album deletion for {pk}"}, 500)
        else:
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
    """
    API endpoint để lấy danh sách playlists (của user hiện tại hoặc public)
    hoặc tạo playlist mới.
    """
    def get_permissions(self):
        if self.request.method == 'POST':
            # Chỉ user đã đăng nhập mới được tạo playlist
            return [IsAuthenticated()]
        # Ai cũng có thể xem danh sách playlist (sẽ lọc sau)
        return [AllowAny()]

    def get(self, request):
        """ Lấy danh sách playlists. """
        if not db: return Response({"error": "Database connection failed"}, 500)
        try:
            # --- Xử lý Filter và Sort (Client-side cho ví dụ này, có thể làm ở backend) ---
            # Ví dụ: Lấy tất cả public playlists và playlist của user hiện tại
            query = {'is_public': True}
            if request.user and request.user.is_authenticated:
                # user_id từ token (dạng string)
                user_id_str = getattr(request.user, 'user_mongo_id', None) or getattr(request.user, 'id', None)
                if user_id_str:
                    try:
                        user_object_id = ObjectId(user_id_str)
                        query = {'$or': [{'is_public': True}, {'user_id': user_object_id}]}
                    except:
                        pass # Bỏ qua nếu user_id không hợp lệ, chỉ lấy public

            # TODO: Thêm $lookup để lấy tên người tạo và ảnh bìa (từ 4 track đầu)
            # Pipeline ví dụ để lấy tên user tạo
            pipeline = [
                {'$match': query},
                {'$lookup': {
                    'from': 'users', # Collection users
                    'localField': 'user_id',
                    'foreignField': '_id',
                    'as': 'user_details'
                }},
                {'$unwind': {'path': '$user_details', 'preserveNullAndEmptyArrays': True}},
                # TODO: $lookup vào songs để lấy 4 ảnh bìa đầu tiên cho tracks_preview
                {'$project': {
                    'playlist_name': 1,
                    'description': 1,
                    'user_id': 1,
                    'is_public': 1,
                    'creation_day': 1,
                    'songs': 1, # Giữ lại mảng songs (có thể chỉ là IDs hoặc object cơ bản)
                    'user': { # Chỉ lấy username
                        '$cond': {
                            'if': '$user_details',
                            'then': {'_id': '$user_details._id', 'username': '$user_details.username'},
                            'else': None
                        }
                    },
                    'image_url': 1, # Nếu bạn lưu ảnh bìa riêng cho playlist
                    
                }},
                {'$sort': {'creation_day': -1}} # Ví dụ sort theo ngày tạo mới nhất
            ]

            playlists_list = list(db.playlists.aggregate(pipeline))
            # ------------------------------------------------------------

            serializer = PlaylistSerializer(playlists_list, many=True, context={'request': request})
            return Response(serializer.data) # API của bạn có thể trả về { "results": serializer.data } nếu có pagination

        except Exception as e:
            print(f"[GET /playlists/] Error: {e}")
            return Response({"error": "Could not retrieve playlists"}, 500)

    def post(self, request):
        """ User tạo playlist mới. """
        if not db: return Response({"error": "Database connection failed"}, 500)

        # --- QUAN TRỌNG: Yêu cầu đăng nhập ---
        if not request.user or not request.user.is_authenticated:
            return Response({"error": "Authentication required to create a playlist."}, status=status.HTTP_401_UNAUTHORIZED)
        # ------------------------------------

        # Lấy user_id từ token JWT (dạng string)
        user_id_str = getattr(request.user, 'user_mongo_id', None) or getattr(request.user, 'id', None)

        if not user_id_str:
            # Lỗi này không nên xảy ra nếu IsAuthenticated hoạt động đúng
            return Response({"error": "User ID not found in token."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user_object_id = ObjectId(user_id_str)
        except Exception:
            return Response({"error": "Invalid user ID format in token."}, status=status.HTTP_400_BAD_REQUEST)

        # Chuẩn bị dữ liệu từ request body
        data_for_serializer = request.data.copy() # request.data là JSON

        # --- GÁN USER_ID VÀ CREATION_DAY Ở BACKEND ---
        data_for_serializer['user_id'] = user_object_id # Gán ObjectId
        data_for_serializer['creation_day'] = datetime.now(timezone.utc) # Thời gian hiện tại UTC
        # Mảng songs có thể rỗng khi tạo, serializer nên có default=[]
        if 'songs' not in data_for_serializer or not isinstance(data_for_serializer.get('songs'), list):
            data_for_serializer['songs'] = []
        # ---------------------------------------------
        serializer = PlaylistSerializer(data=data_for_serializer, context={'request': request})
        if serializer.is_valid():
            playlist_data_to_save = serializer.validated_data
            playlist_data_to_save['user_id'] = user_object_id # Gán ObjectId
            playlist_data_to_save['creation_day'] = datetime.now(timezone.utc) # Thời gian hiện tại UTC
            # `user_id` và `creation_day` đã nằm trong `validated_data`
            # `songs` cũng đã được validate bởi serializer

            try:
                insert_result = db.playlists.insert_one(playlist_data_to_save)
                new_playlist_id = insert_result.inserted_id

                # Fetch lại playlist vừa tạo (có thể cần $lookup user)
                # Giả sử pipeline đã được định nghĩa ở get() hoặc là static method
                pipeline_detail = [
                    {'$match': {'_id': new_playlist_id}}
                ] + (PlaylistList._get_pipeline_stages_for_list() if hasattr(PlaylistList, '_get_pipeline_stages_for_list') else []) # Tái sử dụng pipeline nếu có

                created_playlist_agg = list(db.playlists.aggregate(pipeline_detail))

                if created_playlist_agg:
                    response_serializer = PlaylistSerializer(created_playlist_agg[0], context={'request': request})
                    return Response(response_serializer.data, status=status.HTTP_201_CREATED)
                else:
                    # Fallback nếu aggregation không trả về gì (hiếm)
                    fallback_doc = db.playlists.find_one({'_id': new_playlist_id})
                    if fallback_doc:
                         user_info = get_object(db.users, str(fallback_doc.get('user_id')))
                         fallback_doc['user'] = {'_id': user_info['_id'], 'username': user_info.get('username')} if user_info else None
                         response_serializer = PlaylistSerializer(fallback_doc, context={'request': request})
                         return Response(response_serializer.data, status=status.HTTP_201_CREATED)
                    raise Exception("Could not retrieve created playlist after insert.")

            except Exception as e:
                print(f"[POST Playlist] Error saving: {e}")
                # Nếu đã insert_one mà lỗi sau đó, cần xem xét xóa bản ghi đã tạo
                # (Logic này có thể phức tạp hơn nếu có nhiều bước sau insert_one)
                return Response({"error": f"Could not create playlist: {e}"}, status=500)
        else:
            print("[POST Playlist] Serializer Errors:", serializer.errors)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PlaylistDetail(APIView):
    """
    API endpoint để lấy, sửa, xóa một playlist cụ thể.
    Sẽ trả về cả danh sách bài hát chi tiết trong playlist.
    """
    _get_song_pipeline_stages = staticmethod(get_song_aggregation_pipeline) # Tái sử dụng

    def get_permissions(self):
        # Ai cũng có thể xem playlist public, hoặc chủ sở hữu xem playlist private
        # Sửa/Xóa chỉ chủ sở hữu hoặc Admin
        if self.request.method == 'GET':
            return [AllowAny()] # Logic kiểm tra public/owner sẽ ở trong hàm get
        # TODO: Cần tạo permission IsOwnerOrAdminOrReadOnly
        return [IsAuthenticated()] # Cho PUT/DELETE, cần kiểm tra owner/admin

    def get(self, request, pk):
        """ Lấy chi tiết playlist, bao gồm cả danh sách bài hát chi tiết. """
        if not db: return Response({"error": "Database connection failed"}, 500)
        playlist_id = None
        try: playlist_id = ObjectId(pk)
        except Exception: return Response({"error": "Invalid Playlist ID format"}, 400)

        try:
            # --- Pipeline để lấy chi tiết playlist và lồng user ---
            playlist_pipeline = [
                {'$match': {'_id': playlist_id}},
                {'$lookup': {
                    'from': 'users',
                    'localField': 'user_id',
                    'foreignField': '_id',
                    'as': 'user_details'
                }},
                {'$unwind': {'path': '$user_details', 'preserveNullAndEmptyArrays': True}},
                {'$project': {
                    'playlist_name': 1, 'description': 1, 'user_id': 1, 'is_public': 1,
                    'creation_day': 1, 'songs': 1, 'image_url': 1, # Giữ lại mảng songs (thường là object {song_id, date_added})
                    'user': { '$cond': { 'if': '$user_details', 'then': {'_id': '$user_details._id', 'username': '$user_details.username'}, 'else': None }}
                }}
            ]
            playlist_agg_result = list(db.playlists.aggregate(playlist_pipeline))
            # ----------------------------------------------------------

            if not playlist_agg_result:
                return Response({"error": "Playlist not found"}, status=status.HTTP_404_NOT_FOUND)

            playlist_data = playlist_agg_result[0]

            # --- Kiểm tra quyền xem playlist (nếu không public) ---
            user_id_str_from_token = getattr(request.user, 'user_mongo_id', None) or getattr(request.user, 'id', None)
            is_owner = False
            if user_id_str_from_token:
                try:
                    is_owner = ObjectId(user_id_str_from_token) == playlist_data.get('user_id')
                except: pass

            if not playlist_data.get('is_public', False) and not is_owner and not IsAdminFromMongo().has_permission(request, self):
                 return Response({"error": "You do not have permission to view this playlist."}, status=status.HTTP_403_FORBIDDEN)
            # ----------------------------------------------------

            song_items_from_playlist = playlist_data.get('songs', []) # Đây là mảng [{song_id, date_added}, ...]
            song_ids_to_fetch = []
            # Tạo một map để lưu date_added theo song_id
            song_date_map = {}

            for item in song_items_from_playlist:
                if isinstance(item, dict) and item.get('song_id') and ObjectId.is_valid(item.get('song_id')):
                    song_id_obj = ObjectId(item.get('song_id'))
                    song_ids_to_fetch.append(song_id_obj)
                    song_date_map[str(song_id_obj)] = item.get('date') # Lưu date_added
                # Xử lý trường hợp 'songs' chỉ là mảng ID (nếu có)
                elif ObjectId.is_valid(item):
                    song_id_obj = ObjectId(item)
                    song_ids_to_fetch.append(song_id_obj)
                    song_date_map[str(song_id_obj)] = None # Không có date_added

            detailed_songs_for_playlist = []
            if song_ids_to_fetch:
                # Dùng aggregation để lấy chi tiết các bài hát này
                song_match_stage = {'$match': {'_id': {'$in': song_ids_to_fetch}}}
                song_pipeline = [song_match_stage] + self._get_song_pipeline_stages() # Tái sử dụng pipeline
                songs_from_db = list(db.songs.aggregate(song_pipeline))

                # Tạo map để dễ truy cập chi tiết bài hát
                songs_db_map = {str(s['_id']): s for s in songs_from_db}

                # Tạo lại mảng songs cho playlist_data theo đúng thứ tự và cấu trúc
                for song_id_obj in song_ids_to_fetch: # Lặp qua ID gốc để giữ thứ tự
                    song_detail = songs_db_map.get(str(song_id_obj))
                    if song_detail:
                        detailed_songs_for_playlist.append({
                            'song': song_detail, # <<< Object song đầy đủ
                            'date_added': song_date_map.get(str(song_id_obj)) # <<< Thêm date_added
                        })
            # --------------------------------------------

            playlist_data['songs'] = detailed_songs_for_playlist # Gán lại mảng songs đã xử lý

            serializer = PlaylistSerializer(playlist_data, context={'request': request})
            return Response(serializer.data)

        except Exception as e:
            print(f"[GET /playlists/{pk}] Error: {e}")
            return Response({"error": f"Could not retrieve playlist {pk}"}, 500)

    def put(self, request, pk):
        """ Sửa playlist (tên, mô tả, is_public, danh sách bài hát). """
        if not db: return Response({"error": "Database connection failed"}, 500)
        playlist_id = None
        try: playlist_id = ObjectId(pk)
        except Exception: return Response({"error": "Invalid Playlist ID format"}, 400)

        playlist = get_object(db.playlists, pk)
        if not playlist: return Response(status=status.HTTP_404_NOT_FOUND)

        # --- Kiểm tra quyền sửa ---
        user_id_str_from_token = getattr(request.user, 'user_mongo_id', None) or getattr(request.user, 'id', None)
        is_owner = False
        if user_id_str_from_token:
             try: is_owner = ObjectId(user_id_str_from_token) == playlist.get('user_id')
             except: pass

        if not is_owner and not IsAdminFromMongo().has_permission(request, self):
            return Response({"error": "You do not have permission to edit this playlist."}, status=status.HTTP_403_FORBIDDEN)
        # ------------------------

        serializer = PlaylistSerializer(playlist, data=request.data, partial=True, context={'request': request})
        if serializer.is_valid():
            update_data = serializer.validated_data
            # Serializer đã validate cấu trúc của mảng 'songs' nếu được gửi
            # Không cần hash password hay xử lý file ở đây

            try:
                db.playlists.update_one({'_id': playlist_id}, {'$set': update_data})
                # Fetch lại để trả về (tương tự logic GET)
                pipeline_detail = [{'$match': {'_id': playlist_id}}] + PlaylistList.get_aggregation_pipeline_for_playlist_detail() # Cần hàm helper này
                updated_playlist_agg = list(db.playlists.aggregate(pipeline_detail))

                if updated_playlist_agg:
                     # Cần fetch lại song details cho playlist này
                     # ... (Logic fetch song details như trong GET) ...
                     # Tạm thời serialize lại dữ liệu thô đã update
                     response_serializer = PlaylistSerializer(updated_playlist_agg[0], context={'request': request})
                     return Response(response_serializer.data)
                else: return Response(status=status.HTTP_404_NOT_FOUND)

            except Exception as e:
                 print(f"[PUT Playlist/{pk}] Error: {e}")
                 return Response({"error": f"Could not update playlist {pk}: {e}"}, status=500)
        else:
            print(f"[PUT Playlist/{pk}] Serializer Errors:", serializer.errors)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


    def delete(self, request, pk):
        """ Xóa playlist. """
        if not db: return Response({"error": "Database connection failed"}, 500)
        playlist_id = None
        try: playlist_id = ObjectId(pk)
        except Exception: return Response({"error": "Invalid Playlist ID format"}, 400)

        playlist = get_object(db.playlists, pk)
        if not playlist: return Response(status=status.HTTP_404_NOT_FOUND)

        # --- Kiểm tra quyền xóa ---
        user_id_str_from_token = getattr(request.user, 'user_mongo_id', None) or getattr(request.user, 'id', None)
        is_owner = False
        if user_id_str_from_token:
            try: is_owner = ObjectId(user_id_str_from_token) == playlist.get('user_id')
            except: pass

        if not is_owner and not IsAdminFromMongo().has_permission(request, self):
            return Response({"error": "You do not have permission to delete this playlist."}, status=status.HTTP_403_FORBIDDEN)
        # -----------------------

        try:
            result = db.playlists.delete_one({'_id': playlist_id})
            if result.deleted_count == 1:
                return Response(status=status.HTTP_204_NO_CONTENT)
            else: return Response({"error": f"Could not delete playlist {pk} from DB"}, status=500)
        except Exception as e:
             print(f"[DELETE Playlist/{pk}] Error: {e}")
             return Response({"error": f"Could not complete playlist deletion for {pk}"}, status=500)


# --- Helper pipeline cho PlaylistList và PlaylistDetail để lấy user lồng nhau ---
# Có thể đặt làm static method hoặc hàm riêng
def get_playlist_aggregation_pipeline_with_user():
     return [
        {'$lookup': { 'from': 'users', 'localField': 'user_id', 'foreignField': '_id', 'as': 'user_details' }},
        {'$unwind': {'path': '$user_details', 'preserveNullAndEmptyArrays': True}},
        {'$project': {
            'playlist_name': 1, 'description': 1, 'user_id': 1, 'is_public': 1,
            'creation_day': 1, 'songs': 1, 'image_url': 1,
            'user': { '$cond': { 'if': '$user_details', 'then': {'_id': '$user_details._id', 'username': '$user_details.username'}, 'else': None }}
            # TODO: Thêm logic lấy 4 ảnh bìa đầu tiên cho tracks_preview nếu cần cho PlaylistList
        }}
     ]
     
PlaylistList.get_aggregation_pipeline_for_playlist_detail = staticmethod(get_playlist_aggregation_pipeline_with_user)

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

class MusicGenreSelectView(APIView):
    """ Cung cấp danh sách thể loại nhạc rút gọn cho select options. """
    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()] # Ai cũng xem được list
        # Các method khác (POST) sẽ dùng default (IsAdminFromMongo)
        return super().get_permissions()
    
    def get(self, request):
        if not db: return Response({"error": "Database connection failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        try:
            # Chỉ lấy _id và genre_name, sắp xếp theo tên
            genres_cursor = db.musicgenres.find({}, {'_id': 1, 'musicgenre_name': 1}).sort('musicgenre_name', 1)
            serializer = MusicGenreSelectSerializer(list(genres_cursor), many=True)
            return Response(serializer.data)
        except Exception as e:
            print(f"Error fetching music genre options: {e}")
            return Response({"error": "Could not retrieve music genre options"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
class AlbumSongsView(APIView):
    """ Lấy danh sách bài hát thuộc một album cụ thể. """
    permission_classes = [AllowAny] # Ai cũng có thể lấy bài hát của album

    # Gán lại hàm helper nếu cần
    _get_pipeline_stages = staticmethod(get_song_aggregation_pipeline)

    def get(self, request, pk): # pk ở đây là Album ID
        if not db: return Response({"error": "Database connection failed"}, 500)
        album_id = None
        try:
            album_id = ObjectId(pk)
        except Exception:
             return Response({"error": "Invalid Album ID format"}, status=400)

        # Kiểm tra xem album có tồn tại không (tùy chọn)
        # album_exists = db.albums.count_documents({'_id': album_id}, limit=1) > 0
        # if not album_exists:
        #     return Response({"error": "Album not found"}, status=404)

        try:
            # --- Tìm tất cả bài hát có album_id khớp ---
            # Sử dụng aggregation để lấy cả thông tin artist/album lồng nhau cho các bài hát này
            match_stage = {'$match': {'album_id': album_id}}
            sort_stage = {'$sort': {'track_number': 1, 'song_name': 1}} # Sắp xếp theo số track (nếu có) hoặc tên
            pipeline = [match_stage] + self._get_pipeline_stages() + [sort_stage]

            album_songs = list(db.songs.aggregate(pipeline))
            # ----------------------------------------------

            # Serialize danh sách bài hát
            # Lưu ý: SongSerializer đã có sẵn logic tạo file_url nếu context được truyền
            serializer = SongSerializer(album_songs, many=True, context={'request': request})
            return Response(serializer.data) # Trả về mảng các bài hát

        except Exception as e:
            print(f"Error fetching songs for album {pk}: {e}")
            return Response({"error": f"Could not retrieve songs for album {pk}"}, 500)
        
class ArtistAlbumsView(APIView):
    """ Lấy danh sách albums của một nghệ sĩ cụ thể. """
    permission_classes = [AllowAny] # Ai cũng có thể xem album của nghệ sĩ
    _get_album_pipeline = staticmethod(get_album_aggregation_pipeline) # Nếu dùng chung

    def get(self, request, pk): # pk là Artist ID
        if not db: return Response({"error": "Database connection failed"}, 500)
        artist_id = None
        try: artist_id = ObjectId(pk)
        except Exception: return Response({"error": "Invalid Artist ID format"}, 400)

        # --- Xử lý Params (Sort, Limit) ---
        try:
             # Ví dụ lấy 6 album mới nhất cho "Recent releases"
             limit = int(request.query_params.get('limit', 6))
             # Sort theo release_time giảm dần (cần field này trong DB)
             sort_field = request.query_params.get('sort', 'release_time')
             sort_order = -1 if request.query_params.get('order', 'desc').lower() == 'desc' else 1
             if limit < 1 : limit = 6
        except ValueError: limit = 6; sort_field = 'release_time'; sort_order = -1

        try:
            # --- Tìm albums của nghệ sĩ ---
            # Cách 1: Dùng find (nếu không cần $lookup phức tạp trong AlbumSerializer)
            # albums_cursor = db.albums.find({'artist_id': artist_id}).sort(sort_field, sort_order).limit(limit)
            # albums_list = list(albums_cursor)
            # # Cần fetch artist lại nếu AlbumSerializer không có sẵn artist
            # for album in albums_list:
            #    album['artist'] = get_object(db.artists, str(album.get('artist_id')))

            # Cách 2: Dùng Aggregation (tốt hơn nếu cần dữ liệu lồng nhau cho Album)
            match_stage = {'$match': {'artist_id': artist_id}}
            sort_stage = {'$sort': {sort_field: sort_order}}
            limit_stage = {'$limit': limit}
            pipeline = [match_stage] + self._get_album_pipeline() + [sort_stage, limit_stage] # Gọi pipeline của Album

            albums_list = list(db.albums.aggregate(pipeline))
            # -----------------------------

            # Serialize danh sách album
            serializer = AlbumSerializer(albums_list, many=True, context={'request': request})
            # Trả về mảng trực tiếp hoặc cấu trúc có results tùy ý
            return Response(serializer.data) # Hoặc Response({'results': serializer.data})

        except Exception as e:
            print(f"Error fetching albums for artist {pk}: {e}")
            return Response({"error": f"Could not retrieve albums for artist {pk}"}, 500)
        
class ArtistTopTracksView(APIView):
    """ Lấy danh sách bài hát phổ biến nhất của một nghệ sĩ. """
    permission_classes = [AllowAny]
    _get_song_pipeline = staticmethod(get_song_aggregation_pipeline) # Nếu dùng chung

    def get(self, request, pk): # pk là Artist ID
        if not db: return Response({"error": "Database connection failed"}, 500)
        artist_id = None
        try: artist_id = ObjectId(pk)
        except Exception: return Response({"error": "Invalid Artist ID format"}, 400)

        # --- Xử lý Params (Limit) ---
        try:
             limit = int(request.query_params.get('limit', 5)) # Mặc định lấy top 5
             if limit < 1 : limit = 5
        except ValueError: limit = 5

        try:
            # --- Tìm tracks của nghệ sĩ, sắp xếp theo plays giảm dần ---
            match_stage = {'$match': {'artist_ids': artist_id}} # Tìm trong mảng artist_ids
            sort_stage = {'$sort': {'number_of_plays': -1}} # Sắp xếp giảm dần theo lượt nghe
            limit_stage = {'$limit': limit}
            # Kết hợp với pipeline lấy dữ liệu lồng nhau của Song
            pipeline = [match_stage] + self._get_song_pipeline() + [sort_stage, limit_stage]

            top_tracks = list(db.songs.aggregate(pipeline))
            # ---------------------------------------------------------

            serializer = SongSerializer(top_tracks, many=True, context={'request': request})
            return Response(serializer.data) # Trả về mảng tracks

        except Exception as e:
            print(f"Error fetching top tracks for artist {pk}: {e}")
            return Response({"error": f"Could not retrieve top tracks for artist {pk}"}, 500)
        
class GenreTracksView(APIView):
    """ Lấy danh sách bài hát thuộc một thể loại cụ thể. """
    permission_classes = [AllowAny] # Ai cũng có thể xem bài hát theo genre
    _get_song_pipeline = staticmethod(get_song_aggregation_pipeline)

    def get(self, request, pk): # pk là Genre ID (ObjectId string)
        if not db: return Response({"error": "Database connection failed"}, 500)
        genre_id = None
        try:
            genre_id = ObjectId(pk)
        except Exception:
             return Response({"error": "Invalid Genre ID format"}, status=400)

        # Kiểm tra genre có tồn tại không (tùy chọn)
        genre_exists = db.musicgenres.count_documents({'_id': genre_id}, limit=1) > 0
        if not genre_exists:
            return Response({"error": "Genre not found"}, status=404)

        # --- Xử lý Params (Sort, Pagination - Tùy chọn) ---
        try:
            page = int(request.query_params.get('page', 1))
            limit = int(request.query_params.get('limit', 20)) # Ví dụ 20 bài/trang
            sort_field = request.query_params.get('sort', 'song_name') # Mặc định sort theo tên
            sort_order = 1 if request.query_params.get('order', 'asc').lower() == 'asc' else -1
            if page < 1: page = 1
            if limit < 1: limit = 20
            skip = (page - 1) * limit
        except ValueError:
            return Response({"error": "Invalid 'page' or 'limit' parameter."}, status=400)
        # ----------------------------------------------

        try:
            # --- Tìm tracks có musicgenre_id này ---
            match_stage = {'$match': {'musicgenre_ids': genre_id}} # Tìm trong mảng musicgenre_ids

            # --- Tính tổng số tracks cho pagination ---
            count_pipeline = [match_stage, {'$count': 'total'}]
            count_result = list(db.songs.aggregate(count_pipeline))
            total_documents = count_result[0]['total'] if count_result else 0
            total_pages = ceil(total_documents / limit) # Cần import ceil from math
            # ----------------------------------------

            # --- Pipeline hoàn chỉnh để lấy dữ liệu trang hiện tại ---
            sort_stage = {'$sort': {sort_field: sort_order}}
            skip_stage = {'$skip': skip}
            limit_stage = {'$limit': limit}
            # Kết hợp với pipeline chuẩn của Song để lấy dữ liệu lồng nhau
            pipeline = [match_stage] + self._get_song_pipeline() + [sort_stage, skip_stage, limit_stage]

            genre_tracks = list(db.songs.aggregate(pipeline))
            # -----------------------------------------------

            serializer = SongSerializer(genre_tracks, many=True, context={'request': request})

            # --- Trả về cấu trúc có pagination ---
            return Response({
                'count': total_documents,
                'total_pages': total_pages,
                'current_page': page,
                'limit': limit,
                'results': serializer.data
            })
            # ------------------------------------

        except Exception as e:
            print(f"Error fetching tracks for genre {pk}: {e}")
            return Response({"error": f"Could not retrieve tracks for genre {pk}"}, 500)
        
class FeaturedContentView(APIView):
    """
    Trả về một album hoặc playlist nổi bật (ví dụ: lấy ngẫu nhiên hoặc mới nhất).
    API: GET /api/home/featured/
    """
    permission_classes = [AllowAny]
    _get_album_pipeline = staticmethod(get_album_aggregation_pipeline) # Tái sử dụng

    def get(self, request):
        if not db: return Response({"error": "Database connection failed"}, 500)
        try:
            # --- Logic lấy Featured Content ---
            # Ví dụ: Lấy 1 album mới nhất hoặc ngẫu nhiên
            # Cần có trường ngày tạo (ví dụ: 'createdAt') hoặc dựa vào _id
            # Hoặc một trường 'is_featured' = True

            # Lấy 5 album mới nhất (ví dụ)
            pipeline_albums = [{'$sort': {'_id': -1}}, {'$limit': 5}] + self._get_album_pipeline()
            recent_albums = list(db.albums.aggregate(pipeline_albums))

            # Lấy 5 playlist mới nhất (ví dụ) - Cần tạo get_playlist_aggregation_pipeline()
            # recent_playlists = list(db.playlists.find().sort('_id', -1).limit(5))

            featured_item = None
            item_type = None

            # Chọn ngẫu nhiên từ danh sách lấy được
            if recent_albums:
                # featured_item = random.choice(recent_albums) # Chọn ngẫu nhiên
                featured_item = recent_albums[0] # Hoặc lấy cái mới nhất
                item_type = 'album'
            # elif recent_playlists: # Nếu có playlist
            #     featured_item = random.choice(recent_playlists)
            #     item_type = 'playlist'

            if featured_item:
                # Serialize dựa trên type
                if item_type == 'album':
                    serializer = AlbumSerializer(featured_item, context={'request': request})
                # elif item_type == 'playlist':
                #     serializer = PlaylistSerializer(featured_item, context={'request': request}) # Cần PlaylistSerializer
                else: # Fallback
                     return Response({"error": "No featured content available."}, status=404)

                # Trả về thêm type để frontend biết cách xử lý
                return Response({**serializer.data, "type": item_type})
            else:
                return Response({"error": "No featured content available."}, status=404)

        except Exception as e:
            print(f"Error fetching featured content: {e}")
            return Response({"error": "Could not retrieve featured content"}, 500)


class MostPlayedView(APIView):
    """
    Trả về danh sách các bài hát hoặc album được nghe nhiều nhất.
    API: GET /api/home/most-played/?type=songs&limit=10  (type có thể là 'songs' hoặc 'albums')
    """
    permission_classes = [AllowAny]
    _get_song_pipeline = staticmethod(get_song_aggregation_pipeline)
    _get_album_pipeline = staticmethod(get_album_aggregation_pipeline)

    def get(self, request):
        if not db: return Response({"error": "Database connection failed"}, 500)
        try:
            item_type = request.query_params.get('type', 'songs').lower()
            limit = int(request.query_params.get('limit', 10))
            if limit < 1 or limit > 50: limit = 10 # Giới hạn an toàn

            results = []
            if item_type == 'songs':
                # Sắp xếp theo number_of_plays giảm dần
                pipeline = [{'$sort': {'number_of_plays': -1}}, {'$limit': limit}] + self._get_song_pipeline()
                results = list(db.songs.aggregate(pipeline))
                serializer = SongSerializer(results, many=True, context={'request': request})
            elif item_type == 'albums':
                pipeline = [{'$sort': {'number_of_plays': -1}}, {'$limit': limit}] + self._get_album_pipeline()
                results = list(db.albums.aggregate(pipeline))
                serializer = AlbumSerializer(results, many=True, context={'request': request})
            else:
                return Response({"error": "Invalid type parameter. Use 'songs' or 'albums'."}, status=400)

            return Response({"results": serializer.data, "count": len(results)}) # Hoặc count từ DB nếu có phân trang

        except Exception as e:
            print(f"Error fetching most played {item_type}: {e}")
            return Response({"error": f"Could not retrieve most played {item_type}"}, 500)


class LibraryHighlightsView(APIView):
    """
    Trả về các mục nổi bật từ thư viện (ví dụ: mix albums, playlists, artists).
    API: GET /api/home/library-highlights/?limit=10
    Hiện tại, ví dụ này sẽ trả về albums và artists mới nhất.
    """
    permission_classes = [AllowAny] # Hoặc IsAuthenticated nếu là thư viện của user
    _get_album_pipeline = staticmethod(get_album_aggregation_pipeline)

    def get(self, request):
        if not db: return Response({"error": "Database connection failed"}, 500)
        try:
            limit_per_type = int(request.query_params.get('limit', 5)) # Lấy 5 của mỗi loại
            if limit_per_type < 1 or limit_per_type > 20: limit_per_type = 5

            highlights = []

            # Lấy albums mới nhất
            pipeline_albums = [{'$sort': {'_id': -1}}, {'$limit': limit_per_type}] + self._get_album_pipeline()
            recent_albums = list(db.albums.aggregate(pipeline_albums))
            album_serializer = AlbumSerializer(recent_albums, many=True, context={'request': request})
            for album_data in album_serializer.data:
                highlights.append({**album_data, "item_type": "album"}) # Thêm item_type

            # Lấy artists mới nhất (ví dụ)
            recent_artists = list(db.artists.find().sort('_id', -1).limit(limit_per_type))
            artist_serializer = ArtistSerializer(recent_artists, many=True, context={'request': request})
            for artist_data in artist_serializer.data:
                highlights.append({**artist_data, "item_type": "artist"}) # Thêm item_type

            # Xáo trộn danh sách highlights cuối cùng (tùy chọn)
            random.shuffle(highlights)

            return Response({"results": highlights, "count": len(highlights)})

        except Exception as e:
            print(f"Error fetching library highlights: {e}")
            return Response({"error": "Could not retrieve library highlights"}, 500)


class RecentlyAddedReleasesView(APIView):
    """
    Trả về các album mới được thêm/phát hành gần đây.
    API: GET /api/home/new-releases/?limit=10
    """
    permission_classes = [AllowAny]
    _get_album_pipeline = staticmethod(get_album_aggregation_pipeline)

    def get(self, request):
        if not db: return Response({"error": "Database connection failed"}, 500)
        try:
            limit = int(request.query_params.get('limit', 10))
            if limit < 1 or limit > 50: limit = 10

            # Sắp xếp theo release_time (nếu có) hoặc _id (ngày tạo) giảm dần
            # Nếu release_time là string, cần $dateFromString trước khi sort
            sort_criteria = {'release_time': -1, '_id': -1} # Ưu tiên release_time
            pipeline = [{'$sort': sort_criteria}, {'$limit': limit}] + self._get_album_pipeline()
            new_releases = list(db.albums.aggregate(pipeline))

            serializer = AlbumSerializer(new_releases, many=True, context={'request': request})
            return Response({"results": serializer.data, "count": len(new_releases)})

        except Exception as e:
            print(f"Error fetching new releases: {e}")
            return Response({"error": "Could not retrieve new releases"}, 500)
        
def serve_media_with_range(request, path):
    """
    View tùy chỉnh để phục vụ file media có hỗ trợ Range Requests và no-cache.
    """
    fullpath = os.path.join(settings.MEDIA_ROOT, path)
    if not os.path.abspath(fullpath).startswith(os.path.abspath(settings.MEDIA_ROOT)) or not os.path.exists(fullpath):
         raise Http404('"%(path)s" does not exist' % {"path": fullpath})
    if os.path.isdir(fullpath):
         raise Http404('"%(path)s" is a directory' % {"path": fullpath})

    try:
        statobj = os.stat(fullpath)
    except OSError:
         raise Http404("File not found or permissions error reading file stats.")

    range_header = request.META.get('HTTP_RANGE', '').strip()
    range_match = re.match(r'bytes=(\d+)-(\d*)', range_header)
    size = statobj.st_size
    content_type, encoding = mimetypes.guess_type(fullpath)
    content_type = content_type or 'application/octet-stream'
    response = None
    file_handle = None # Khởi tạo để có thể đóng trong finally nếu cần

    try: # Thêm try...finally để đảm bảo file được đóng
        if range_match:
            first_byte, last_byte = range_match.groups()
            first_byte = int(first_byte) if first_byte else 0
            last_byte = int(last_byte) if last_byte else size - 1
            if last_byte >= size: last_byte = size - 1
            length = last_byte - first_byte + 1
            if first_byte >= size or length <= 0:
                response = HttpResponse(status=416)
                response["Content-Range"] = f"bytes */{size}"
                # Vẫn thêm header no-cache cho lỗi
                response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
                response['Pragma'] = 'no-cache'
                response['Expires'] = '0'
                return response

            # Mở file handle
            file_handle = open(fullpath, 'rb')
            file_handle.seek(first_byte)

            # Tạo StreamingHttpResponse với iterator đọc theo chunk
            # Chỉ đọc đúng số byte cần thiết
            def file_iterator(file_handle, chunk_size=8192, bytes_to_read=length):
                 bytes_read = 0
                 while bytes_read < bytes_to_read:
                     read_size = min(chunk_size, bytes_to_read - bytes_read)
                     chunk = file_handle.read(read_size)
                     if not chunk:
                         break # Hết file sớm hơn dự kiến?
                     bytes_read += len(chunk)
                     yield chunk
                 # Đóng file handle sau khi đọc xong iterator (quan trọng)
                 file_handle.close()

            response = StreamingHttpResponse(file_iterator(file_handle), content_type=content_type, status=206)
            response["Content-Length"] = str(length)
            response["Content-Range"] = f"bytes {first_byte}-{last_byte}/{size}"
            # --- KHÔNG CẦN DÒNG NÀY ---
            # response.file_to_stream = file_handle
            # --------------------------

        else:
            # Không có Range header, trả về toàn bộ file bằng StreamingHttpResponse
            file_handle = open(fullpath, 'rb')
            # Dùng FileWrapper sẽ tự đóng file khi response kết thúc
            response = StreamingHttpResponse(FileWrapper(file_handle, 8192), content_type=content_type)
            response["Content-Length"] = str(size)
            # --- KHÔNG CẦN DÒNG NÀY ---
            # response.file_to_stream = file_handle
            # --------------------------

        # --- Thêm các Headers (No-Cache, Last-Modified, Accept-Ranges) ---
        response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        response["Last-Modified"] = http_date(statobj.st_mtime)
        response["Accept-Ranges"] = "bytes"
        # --------------------------------------------------------------

        return response

    except Exception as e:
        print(f"Error serving media file {path}: {e}")
        # Đảm bảo đóng file nếu có lỗi xảy ra trước khi response được tạo
        if file_handle and not file_handle.closed:
             file_handle.close()
             print(f"Closed file handle for {path} due to exception.")
        # Có thể raise Http404 hoặc trả về lỗi server tùy tình huống
        # raise Http404("Error processing file.")
        return HttpResponseServerError("Error processing media file.")
    
class ChangePasswordView(APIView):
    """ Endpoint cho phép user đã đăng nhập đổi mật khẩu của chính họ. """
    permission_classes = [IsAuthenticated] # << Yêu cầu phải đăng nhập

    def post(self, request, *args, **kwargs):
        print("[ChangePasswordView] Received POST request.") # Thêm debug
        if not db: return Response({"error": "Lỗi DB."}, status=500)

        user = request.user
        user_mongo_id_str = getattr(user, 'user_mongo_id', None)
        if not user_mongo_id_str:
            return Response({"error": "Không thể xác định người dùng."}, status=400)

        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})

        if serializer.is_valid():
            old_password = serializer.validated_data['old_password']
            new_password = serializer.validated_data['new_password']

            # Lấy hash cũ từ DB
            try:
                user_doc = db.users.find_one({'_id': ObjectId(user_mongo_id_str)})
                if not user_doc: return Response({"error": "User not found."}, 404)
                current_hash = user_doc.get('password')
            except Exception as e:
                print(f"Error fetching user for pass change: {e}")
                return Response({"error": "Lỗi DB."}, 500)

            # Kiểm tra pass cũ
            if not check_password(old_password, current_hash):
                return Response({"old_password": ["Mật khẩu cũ không chính xác."]}, status=400)

            # Hash và cập nhật pass mới
            try:
                new_hash = make_password(new_password)
                db.users.update_one({'_id': ObjectId(user_mongo_id_str)}, {'$set': {'password': new_hash}})
                return Response({"message": "Đổi mật khẩu thành công."}, status=200)
            except Exception as e:
                print(f"Error updating password: {e}")
                return Response({"error": "Lỗi cập nhật mật khẩu."}, 500)
        else:
            return Response(serializer.errors, status=400) # Lỗi validation