# music_api/serializers.py
from rest_framework import serializers
from bson import ObjectId
from django.conf import settings # Import settings
from django.urls import reverse # Có thể không cần nếu chỉ nối chuỗi

class ObjectIdField(serializers.Field): # Custom field to handle ObjectIds
    def to_representation(self, value):
        return str(value)

    def to_internal_value(self, data):
        try:
            return ObjectId(data)
        except:
            raise serializers.ValidationError("Invalid ObjectId")

class MusicGenreSerializer(serializers.Serializer):
    _id = ObjectIdField(read_only=True)
    musicgenre_name = serializers.CharField(max_length=50)

class UserSerializer(serializers.Serializer):
    _id = ObjectIdField(read_only=True)
    username = serializers.CharField(max_length=50)
    email = serializers.EmailField(max_length=100)
    password = serializers.CharField(max_length=255, write_only=True)  # Important: write_only prevents the password from being sent in responses
    profile_picture = serializers.CharField(max_length=255, required=False)
    date_of_birth = serializers.DateTimeField(required=False)
    favourite_songs = serializers.ListField(child=ObjectIdField(), required=False)

class AdminSerializer(serializers.Serializer):
     _id = ObjectIdField(read_only=True)
     user_id = ObjectIdField()
     username = serializers.CharField(max_length=50)
     password = serializers.CharField(max_length=255, write_only=True)

class ArtistSerializer(serializers.Serializer):
    _id = ObjectIdField(read_only=True)
    artist_name = serializers.CharField(max_length=50)
    date_of_birth = serializers.DateTimeField(required=False)
    national = serializers.CharField(max_length=50, required=False)
    description = serializers.CharField(required=False)
    artist_avatar = serializers.CharField(max_length=255, required=False)
    social_media = serializers.CharField(max_length=255, required=False)
    number_of_songs = serializers.IntegerField(required=False)
    number_of_plays = serializers.IntegerField(required=False)
    number_of_likes = serializers.IntegerField(required=False)
    musicgenre_ids = serializers.ListField(child=ObjectIdField(), required=False)

class AlbumSerializer(serializers.Serializer):
    _id = ObjectIdField(read_only=True)
    artist_id = ObjectIdField()
    album_name = serializers.CharField(max_length=50)
    release_time = serializers.DateTimeField(required=False)
    image = serializers.CharField(max_length=255, required=False)
    description = serializers.CharField(required=False)
    number_of_songs = serializers.IntegerField(required=False)
    number_of_plays = serializers.IntegerField(required=False)
    number_of_likes = serializers.IntegerField(required=False)

class SongSerializer(serializers.Serializer):
    _id = ObjectIdField(read_only=True)
    artist_ids = serializers.ListField(child=ObjectIdField())
    musicgenre_ids = serializers.ListField(child=ObjectIdField())
    album_id = ObjectIdField(required=False)
    song_name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False)
    lyrics = serializers.CharField(required=False)
    release_time = serializers.DateTimeField(required=False)
    duration_song = serializers.IntegerField(required=False)
    number_of_plays = serializers.IntegerField(required=False)
    number_of_likes = serializers.IntegerField(required=False)
    file_url = serializers.SerializerMethodField() # Trường mới để chứa URL
    status = serializers.CharField(max_length=20, required=False)
    def get_file_url(self, obj):
        """
        Tạo URL đầy đủ cho file nhạc.
        'obj' ở đây là dictionary đại diện cho document Song từ MongoDB.
        """
        # Lấy đường dẫn tương đối từ database (giả sử lưu trong key 'file_up')
        relative_path = obj.get('file_up')
        if relative_path:
            # Lấy request từ context của serializer
            request = self.context.get('request')
            if request:
                # Xây dựng URL tuyệt đối bằng request.build_absolute_uri
                # và nối với MEDIA_URL và đường dẫn tương đối
                # Loại bỏ dấu / ở đầu relative_path nếu có để tránh //
                media_path = relative_path.lstrip('/')
                # Đảm bảo MEDIA_URL kết thúc bằng /
                media_url = settings.MEDIA_URL if settings.MEDIA_URL.endswith('/') else settings.MEDIA_URL + '/'
                # Nối chúng lại
                absolute_url = request.build_absolute_uri(f"{media_url}{media_path}")
                return absolute_url
            else:
                # Fallback nếu không có request (ít xảy ra với DRF views)
                # Chỉ trả về đường dẫn với MEDIA_URL (không có domain)
                media_path = relative_path.lstrip('/')
                media_url = settings.MEDIA_URL if settings.MEDIA_URL.endswith('/') else settings.MEDIA_URL + '/'
                return f"{media_url}{media_path}"
        return None # Trả về None nếu không có file_up

class PlaylistSerializer(serializers.Serializer):
    _id = ObjectIdField(read_only = True)
    user_id = ObjectIdField()
    playlist_name = serializers.CharField(max_length = 255)
    description = serializers.CharField(required = False)
    number_of_songs = serializers.IntegerField(read_only = True, required = False)
    creation_day = serializers.DateTimeField(required = False)
    is_public = serializers.BooleanField(required = False)
    songs = serializers.ListField(child = serializers.DictField(), required = False) #List of dictionaries