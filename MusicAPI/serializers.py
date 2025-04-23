# music_api/serializers.py
from rest_framework import serializers
from bson import ObjectId
from django.conf import settings


# from urllib.parse import urljoin # Một lựa chọn khác

# --- Custom ObjectId Field ---
class ObjectIdField(serializers.Field):
    """
    Serializer field for MongoDB ObjectId.
    Converts ObjectId to string for representation and string to ObjectId for internal value.
    """
    def to_representation(self, value):
        return str(value)

    def to_internal_value(self, data):
        try:
            # Allow data to be already an ObjectId instance
            if isinstance(data, ObjectId):
                return data
            # Attempt to convert string to ObjectId
            return ObjectId(data)
        except Exception: # Catch broader exceptions including TypeError if data is not string/bytes
            raise serializers.ValidationError(f"'{data}' is not a valid ObjectId.")

# --- Base Serializer for Media URL Handling ---
class BaseMediaURLSerializer(serializers.Serializer):
    """
    Base serializer providing a method to generate absolute media URLs.
    Requires 'request' in the serializer context.
    """
    def _get_absolute_media_url(self, relative_path):
        """
        Generates an absolute URL for a given relative media path.
        """
        if not relative_path:
            return None

        request = self.context.get('request')
        if not request:
            # Fallback if request context is missing (less ideal)
            media_url = settings.MEDIA_URL if settings.MEDIA_URL.endswith('/') else settings.MEDIA_URL + '/'
            clean_path = relative_path.lstrip('/')
            # Warning: This won't include the domain, only use as last resort
            return f"{media_url}{clean_path}"

        # Ensure MEDIA_URL ends with '/' and path doesn't start with '/'
        media_url = settings.MEDIA_URL if settings.MEDIA_URL.endswith('/') else settings.MEDIA_URL + '/'
        clean_path = relative_path.lstrip('/')

        # Use request.build_absolute_uri for a full URL including scheme and domain
        return request.build_absolute_uri(f"{media_url}{clean_path}")

        # Alternative using urljoin:
        # base_url = request.build_absolute_uri('/') # Gets http://domain/
        # return urljoin(base_url, f"{media_url}{clean_path}")


# --- Basic Serializers for Nested Data (Inherit for Media URL handling) ---

class ArtistBasicSerializer(BaseMediaURLSerializer):
    """ Basic representation of an Artist, suitable for nesting. """
    _id = ObjectIdField(read_only=True)
    artist_name = serializers.CharField(read_only=True)
    artist_avatar_url = serializers.SerializerMethodField(read_only=True)

    def get_artist_avatar_url(self, obj):
        return self._get_absolute_media_url(obj.get('artist_avatar'))

class AlbumBasicSerializer(BaseMediaURLSerializer):
    """ Basic representation of an Album, suitable for nesting. """
    _id = ObjectIdField(read_only=True)
    album_name = serializers.CharField(read_only=True)
    image_url = serializers.SerializerMethodField(read_only=True)

    def get_image_url(self, obj):
        return self._get_absolute_media_url(obj.get('image'))
    
class AlbumSelectSerializer(serializers.Serializer):
    """ Trả về ID và tên Album cho dropdown select. """
    _id = ObjectIdField(read_only=True)
    album_name = serializers.CharField(read_only=True)


# --- Main Model Serializers ---

class MusicGenreSerializer(serializers.Serializer):
    _id = ObjectIdField(read_only=True)
    musicgenre_name = serializers.CharField(max_length=50)

class UserSerializer(BaseMediaURLSerializer):
    _id = ObjectIdField(read_only=True)
    username = serializers.CharField(max_length=100, required=True) # ERD có 100
    email = serializers.EmailField(max_length=100, required=True) # ERD có 100

    # --- Password Handling ---
    # write_only=True: không bao giờ gửi về client
    # required=False: không bắt buộc nhập khi update (trừ khi muốn đổi pass)
    #                  khi tạo mới (POST), view sẽ cần kiểm tra và bắt buộc
    password = serializers.CharField(
        max_length=255,
        write_only=True,
        required=False, # Không bắt buộc khi PUT (chỉ nhập nếu muốn đổi)
        style={'input_type': 'password'} # Gợi ý cho browsable API
    )
    # -----------------------

    # --- Profile Picture Handling ---
    profile_picture_url = serializers.SerializerMethodField(read_only=True) # Để đọc URL
    profile_picture = serializers.FileField(write_only=True, required=False, allow_null=True) # Để nhận file upload
    # ----------------------------

    date_of_birth = serializers.DateTimeField(required=False, allow_null=True)

    # --- Admin/Staff Status ---
    # read_only=True: Thường chỉ admin cấp cao nhất mới đổi được quyền này
    # Hoặc bạn có thể cho phép ghi (writeable) nếu muốn admin sửa quyền user khác
    is_staff = serializers.BooleanField(default=False, read_only=False) # Ví dụ: Chỉ đọc
    is_active = serializers.BooleanField(default=True, read_only=False) # Ví dụ: Chỉ đọc
    # -------------------------

    # favourite_songs = serializers.ListField(child=ObjectIdField(), required=False, default=list) # Tùy chọn

    def get_profile_picture_url(self, obj):
        # Lấy từ trường 'profile_picture' (chứa path) trong document MongoDB
        return self._get_absolute_media_url(obj.get('profile_picture'))

    def validate_username(self, value):
        from .views import db # Import db từ views.py để kiểm tra kết nối
        
        """Kiểm tra username không trùng (khi tạo và có thể cả khi sửa)."""
        if not db: raise serializers.ValidationError("Database error.")
        # Lấy instance hiện tại (nếu là update) từ context hoặc self.instance
        instance_id = self.instance.get('_id') if self.instance else None
        query = {'username': value}
        if instance_id:
            query['_id'] = {'$ne': instance_id} # Loại trừ chính user đang sửa
        if db.users.count_documents(query) > 0:
            raise serializers.ValidationError("A user with that username already exists.")
        return value

    def validate_email(self, value):
        """Kiểm tra email không trùng."""
        from .views import db # Import db từ views.py để kiểm tra kết nối
        if not db: raise serializers.ValidationError("Database error.")
        instance_id = self.instance.get('_id') if self.instance else None
        query = {'email': value}
        if instance_id:
            query['_id'] = {'$ne': instance_id}
        if db.users.count_documents(query) > 0:
            raise serializers.ValidationError("A user with that email already exists.")
        return value

class AdminSerializer(serializers.Serializer):
     _id = ObjectIdField(read_only=True)
     user_id = ObjectIdField() # Assuming this refers to a User document _id
     username = serializers.CharField(max_length=50)
     password = serializers.CharField(max_length=255, write_only=True)

class ArtistSerializer(BaseMediaURLSerializer):
    _id = ObjectIdField(read_only=True)
    artist_name = serializers.CharField(max_length=50)
    date_of_birth = serializers.DateTimeField(required=False, allow_null=True)
    national = serializers.CharField(max_length=50, required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)
    artist_avatar_url = serializers.SerializerMethodField(read_only=True) # Read-only URL field
    # Field for receiving relative path during POST/PUT (optional)
    artist_avatar = serializers.CharField(write_only=True, required=False, allow_null=True, allow_blank=True)
    social_media = serializers.CharField(max_length=255, required=False, allow_blank=True)
    # These might be calculated fields, consider making them read_only or removing if managed elsewhere
    number_of_songs = serializers.IntegerField(required=False, default=0)
    number_of_plays = serializers.IntegerField(required=False, default=0)
    number_of_likes = serializers.IntegerField(required=False, default=0)
    # --- Trường nhận file upload ---
    artist_avatar = serializers.FileField(write_only=True, required=False, allow_null=True)
    # Assuming you write genre IDs and read them separately if needed
    musicgenre_ids = serializers.ListField(child=ObjectIdField(), required=False, default=list)

    def get_artist_avatar_url(self, obj):
        return self._get_absolute_media_url(obj.get('artist_avatar'))

class AlbumSerializer(BaseMediaURLSerializer):
    _id = ObjectIdField(read_only=True)
    # --- Artist ---
    artist_id = ObjectIdField(write_only=True, required=True) # Bắt buộc khi tạo/thay đổi artist
    artist = ArtistBasicSerializer(read_only=True) # Hiển thị khi đọc (dữ liệu cần được view cung cấp)
    # --------------
    album_name = serializers.CharField(max_length=60, required=True)
    release_time = serializers.DateTimeField(required=False, allow_null=True)
    description = serializers.CharField(max_length=255, required=False, allow_blank=True)
    # --- Image ---
    image_url = serializers.SerializerMethodField(read_only=True) # Để đọc URL
    image = serializers.FileField(write_only=True, required=False, allow_null=True) # Để nhận file upload (dùng ImageField để có validation cơ bản)
    # -------------
    # Các trường read-only (thường được tính toán hoặc quản lý riêng)
    number_of_songs = serializers.IntegerField(read_only=True, default=0)
    number_of_plays = serializers.IntegerField(read_only=True, default=0)
    number_of_likes = serializers.IntegerField(read_only=True, default=0)
    # Có thể thêm trường 'songs' nếu muốn trả về danh sách bài hát trong chi tiết album
    # songs = SongBasicSerializer(many=True, read_only=True) # Cần tạo SongBasicSerializer

    def get_image_url(self, obj):
        # Lấy từ trường 'image' (chứa path tương đối) trong document MongoDB
        return self._get_absolute_media_url(obj.get('image'))

    def validate_artist_id(self, value):
        from .views import db # Import db từ views.py để kiểm tra kết nối
        from .views import get_object # Import hàm get_object từ views.py để kiểm tra ObjectId
        
        """Kiểm tra xem Artist ID có tồn tại không."""
        if not db: raise serializers.ValidationError("Database not connected.")
        
        if not get_object(db.artists, str(value)): # Chuyển về string để tìm
            raise serializers.ValidationError(f"Artist with ID '{value}' does not exist.")
        return value # Trả về ObjectId đã được convert bởi ObjectIdField

class SongSerializer(BaseMediaURLSerializer):
    _id = ObjectIdField(read_only=True)
    # For reading nested info (assuming view provides it)
    artists = ArtistBasicSerializer(many=True, read_only=True)
    album = AlbumBasicSerializer(read_only=True)
    # For writing relationships
    artist_ids = serializers.ListField(child=ObjectIdField(), write_only=True, required=True) # Must have at least one artist
    album_id = ObjectIdField(write_only=True, required=False, allow_null=True) # Album can be optional

    song_name = serializers.CharField(max_length=255) # Max length from ERD
    description = serializers.CharField(max_length=255, required=False, allow_blank=True)
    lyrics = serializers.CharField(required=False, allow_blank=True) # Assuming text field
    release_time = serializers.DateTimeField(required=False, allow_null=True) # Date or DateTime?
    duration_song = serializers.IntegerField(required=False, allow_null=True) # Duration in seconds?
    # Read-only calculated fields?
    number_of_plays = serializers.IntegerField(required=False, read_only=True, default=0)
    number_of_likes = serializers.IntegerField(required=False, read_only=True, default=0)
    
     # --- Trường để nhận file upload ---
    # write_only=True vì không lưu trực tiếp file object vào Mongo
    # required=False nếu không bắt buộc phải upload file khi tạo/sửa
    audio_file = serializers.FileField(write_only=True, required=False, allow_null=True)
    # ---------------------------------

    file_url = serializers.SerializerMethodField(read_only=True) # Read-only URL field
    # Field for receiving relative path during POST/PUT (optional)
    # file_up = serializers.CharField(write_only=True, required=False, allow_null=True, allow_blank=True)

    status = serializers.CharField(max_length=20, required=False, allow_blank=True) # Max length from ERD

    def get_file_url(self, obj):
        # Assumes the relative path is stored in the 'file_up' key in the MongoDB document
        return self._get_absolute_media_url(obj.get('file_up'))

class PlaylistSongSerializer(serializers.Serializer): # Example if you need details in playlist songs
    song_id = ObjectIdField()
    # You could add more song details here if needed by fetching/nesting
    # song_name = serializers.CharField(read_only=True) # Example
    date = serializers.DateTimeField() # From ERD

class PlaylistSerializer(serializers.Serializer):
    _id = ObjectIdField(read_only=True)
    user_id = ObjectIdField() # Assuming created by a user
    playlist_name = serializers.CharField(max_length=255)
    description = serializers.CharField(max_length=255, required=False, allow_blank=True)
    # number_of_songs = serializers.IntegerField(read_only=True) # Often calculated dynamically
    creation_day = serializers.DateTimeField(required=False) # From ERD
    is_public = serializers.BooleanField(default=True)
    # Depending on how you store/retrieve songs for a playlist
    # Option 1: List of ObjectIDs
    # song_ids = serializers.ListField(child=ObjectIdField(), required=False, default=list)
    # Option 2: List of embedded song details (use PlaylistSongSerializer or similar)
    songs = PlaylistSongSerializer(many=True, required=False, default=list) # Matches ERD more closely
    
class ArtistSelectSerializer(serializers.Serializer):
    """ Trả về ID và tên Artist cho dropdown select. """
    _id = ObjectIdField(read_only=True)
    artist_name = serializers.CharField(read_only=True)

class AlbumSelectSerializer(serializers.Serializer):
    """ Trả về ID và tên Album cho dropdown select. """
    _id = ObjectIdField(read_only=True)
    album_name = serializers.CharField(read_only=True)
    
class MusicGenreSelectSerializer(serializers.Serializer):
    """ Trả về ID và tên thể loại nhạc cho dropdown select. """
    _id = ObjectIdField(read_only=True)
    musicgenre_name = serializers.CharField(read_only=True)